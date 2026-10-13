#!/usr/bin/env python3
"""Ingest normalized messages from an explicitly selected read-only adapter."""

import argparse
import hashlib
import re
import sys
from pathlib import Path

from adapters import SyntheticJsonAdapter
from email_crm import (
    canonical_json,
    classify_conversation,
    connect,
    emit,
    initialize,
    normalize_email,
    normalize_subject,
    normalize_utc_timestamp,
    utc_now,
)


SENSITIVE_METADATA_KEYS = {
    "api_key", "attachment", "attachments", "authorization", "body", "client_secret", "cookie", "cookies",
    "credential", "credentials", "headers", "html", "html_body", "id_token", "password", "passwd",
    "private_key", "raw", "raw_body", "raw_headers", "refresh_token", "secret", "session_token", "set_cookie",
    "text_body", "token", "access_token",
}
MAX_METADATA_BYTES = 16 * 1024


def required_identifier(value, field_name, max_length):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    normalized = value.strip()
    if len(normalized) > max_length:
        raise ValueError(f"{field_name} exceeds {max_length} characters")
    return normalized


def validate_metadata(value):
    if not isinstance(value, dict):
        raise ValueError("metadata must be a JSON object")

    def inspect(item):
        if isinstance(item, dict):
            for key, child in item.items():
                if not isinstance(key, str):
                    raise ValueError("metadata object keys must be strings")
                normalized_key = re.sub(r"[^a-z0-9]+", "_", key.casefold()).strip("_")
                if normalized_key in SENSITIVE_METADATA_KEYS:
                    raise ValueError(f"metadata key is not allowed: {key}")
                inspect(child)
        elif isinstance(item, list):
            for child in item:
                inspect(child)

    inspect(value)
    serialized = canonical_json(value)
    if len(serialized.encode("utf-8")) > MAX_METADATA_BYTES:
        raise ValueError(f"metadata exceeds {MAX_METADATA_BYTES} bytes")
    return serialized


def synthetic_source_ref(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "content-sha256:" + digest.hexdigest()


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
    source_ref = synthetic_source_ref(args.input)
    cursor = conn.execute(
        "INSERT INTO ingestion_runs (adapter_name, source_ref, started_at) VALUES (?, ?, ?)",
        (adapter.name, source_ref, now),
    )
    run_id = cursor.lastrowid
    imported = duplicates = errors = 0
    touched = set()
    for record in adapter.iter_messages():
        provider = required_identifier(record.provider, "provider", 128)
        account_ref = required_identifier(record.account_ref, "account_ref", 512)
        external_id = required_identifier(record.external_id, "external_id", 512)
        conversation_external_id = required_identifier(
            record.conversation_external_id, "conversation_external_id", 512
        )
        if record.direction not in ("inbound", "outbound", "internal", "unknown"):
            raise ValueError(f"unsupported direction: {record.direction}")
        occurred_at = normalize_utc_timestamp(record.occurred_at, "occurred_at")
        sender = normalized_address(record.sender)
        recipients = sorted({normalize_email(item) for item in record.recipients})
        subject_normalized = normalize_subject(record.subject)
        participant_key = "|".join(sorted(set(recipients + ([sender] if sender else []))))
        excerpt = record.excerpt[:500] if record.excerpt else None
        metadata_json = validate_metadata(record.metadata)
        content_hash = record.content_hash
        if content_hash is None and record.excerpt is not None:
            content_hash = hashlib.sha256(record.excerpt.encode("utf-8")).hexdigest()
        expected_message = (
            record.rfc_message_id,
            record.direction,
            sender,
            canonical_json(recipients),
            record.subject,
            subject_normalized,
            occurred_at,
            content_hash,
            excerpt,
            metadata_json,
        )
        existing = conn.execute(
            "SELECT m.conversation_id, c.external_id AS conversation_external_id, m.rfc_message_id, m.direction, "
            "m.sender_normalized, m.recipients_json, m.subject, m.subject_normalized, m.occurred_at, "
            "m.content_hash, m.excerpt, m.metadata_json FROM messages m JOIN conversations c ON c.id = m.conversation_id "
            "WHERE m.provider = ? AND m.account_ref = ? AND m.external_id = ?",
            (provider, account_ref, external_id),
        ).fetchone()
        if existing is not None:
            stored_message = (
                existing["rfc_message_id"], existing["direction"], existing["sender_normalized"],
                existing["recipients_json"], existing["subject"], existing["subject_normalized"],
                normalize_utc_timestamp(existing["occurred_at"], "stored occurred_at"), existing["content_hash"],
                existing["excerpt"], existing["metadata_json"],
            )
            if existing["conversation_external_id"] != conversation_external_id or stored_message != expected_message:
                raise ValueError("conflicting duplicate message identity")
            duplicates += 1
            touched.add(existing["conversation_id"])
            continue
        conn.execute(
            "INSERT INTO conversations (provider, account_ref, external_id, subject, subject_normalized, participant_key, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(provider, account_ref, external_id) DO UPDATE SET "
            "subject = COALESCE(excluded.subject, conversations.subject), subject_normalized = COALESCE(excluded.subject_normalized, conversations.subject_normalized), "
            "participant_key = excluded.participant_key, updated_at = excluded.updated_at",
            (provider, account_ref, conversation_external_id, record.subject, subject_normalized, participant_key, now, now),
        )
        conversation_id = conn.execute(
            "SELECT id FROM conversations WHERE provider = ? AND account_ref = ? AND external_id = ?",
            (provider, account_ref, conversation_external_id),
        ).fetchone()["id"]
        cursor = conn.execute(
            "INSERT INTO messages (conversation_id, provider, account_ref, external_id, rfc_message_id, direction, sender_normalized, recipients_json, subject, subject_normalized, occurred_at, content_hash, excerpt, metadata_json, ingested_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(provider, account_ref, external_id) DO NOTHING",
            (conversation_id, provider, account_ref, external_id, record.rfc_message_id, record.direction, sender,
             canonical_json(recipients), record.subject, subject_normalized, occurred_at, content_hash,
             excerpt, metadata_json, now),
        )
        if cursor.rowcount:
            imported += 1
        else:
            duplicates += 1
        conn.execute(
            "UPDATE conversations SET first_message_at = COALESCE(MIN(first_message_at, ?), ?), "
            "last_message_at = COALESCE(MAX(last_message_at, ?), ?), updated_at = ? WHERE id = ?",
            (occurred_at, occurred_at, occurred_at, occurred_at, now, conversation_id),
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
