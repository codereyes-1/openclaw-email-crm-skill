#!/usr/bin/env python3
"""Ingest normalized messages from an explicitly selected read-only adapter."""

import argparse
import hashlib
import sys

from adapters import SyntheticJsonAdapter
from email_crm import canonical_json, classify_conversation, connect, emit, initialize, normalize_email, normalize_subject, utc_now


def normalized_address(value):
    if value is None:
        return None
    return normalize_email(value)


parser = argparse.ArgumentParser()
parser.add_argument("--db")
parser.add_argument("--adapter", required=True, choices=("synthetic",))
parser.add_argument("--input", required=True, help="adapter input path; synthetic JSON only in this package")
args = parser.parse_args()

adapter = SyntheticJsonAdapter(args.input)
conn = connect(args.db)
run_id = None
try:
    initialize(conn)
    now = utc_now()
    cursor = conn.execute(
        "INSERT INTO ingestion_runs (adapter_name, source_ref, started_at) VALUES (?, ?, ?)",
        (adapter.name, str(args.input), now),
    )
    run_id = cursor.lastrowid
    imported = duplicates = errors = 0
    touched = set()
    for record in adapter.iter_messages():
        if record.direction not in ("inbound", "outbound", "internal", "unknown"):
            raise ValueError(f"unsupported direction: {record.direction}")
        sender = normalized_address(record.sender)
        recipients = sorted({normalize_email(item) for item in record.recipients})
        subject_normalized = normalize_subject(record.subject)
        participant_key = "|".join(sorted(set(recipients + ([sender] if sender else []))))
        conn.execute(
            "INSERT INTO conversations (provider, account_ref, external_id, subject, subject_normalized, participant_key, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(provider, account_ref, external_id) DO UPDATE SET "
            "subject = COALESCE(excluded.subject, conversations.subject), subject_normalized = COALESCE(excluded.subject_normalized, conversations.subject_normalized), "
            "participant_key = excluded.participant_key, updated_at = excluded.updated_at",
            (record.provider, record.account_ref, record.conversation_external_id, record.subject, subject_normalized, participant_key, now, now),
        )
        conversation_id = conn.execute(
            "SELECT id FROM conversations WHERE provider = ? AND account_ref = ? AND external_id = ?",
            (record.provider, record.account_ref, record.conversation_external_id),
        ).fetchone()["id"]
        content_hash = record.content_hash
        if content_hash is None and record.excerpt is not None:
            content_hash = hashlib.sha256(record.excerpt.encode("utf-8")).hexdigest()
        cursor = conn.execute(
            "INSERT INTO messages (conversation_id, provider, account_ref, external_id, rfc_message_id, direction, sender_normalized, recipients_json, subject, subject_normalized, occurred_at, content_hash, excerpt, metadata_json, ingested_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(provider, account_ref, external_id) DO NOTHING",
            (conversation_id, record.provider, record.account_ref, record.external_id, record.rfc_message_id, record.direction, sender,
             canonical_json(recipients), record.subject, subject_normalized, record.occurred_at, content_hash,
             record.excerpt[:500] if record.excerpt else None, canonical_json(record.metadata), now),
        )
        if cursor.rowcount:
            imported += 1
        else:
            duplicates += 1
        conn.execute(
            "UPDATE conversations SET first_message_at = COALESCE(MIN(first_message_at, ?), ?), "
            "last_message_at = COALESCE(MAX(last_message_at, ?), ?), updated_at = ? WHERE id = ?",
            (record.occurred_at, record.occurred_at, record.occurred_at, record.occurred_at, now, conversation_id),
        )
        touched.add(conversation_id)
    states = []
    for conversation_id in sorted(touched):
        states.append({"conversation_id": conversation_id, **classify_conversation(conn, conversation_id)})
    conn.execute(
        "UPDATE ingestion_runs SET imported_count = ?, duplicate_count = ?, error_count = ?, completed_at = ? WHERE id = ?",
        (imported, duplicates, errors, utc_now(), run_id),
    )
    conn.commit()
    emit({"ok": True, "run_id": run_id, "adapter": adapter.name, "imported": imported, "duplicates": duplicates, "states": states})
except Exception as exc:
    conn.rollback()
    print(f"ingestion failed: {exc}", file=sys.stderr)
    sys.exit(1)
finally:
    conn.close()
