CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY,
    provider TEXT NOT NULL,
    account_ref TEXT NOT NULL DEFAULT '',
    external_id TEXT NOT NULL,
    subject TEXT,
    subject_normalized TEXT,
    participant_key TEXT NOT NULL DEFAULT '',
    computed_state TEXT NOT NULL DEFAULT 'new'
      CHECK (computed_state IN ('new','awaiting_me','awaiting_them','closed','needs_review')),
    state_confidence REAL NOT NULL DEFAULT 0.0 CHECK (state_confidence BETWEEN 0.0 AND 1.0),
    state_evidence_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(state_evidence_json)),
    manual_state TEXT CHECK (manual_state IN ('new','awaiting_me','awaiting_them','closed','needs_review')),
    manual_state_reason TEXT,
    manual_state_at TEXT,
    first_message_at TEXT,
    last_message_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(provider, account_ref, external_id)
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY,
    conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    provider TEXT NOT NULL,
    account_ref TEXT NOT NULL DEFAULT '',
    external_id TEXT NOT NULL,
    rfc_message_id TEXT,
    direction TEXT NOT NULL CHECK (direction IN ('inbound','outbound','internal','unknown')),
    sender_normalized TEXT,
    recipients_json TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(recipients_json)),
    subject TEXT,
    subject_normalized TEXT,
    occurred_at TEXT NOT NULL,
    content_hash TEXT,
    excerpt TEXT CHECK (excerpt IS NULL OR length(excerpt) <= 500),
    metadata_json TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(metadata_json)),
    ingested_at TEXT NOT NULL,
    UNIQUE(provider, account_ref, external_id)
);
CREATE INDEX IF NOT EXISTS idx_messages_conversation_time ON messages(conversation_id, occurred_at, id);
CREATE INDEX IF NOT EXISTS idx_messages_rfc_id ON messages(rfc_message_id) WHERE rfc_message_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS obligations (
    id INTEGER PRIMARY KEY,
    conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    source_message_id INTEGER REFERENCES messages(id) ON DELETE SET NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    summary TEXT NOT NULL CHECK (length(trim(summary)) > 0),
    owner TEXT NOT NULL CHECK (owner IN ('me','them','third_party','unknown')),
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open','completed','canceled')),
    due_at TEXT,
    confidence REAL NOT NULL CHECK (confidence BETWEEN 0.0 AND 1.0),
    evidence_json TEXT NOT NULL CHECK (json_valid(evidence_json)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_obligations_open ON obligations(status, due_at, owner);

CREATE TABLE IF NOT EXISTS action_proposals (
    id INTEGER PRIMARY KEY,
    conversation_id INTEGER REFERENCES conversations(id) ON DELETE SET NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    action_type TEXT NOT NULL CHECK (action_type IN ('draft_reply','create_reminder','update_state','other')),
    payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
    payload_hash TEXT NOT NULL,
    rationale TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'proposed'
      CHECK (status IN ('proposed','approved','rejected','reconciled','canceled')),
    proposed_at TEXT NOT NULL,
    approved_at TEXT,
    reconciled_at TEXT
);

CREATE TABLE IF NOT EXISTS action_audit (
    id INTEGER PRIMARY KEY,
    proposal_id INTEGER REFERENCES action_proposals(id) ON DELETE SET NULL,
    event_type TEXT NOT NULL CHECK (event_type IN ('proposed','approved','rejected','reconciled_noop','canceled')),
    actor TEXT NOT NULL,
    details_json TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(details_json)),
    occurred_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_action_audit_proposal ON action_audit(proposal_id, occurred_at);

CREATE TABLE IF NOT EXISTS ingestion_runs (
    id INTEGER PRIMARY KEY,
    adapter_name TEXT NOT NULL,
    source_ref TEXT,
    imported_count INTEGER NOT NULL DEFAULT 0,
    duplicate_count INTEGER NOT NULL DEFAULT 0,
    error_count INTEGER NOT NULL DEFAULT 0,
    started_at TEXT NOT NULL,
    completed_at TEXT
);
