"""Shared SQLite utilities for the email-only CRM skill."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

SCHEMA_VERSION = 2
EVENT_TYPES = ("drafted", "queued", "sent", "delivered", "opened", "replied", "bounced", "failed")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
DEFAULT_DATA_HOME = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
DEFAULT_DB_PATH = DEFAULT_DATA_HOME / "openclaw-email-crm" / "email_crm.sqlite"
MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"
CONVERSATION_STATES = ("new", "awaiting_me", "awaiting_them", "closed", "needs_review")


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalize_utc_timestamp(value: str, field_name: str = "timestamp") -> str:
    if not isinstance(value, str) or "T" not in value:
        raise ValueError(f"{field_name} must be an ISO-8601 timestamp with a timezone")
    candidate = value.strip()
    try:
        parsed = datetime.fromisoformat(candidate[:-1] + "+00:00" if candidate.endswith("Z") else candidate)
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO-8601 timestamp with a timezone") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field_name} must be an ISO-8601 timestamp with a timezone")
    normalized = parsed.astimezone(timezone.utc)
    return normalized.isoformat(timespec="microseconds").replace("+00:00", "Z")


def normalize_email(value: str) -> str:
    normalized = value.strip().lower()
    if not EMAIL_RE.fullmatch(normalized):
        raise ValueError("invalid email address")
    return normalized


def add_db_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--db", help="SQLite database path; defaults to EMAIL_CRM_DB or the per-user data directory")


def add_email_arguments(parser: argparse.ArgumentParser) -> None:
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--email", help="email address (prefer --email-stdin in agent automation)")
    group.add_argument("--email-stdin", action="store_true", help="read the email address from standard input")


def read_email_argument(args: argparse.Namespace) -> str:
    return sys.stdin.read() if args.email_stdin else args.email


def resolve_db_path(value: Optional[str]) -> Path:
    return Path(value or os.environ.get("EMAIL_CRM_DB") or DEFAULT_DB_PATH).expanduser()


def enforce_database_permissions(path: Path) -> None:
    for candidate in (path, Path(f"{path}-wal"), Path(f"{path}-shm"), Path(f"{path}-journal")):
        try:
            candidate.chmod(0o600)
        except FileNotFoundError:
            pass


def connect(db_path: Optional[str]) -> sqlite3.Connection:
    path = resolve_db_path(db_path)
    previous_umask = os.umask(0o077)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(path)
    finally:
        os.umask(previous_umask)
    enforce_database_permissions(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def initialize(conn: sqlite3.Connection) -> int:
    # Compatibility must be established before any DDL or journal-mode change.
    # That keeps an unsupported database byte-for-byte untouched.
    meta_exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'schema_meta'"
    ).fetchone()
    if meta_exists:
        row = conn.execute("SELECT schema_version FROM schema_meta WHERE singleton = 1").fetchone()
        if row is None:
            raise RuntimeError("database schema metadata is invalid")
        if row["schema_version"] > SCHEMA_VERSION:
            raise RuntimeError("database schema is newer than this skill")
        if row["schema_version"] < 1:
            raise RuntimeError("no migration is available for this database version")
    row = conn.execute("SELECT schema_version FROM schema_meta WHERE singleton = 1").fetchone() if meta_exists else None
    current = int(row["schema_version"]) if row else 0
    for version in range(current + 1, SCHEMA_VERSION + 1):
        matches = sorted(MIGRATIONS_DIR.glob(f"{version:03d}_*.sql"))
        if len(matches) != 1:
            raise RuntimeError(f"expected exactly one migration for schema version {version}")
        try:
            now = utc_now()
            quoted_now = conn.execute("SELECT quote(?)", (now,)).fetchone()[0]
            if version == 1:
                version_statement = (
                    f"INSERT INTO schema_meta (singleton, schema_version, updated_at) VALUES (1, {version}, {quoted_now});"
                )
            else:
                version_statement = (
                    f"UPDATE schema_meta SET schema_version = {version}, updated_at = {quoted_now} WHERE singleton = 1;"
                )
            migration_sql = matches[0].read_text(encoding="utf-8")
            conn.executescript(f"BEGIN IMMEDIATE;\n{migration_sql}\n{version_statement}\nCOMMIT;")
        except Exception:
            conn.rollback()
            raise
    row = conn.execute("SELECT schema_version FROM schema_meta WHERE singleton = 1").fetchone()
    now = utc_now()
    if row is None or int(row["schema_version"]) != SCHEMA_VERSION:
        raise RuntimeError("database migration did not reach the expected schema version")
    conn.execute("PRAGMA journal_mode = WAL")
    database_path = conn.execute("PRAGMA database_list").fetchone()[2]
    if database_path:
        enforce_database_permissions(Path(database_path))
    return SCHEMA_VERSION


def require_initialized(conn: sqlite3.Connection) -> None:
    row = conn.execute("SELECT schema_version FROM schema_meta WHERE singleton = 1").fetchone()
    if row is None:
        raise RuntimeError("database is not initialized; run init_email_crm.py first")


def parse_metadata(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    parsed = json.loads(value)
    return json.dumps(parsed, sort_keys=True, separators=(",", ":"))


def emit(payload: dict) -> None:
    print(json.dumps(payload, sort_keys=True))


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def stable_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def normalize_subject(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    subject = " ".join(value.split())
    while re.match(r"^(?:re|fw|fwd)\s*:\s*", subject, flags=re.IGNORECASE):
        subject = re.sub(r"^(?:re|fw|fwd)\s*:\s*", "", subject, count=1, flags=re.IGNORECASE)
    return subject.casefold() or None


def classify_conversation(conn: sqlite3.Connection, conversation_id: int) -> dict:
    conversation = conn.execute(
        "SELECT manual_state, manual_state_reason FROM conversations WHERE id = ?", (conversation_id,)
    ).fetchone()
    if conversation is None:
        raise ValueError("conversation not found")
    if conversation["manual_state"]:
        decision = {
            "state": conversation["manual_state"],
            "confidence": 1.0,
            "evidence": [{"type": "manual_override", "reason": conversation["manual_state_reason"]}],
            "manual_override": True,
        }
    else:
        obligation = conn.execute(
            "SELECT id, owner, due_at FROM obligations WHERE conversation_id = ? AND status = 'open' "
            "ORDER BY CASE WHEN due_at IS NULL THEN 1 ELSE 0 END, due_at, id LIMIT 1",
            (conversation_id,),
        ).fetchone()
        latest = conn.execute(
            "SELECT id, direction, occurred_at FROM messages WHERE conversation_id = ? "
            "ORDER BY occurred_at DESC, id DESC LIMIT 1",
            (conversation_id,),
        ).fetchone()
        if obligation and obligation["owner"] == "me":
            state, confidence = "awaiting_me", 0.98
            evidence = [{"type": "open_obligation", "obligation_id": obligation["id"], "owner": "me"}]
        elif obligation and obligation["owner"] in ("them", "third_party"):
            state, confidence = "awaiting_them", 0.96
            evidence = [{"type": "open_obligation", "obligation_id": obligation["id"], "owner": obligation["owner"]}]
        elif latest is None:
            state, confidence, evidence = "new", 1.0, [{"type": "no_messages"}]
        elif latest["direction"] == "inbound":
            state, confidence = "awaiting_me", 0.9
            evidence = [{"type": "latest_direction", "message_id": latest["id"], "direction": "inbound"}]
        elif latest["direction"] == "outbound":
            state, confidence = "awaiting_them", 0.85
            evidence = [{"type": "latest_direction", "message_id": latest["id"], "direction": "outbound"}]
        else:
            state, confidence = "needs_review", 0.35
            evidence = [{"type": "ambiguous_latest_direction", "message_id": latest["id"], "direction": latest["direction"]}]
        decision = {"state": state, "confidence": confidence, "evidence": evidence, "manual_override": False}
    conn.execute(
        "UPDATE conversations SET computed_state = ?, state_confidence = ?, state_evidence_json = ?, updated_at = ? WHERE id = ?",
        (decision["state"], decision["confidence"], canonical_json(decision["evidence"]), utc_now(), conversation_id),
    )
    return decision
