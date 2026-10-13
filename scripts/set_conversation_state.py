#!/usr/bin/env python3
"""Set or clear an explicit human state override and retain its evidence."""
import argparse

from email_crm import CONVERSATION_STATES, classify_conversation, connect, emit, initialize, utc_now

parser = argparse.ArgumentParser()
parser.add_argument("--db")
parser.add_argument("--conversation-id", required=True, type=int)
group = parser.add_mutually_exclusive_group(required=True)
group.add_argument("--state", choices=CONVERSATION_STATES)
group.add_argument("--clear", action="store_true")
parser.add_argument("--reason", help="required with --state")
args = parser.parse_args()
if args.state and not (args.reason or "").strip():
    parser.error("--reason is required with --state")

conn = connect(args.db)
try:
    initialize(conn)
    if args.clear:
        values = (None, None, None, utc_now(), args.conversation_id)
    else:
        values = (args.state, args.reason.strip(), utc_now(), utc_now(), args.conversation_id)
    updated = conn.execute(
        "UPDATE conversations SET manual_state = ?, manual_state_reason = ?, manual_state_at = ?, updated_at = ? WHERE id = ?",
        values,
    ).rowcount
    if not updated:
        parser.error("conversation not found")
    decision = classify_conversation(conn, args.conversation_id)
    conn.commit()
    emit({"ok": True, "conversation_id": args.conversation_id, **decision})
finally:
    conn.close()
