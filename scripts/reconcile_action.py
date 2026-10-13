#!/usr/bin/env python3
"""Idempotently reconcile approval into an auditable no-op; never send email."""
import argparse

from email_crm import canonical_json, connect, emit, initialize, utc_now

parser = argparse.ArgumentParser()
parser.add_argument("--db")
parser.add_argument("--proposal-id", required=True, type=int)
parser.add_argument("--actor", default="reconciler")
args = parser.parse_args()

conn = connect(args.db)
try:
    initialize(conn)
    conn.execute("BEGIN IMMEDIATE")
    row = conn.execute("SELECT status, action_type, payload_json FROM action_proposals WHERE id = ?", (args.proposal_id,)).fetchone()
    if row is None:
        parser.error("proposal not found")
    if row["status"] == "reconciled":
        conn.rollback()
        emit({"ok": True, "proposal_id": args.proposal_id, "status": "reconciled", "changed": False, "transport_performed": False})
    else:
        if row["status"] != "approved":
            conn.rollback()
            parser.error("only approved proposals can be reconciled")
        now = utc_now()
        conn.execute("UPDATE action_proposals SET status = 'reconciled', reconciled_at = ? WHERE id = ?", (now, args.proposal_id))
        conn.execute(
            "INSERT INTO action_audit (proposal_id, event_type, actor, details_json, occurred_at) VALUES (?, 'reconciled_noop', ?, ?, ?)",
            (args.proposal_id, args.actor, canonical_json({"action_type": row["action_type"], "policy": "no_transport"}), now),
        )
        conn.commit()
        emit({"ok": True, "proposal_id": args.proposal_id, "status": "reconciled", "changed": True, "transport_performed": False})
finally:
    conn.close()
