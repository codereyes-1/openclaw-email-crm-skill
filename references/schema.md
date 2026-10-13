# Schema contract

Schema version: `2`

## `contacts`

| Column | Meaning |
| --- | --- |
| `id` | Stable local integer identifier. |
| `email` | Trimmed, lowercased email. This currently matches `email_normalized`. |
| `email_normalized` | Trimmed, lowercased email used for every comparison; unique. |
| `source` | Required accountable origin such as `manual-review`. |
| `do_not_contact` | `0` or `1`; set to `1` whenever the address is suppressed. |
| `created_at`, `updated_at` | UTC ISO-8601 timestamps. |

An upsert returns JSON containing `ok` and `contact_id`. It replaces the stored `source` and refreshes `updated_at`, while retaining `created_at` and any existing DNC state. If the normalized address was suppressed before the contact existed, the inserted contact starts with `do_not_contact = 1`.

## `email_events`

Append-only lifecycle entries. `contact_id` references `contacts(id)` and is protected by a foreign key. Event types are constrained to `drafted`, `queued`, `sent`, `delivered`, `opened`, `replied`, `bounced`, and `failed`.

`metadata_json` is optional and must contain valid JSON. Do not place email content, recipient addresses, credentials, or sensitive personal data in it.

## `email_suppressions`

One row per normalized email address. Suppressing an address is idempotent and synchronizes matching contacts to `do_not_contact = 1`. The first persisted reason is retained and returned on later calls.

## `schema_meta`

Stores the schema version. SQL migrations live in `migrations/` and are applied in numeric order. Version 2 migrates version 1 in place.

## `conversations` and `messages`

Provider/account/external IDs form stable idempotency keys. Messages normalize direction, participants, subject, timestamp, optional RFC Message-ID, a content hash, and at most a 500-character excerpt. Conversations store deterministic computed state, confidence, evidence JSON, and an optional manual override.

## `obligations`

One reusable idempotency key identifies each obligation. Owner, status, due time, confidence, and evidence are explicit. Open obligations participate in deterministic state classification.

## `action_proposals` and `action_audit`

Proposals are inert JSON records identified by a unique idempotency key and canonical payload hash. Review and no-op reconciliation append audit events. There is deliberately no delivery or provider-execution table.

## `ingestion_runs`

Records adapter name, source reference, counts, and timestamps for local operational audit. It never stores credentials.
