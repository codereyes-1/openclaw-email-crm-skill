#!/usr/bin/env python3
"""Produce an attention brief in stable JSON or concise human text."""
import argparse
import json

from email_crm import connect, emit, initialize, utc_now

parser = argparse.ArgumentParser()
parser.add_argument("--db")
parser.add_argument("--json", action="store_true")
parser.add_argument("--limit", type=int, default=50)
args = parser.parse_args()
if args.limit < 1 or args.limit > 500:
    parser.error("limit must be between 1 and 500")

conn = connect(args.db)
try:
    initialize(conn)
    rows = conn.execute(
        "SELECT id, subject, computed_state, state_confidence, state_evidence_json, manual_state, last_message_at "
        "FROM conversations WHERE computed_state IN ('awaiting_me','needs_review') "
        "ORDER BY CASE computed_state WHEN 'awaiting_me' THEN 0 ELSE 1 END, COALESCE(last_message_at, created_at), id LIMIT ?",
        (args.limit,),
    ).fetchall()
    items = []
    for row in rows:
        obligations = conn.execute(
            "SELECT id, summary, owner, due_at, confidence FROM obligations WHERE conversation_id = ? AND status = 'open' "
            "ORDER BY CASE WHEN due_at IS NULL THEN 1 ELSE 0 END, due_at, id",
            (row["id"],),
        ).fetchall()
        items.append({
            "conversation_id": row["id"], "subject": row["subject"], "state": row["computed_state"],
            "confidence": row["state_confidence"], "manual_override": row["manual_state"] is not None,
            "evidence": json.loads(row["state_evidence_json"]), "last_message_at": row["last_message_at"],
            "obligations": [dict(item) for item in obligations],
        })
    payload = {"ok": True, "generated_at": utc_now(), "count": len(items), "items": items}
    if args.json:
        emit(payload)
    else:
        print(f"Email CRM brief — {len(items)} item(s) need attention")
        for item in items:
            marker = " [manual]" if item["manual_override"] else ""
            print(f"- #{item['conversation_id']} {item['state']} ({item['confidence']:.2f}){marker}: {item['subject'] or '(no subject)'}")
            for obligation in item["obligations"]:
                due = f" due {obligation['due_at']}" if obligation["due_at"] else ""
                print(f"  - [{obligation['owner']}] {obligation['summary']}{due}")
finally:
    conn.close()
