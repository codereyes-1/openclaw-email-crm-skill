"""Shared SQLite utilities for the email-only CRM skill."""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 1
EVENT_TYPES = ("drafted", "queued", "sent", "delivered", "opened", "replied", "bounced", "failed")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalize_email(value: str) -> str:
    normalized = value.strip().lower()
    if not EMAIL_RE.fullmatch(normalized):
        raise ValueError("invalid email address")
    return normalized


def add_db_argument(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--db", help="SQLite database path; defaults to EMAIL_CRM_DB or data/email_crm.sqlite")


def resolve_db_path(value: str | None) -> Path:
    return Path(value or os.environ.get("EMAIL_CRM_DB") or "data/email_crm.sqlite")


def connect(db_path: str | None) -> sqlite3.Connection:
    path = resolve_db_path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def initialize(conn: sqlite3.Connection) -> int:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS schema_meta (
            singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
            schema_version INTEGER NOT NULL CHECK (schema_version >= 1),
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS contacts (
            id INTEGER PRIMARY KEY,
            email TEXT NOT NULL,
            email_normalized TEXT NOT NULL UNIQUE,
            source TEXT NOT NULL CHECK (length(trim(source)) > 0),
            do_not_contact INTEGER NOT NULL DEFAULT 0 CHECK (do_not_contact IN (0, 1)),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS email_suppressions (
            id INTEGER PRIMARY KEY,
            email_normalized TEXT NOT NULL UNIQUE,
            reason TEXT NOT NULL CHECK (length(trim(reason)) > 0),
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS email_events (
            id INTEGER PRIMARY KEY,
            contact_id INTEGER NOT NULL REFERENCES contacts(id),
            event_type TEXT NOT NULL CHECK (event_type IN ('drafted', 'queued', 'sent', 'delivered', 'opened', 'replied', 'bounced', 'failed')),
            metadata_json TEXT,
            occurred_at TEXT NOT NULL
        );
        """
    )
    row = conn.execute("SELECT schema_version FROM schema_meta WHERE singleton = 1").fetchone()
    now = utc_now()
    if row is None:
        conn.execute("INSERT INTO schema_meta (singleton, schema_version, updated_at) VALUES (1, ?, ?)", (SCHEMA_VERSION, now))
    elif row["schema_version"] > SCHEMA_VERSION:
        raise RuntimeError("database schema is newer than this skill")
    elif row["schema_version"] < SCHEMA_VERSION:
        raise RuntimeError("no migration is available for this database version")
    conn.commit()
    return SCHEMA_VERSION


def require_initialized(conn: sqlite3.Connection) -> None:
    row = conn.execute("SELECT schema_version FROM schema_meta WHERE singleton = 1").fetchone()
    if row is None:
        raise RuntimeError("database is not initialized; run init_email_crm.py first")


def parse_metadata(value: str | None) -> str | None:
    if value is None:
        return None
    parsed = json.loads(value)
    return json.dumps(parsed, sort_keys=True, separators=(",", ":"))


def emit(payload: dict) -> None:
    print(json.dumps(payload, sort_keys=True))
