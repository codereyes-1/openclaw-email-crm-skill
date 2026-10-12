#!/usr/bin/env python3
"""Create or update a sourced email contact without emitting its address."""
import argparse

from email_crm import add_db_argument, connect, emit, initialize, normalize_email, utc_now

parser = argparse.ArgumentParser()
add_db_argument(parser)
parser.add_argument("--email", required=True)
parser.add_argument("--source", required=True)
args = parser.parse_args()

try:
    email = normalize_email(args.email)
except ValueError as exc:
    parser.error(str(exc))
if not args.source.strip():
    parser.error("source must not be blank")

conn = connect(args.db)
try:
    initialize(conn)
    now = utc_now()
    conn.execute(
        """
        INSERT INTO contacts (email, email_normalized, source, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(email_normalized) DO UPDATE SET
            email = excluded.email,
            source = excluded.source,
            updated_at = excluded.updated_at
        """,
        (email, email, args.source.strip(), now, now),
    )
    contact = conn.execute("SELECT id FROM contacts WHERE email_normalized = ?", (email,)).fetchone()
    conn.commit()
    emit({"ok": True, "contact_id": contact["id"]})
finally:
    conn.close()
