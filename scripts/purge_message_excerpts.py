#!/usr/bin/env python3
"""Minimize retained content by nulling old excerpts; dry-run unless --apply."""
import argparse

from email_crm import connect, emit, initialize, normalize_utc_timestamp

parser = argparse.ArgumentParser()
parser.add_argument("--db")
parser.add_argument("--before", required=True, help="exclusive ISO-8601 cutoff compared to occurred_at")
parser.add_argument("--apply", action="store_true", help="perform the update; otherwise report only")
args = parser.parse_args()
cutoff = normalize_utc_timestamp(args.before, "before")

conn = connect(args.db)
try:
    initialize(conn)
    count = conn.execute(
        "SELECT COUNT(*) FROM messages WHERE excerpt IS NOT NULL AND occurred_at < ?", (cutoff,)
    ).fetchone()[0]
    if args.apply:
        conn.execute("UPDATE messages SET excerpt = NULL WHERE excerpt IS NOT NULL AND occurred_at < ?", (cutoff,))
        conn.commit()
    emit({"ok": True, "eligible": count, "purged": count if args.apply else 0, "applied": args.apply})
finally:
    conn.close()
