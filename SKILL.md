---
name: email-crm
description: Maintain a local, provider-neutral email CRM in SQLite. Use for sourced contacts and suppressions, normalized conversation ingestion, deterministic attention state and obligations, briefings, or reviewed action proposals. This skill never discovers contacts or sends email.
license: MIT
metadata:
  openclaw:
    emoji: "✉️"
---

# Email CRM

Use this skill as a local decision and audit layer for email workflows. It stores contacts, normalized message metadata, conversation state, obligations, and inert action proposals. It does not discover leads, enrich profiles, make calls, connect to a mailbox by itself, or send messages.

## 1. Choose the database

Pass `--db PATH` to every helper for an explicit database. If omitted, helpers use `EMAIL_CRM_DB`, then `$XDG_DATA_HOME/openclaw-email-crm/email_crm.sqlite` (or `~/.local/share/openclaw-email-crm/email_crm.sqlite` when `XDG_DATA_HOME` is unset). The default never depends on the caller's current working directory. Database files and SQLite sidecars are restricted to the owning user (`0600`).

`{baseDir}` below is the absolute installation directory supplied by OpenClaw. Keep it in every script invocation so commands work regardless of the current working directory.

## 2. Initialize before use

```bash
python3 "{baseDir}/scripts/init_email_crm.py" --db /absolute/private/path/email_crm.sqlite
```

The command creates or migrates the versioned schema, verifies compatibility with an existing database, and enables SQLite foreign keys. Confirm that it returns `schema_version: 2`. Existing version 1 databases migrate in place without replacing contact, event, or suppression tables.

## 3. Add or update a sourced contact

```bash
python3 "{baseDir}/scripts/upsert_contact.py" \
  --db /absolute/private/path/email_crm.sqlite \
  --email-stdin \
  --source "manual-review"
```

Provide the email value on standard input. Agents must use `--email-stdin`, passing the value directly as stdin rather than interpolating it into a shell command or exposing it in process arguments. `--email` remains available for attended CLI use.

`--source` is required. The helper trims and lowercases the email before storing it in both email columns, upserts exactly one contact, and returns JSON containing `ok` and the stable numeric `contact_id`. On an existing contact it replaces `source`, refreshes `updated_at`, and preserves DNC state. A suppression created before the contact also sets the new contact's DNC state.

## 4. Check readiness before an external sender acts

```bash
python3 "{baseDir}/scripts/check_email_readiness.py" \
  --db /absolute/private/path/email_crm.sqlite \
  --email-stdin
```

Treat `ready: false` as a hard stop. A caller must run this check immediately before queuing or sending email, then respect every returned reason code. This skill does not itself send email.

## 5. Record email lifecycle events

```bash
python3 "{baseDir}/scripts/log_email_event.py" \
  --db /absolute/private/path/email_crm.sqlite \
  --contact-id 1 \
  --event-type drafted
```

Allowed event types are `drafted`, `queued`, `sent`, `delivered`, `opened`, `replied`, `bounced`, and `failed`. Use `--metadata-json` only for non-sensitive operational metadata.

## 6. Process a manual DNC request or unsubscribe

```bash
python3 "{baseDir}/scripts/suppress_email.py" \
  --db /absolute/private/path/email_crm.sqlite \
  --email-stdin \
  --reason unsubscribe
```

Suppression is normalized, unique, idempotent, and also marks any matching contact as `do_not_contact`. Its JSON `reason` is the reason actually persisted by the first suppression, even if a later idempotent call supplies a different reason. Do not log raw email addresses in surrounding automation.

## 7. Ingest normalized messages

Adapters implement the read-only contract in `scripts/adapters/base.py`. This package ships only a synthetic JSON adapter:

```bash
python3 "{baseDir}/scripts/ingest_messages.py" --db /absolute/private/path/email_crm.sqlite \
  --adapter synthetic --input "{baseDir}/fixtures/synthetic_messages.json"
```

Confirm `imported`, `duplicates`, and each deterministic state result. Repeating the same input must increase `duplicates`, not message count. Add provider adapters outside the core and keep fetch credentials out of this repository and database.

## 8. Record obligations and corrections

```bash
python3 "{baseDir}/scripts/upsert_obligation.py" --db /absolute/private/path/email_crm.sqlite \
  --conversation-id 1 --idempotency-key revised-quote-v1 --summary "Send revised quote" \
  --owner me --confidence 0.95 --evidence-json '[{"message_id":2}]'

python3 "{baseDir}/scripts/set_conversation_state.py" --db /absolute/private/path/email_crm.sqlite \
  --conversation-id 1 --state closed --reason "Operator confirmed completion"
```

Manual overrides win until explicitly cleared with `--clear`. Every computed decision retains machine-readable evidence and confidence.

## 9. Produce a briefing

Use `brief_email_crm.py --json` for agents and omit `--json` for human text. The brief includes only `awaiting_me` and `needs_review` conversations, their evidence, and open obligations.

## 10. Propose and review actions

Create with `propose_action.py`, approve or reject with `review_action.py`, and record a no-op reconciliation with `reconcile_action.py`. Every proposal requires an idempotency key; reused keys must have identical content. Reconciliation only writes `reconciled_noop` to the local audit trail and always reports `transport_performed: false`. No script in this skill connects to a sending provider.

## Verification

Run `cd "{baseDir}" && python3 -m unittest discover -s tests -v`. The tests use only temporary databases and `example.com` addresses.

See [the schema reference](references/schema.md), [adapter contract](references/adapter-contract.md), [state and action rules](references/state-and-actions.md), and [privacy/security/retention guide](references/privacy-security-retention.md) for the integration contract.
