#!/usr/bin/env python3
"""Create an inert action proposal. This command never executes or sends it."""
import argparse
import json

from email_crm import canonical_json, connect, emit, initialize, stable_hash, utc_now

parser = argparse.ArgumentParser()
parser.add_argument("--db")
parser.add_argument("--conversation-id", type=int)
parser.add_argument("--idempotency-key", required=True)
parser.add_argument("--action-type", required=True, choices=("draft_reply", "create_reminder", "update_state", "other"))
parser.add_argument("--payload-json", required=True)
parser.add_argument("--rationale", required=True)
args = parser.parse_args()
try:
    payload = json.loads(args.payload_json)
except ValueError as exc:
    parser.error(f"payload-json must be valid JSON: {exc}")
if not args.idempotency_key.strip() or not args.rationale.strip():
    parser.error("idempotency-key and rationale must not be blank")
payload_json = canonical_json(payload)
payload_hash = stable_hash({"action_type": args.action_type, "payload": payload, "rationale": args.rationale.strip()})

conn = connect(args.db)
try:
    initialize(conn)
    existing = conn.execute("SELECT * FROM action_proposals WHERE idempotency_key = ?", (args.idempotency_key.strip(),)).fetchone()
    created = False
    if existing:
        if existing["payload_hash"] != payload_hash or existing["conversation_id"] != args.conversation_id:
            parser.error("idempotency key already exists with different proposal content")
        proposal_id, status = existing["id"], existing["status"]
    else:
        now = utc_now()
        cursor = conn.execute(
            "INSERT INTO action_proposals (conversation_id, idempotency_key, action_type, payload_json, payload_hash, rationale, proposed_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (args.conversation_id, args.idempotency_key.strip(), args.action_type, payload_json, payload_hash, args.rationale.strip(), now),
        )
        proposal_id, status, created = cursor.lastrowid, "proposed", True
        conn.execute(
            "INSERT INTO action_audit (proposal_id, event_type, actor, details_json, occurred_at) VALUES (?, 'proposed', 'cli', ?, ?)",
            (proposal_id, canonical_json({"payload_hash": payload_hash}), now),
        )
        conn.commit()
    emit({"ok": True, "proposal_id": proposal_id, "status": status, "created": created, "transport_performed": False})
finally:
    conn.close()
