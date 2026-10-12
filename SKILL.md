---
name: email-crm
description: Maintain a local, email-only CRM ledger in SQLite. Use for adding sourced email contacts, recording email lifecycle events, checking whether a contact is safe to email, and processing email suppressions or unsubscribes. This skill never discovers contacts or sends email.
license: MIT
metadata:
  openclaw:
    emoji: "✉️"
---

# Email CRM

Use this skill as a local decision and audit layer for email workflows. It stores only contacts, email events, and suppressions; it does not discover leads, enrich profiles, make calls, or send messages.

## 1. Choose the database

Pass `--db PATH` to every helper for an explicit database. If omitted, helpers use `EMAIL_CRM_DB`, then `data/email_crm.sqlite` relative to the current working directory. The default location is deliberately ignored by Git.

## 2. Initialize before use

```bash
python scripts/init_email_crm.py --db data/email_crm.sqlite
```

The command creates or migrates the schema and enables SQLite foreign keys for its connection. Confirm that it returns `schema_version: 1`.

## 3. Add or update a sourced contact

```bash
python scripts/upsert_contact.py \
  --db data/email_crm.sqlite \
  --email alice@example.com \
  --source "manual-review"
```

`--source` is required. The helper normalizes the email, upserts exactly one contact, and prints only its numeric ID.

## 4. Check readiness before an external sender acts

```bash
python scripts/check_email_readiness.py \
  --db data/email_crm.sqlite \
  --email alice@example.com
```

Treat `ready: false` as a hard stop. A caller must run this check immediately before queuing or sending email, then respect every returned reason code. This skill does not itself send email.

## 5. Record email lifecycle events

```bash
python scripts/log_email_event.py \
  --db data/email_crm.sqlite \
  --contact-id 1 \
  --event-type drafted
```

Allowed event types are `drafted`, `queued`, `sent`, `delivered`, `opened`, `replied`, `bounced`, and `failed`. Use `--metadata-json` only for non-sensitive operational metadata.

## 6. Process a manual DNC request or unsubscribe

```bash
python scripts/suppress_email.py \
  --db data/email_crm.sqlite \
  --email alice@example.com \
  --reason unsubscribe
```

Suppression is normalized, unique, idempotent, and also marks any matching contact as `do_not_contact`. Do not log raw email addresses in surrounding automation.

## Verification

Run `python -m unittest discover -s tests -v`. The tests use only temporary databases and `example.com` addresses.

See [the schema reference](references/schema.md) and [readiness rules](references/readiness-rules.md) for the stable integration contract.
