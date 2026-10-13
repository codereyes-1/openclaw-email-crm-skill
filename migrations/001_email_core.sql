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
    event_type TEXT NOT NULL CHECK (event_type IN ('drafted','queued','sent','delivered','opened','replied','bounced','failed')),
    metadata_json TEXT,
    occurred_at TEXT NOT NULL
);
