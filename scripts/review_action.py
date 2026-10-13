#!/usr/bin/env python3
"""Approve or reject a proposal without executing it."""
import argparse

from email_crm import canonical_json, connect, emit, initialize, utc_now

parser = argparse.ArgumentParser()
parser.add_argument("--db")
parser.add_argument("--proposal-id", required=True, type=int)
decision = parser.add_mutually_exclusive_group(required=True)
decision.add_argument("--approve", action="store_true")
decision.add_argument("--reject", action="store_true")
parser.add_argument("--actor", default="human-review")
parser.add_argument("--note")
args = parser.parse_args()
target = "approved" if args.approve else "rejected"
event = "approved" if args.approve else "rejected"

conn = connect(args.db)
try:
    initialize(conn)
    row = conn.execute("SELECT status FROM action_proposals WHERE id = ?", (args.proposal_id,)).fetchone()
    if row is None:
        parser.error("proposal not found")
    if row["status"] == target:
        emit({"ok": True, "proposal_id": args.proposal_id, "status": target, "changed": False, "transport_performed": False})
    else:
        if row["status"] != "proposed":
            parser.error(f"cannot {event} proposal in {row['status']} state")
        now = utc_now()
        conn.execute(
            "UPDATE action_proposals SET status = ?, approved_at = CASE WHEN ? = 'approved' THEN ? ELSE approved_at END WHERE id = ?",
            (target, target, now, args.proposal_id),
        )
        conn.execute(
            "INSERT INTO action_audit (proposal_id, event_type, actor, details_json, occurred_at) VALUES (?, ?, ?, ?, ?)",
            (args.proposal_id, event, args.actor, canonical_json({"note": args.note}), now),
        )
        conn.commit()
        emit({"ok": True, "proposal_id": args.proposal_id, "status": target, "changed": True, "transport_performed": False})
finally:
    conn.close()
