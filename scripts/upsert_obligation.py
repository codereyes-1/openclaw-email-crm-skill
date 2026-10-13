#!/usr/bin/env python3
"""Create or update a deterministic conversation obligation."""
import argparse

from email_crm import canonical_json, classify_conversation, connect, emit, initialize, utc_now

parser = argparse.ArgumentParser()
parser.add_argument("--db")
parser.add_argument("--conversation-id", required=True, type=int)
parser.add_argument("--idempotency-key", required=True)
parser.add_argument("--summary", required=True)
parser.add_argument("--owner", required=True, choices=("me", "them", "third_party", "unknown"))
parser.add_argument("--status", default="open", choices=("open", "completed", "canceled"))
parser.add_argument("--due-at")
parser.add_argument("--confidence", type=float, default=1.0)
parser.add_argument("--evidence-json", default="[]")
args = parser.parse_args()
if not 0.0 <= args.confidence <= 1.0:
    parser.error("confidence must be between 0 and 1")
try:
    import json
    evidence = json.loads(args.evidence_json)
except ValueError as exc:
    parser.error(f"evidence-json must be valid JSON: {exc}")
if not args.summary.strip() or not args.idempotency_key.strip():
    parser.error("summary and idempotency-key must not be blank")

conn = connect(args.db)
try:
    initialize(conn)
    now = utc_now()
    conn.execute(
        "INSERT INTO obligations (conversation_id, idempotency_key, summary, owner, status, due_at, confidence, evidence_json, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(idempotency_key) DO UPDATE SET "
        "summary = excluded.summary, owner = excluded.owner, status = excluded.status, due_at = excluded.due_at, "
        "confidence = excluded.confidence, evidence_json = excluded.evidence_json, updated_at = excluded.updated_at",
        (args.conversation_id, args.idempotency_key.strip(), args.summary.strip(), args.owner, args.status, args.due_at,
         args.confidence, canonical_json(evidence), now, now),
    )
    row = conn.execute("SELECT id, conversation_id FROM obligations WHERE idempotency_key = ?", (args.idempotency_key.strip(),)).fetchone()
    if row["conversation_id"] != args.conversation_id:
        raise ValueError("idempotency key belongs to a different conversation")
    decision = classify_conversation(conn, args.conversation_id)
    conn.commit()
    emit({"ok": True, "obligation_id": row["id"], "conversation_id": args.conversation_id, "state": decision})
finally:
    conn.close()
