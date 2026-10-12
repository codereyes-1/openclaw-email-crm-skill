# OpenClaw Email CRM Skill

A small, local SQLite CRM core for email workflows. It records sourced contacts, email lifecycle events, and email suppressions without binding to a sender, lead provider, or enrichment service.

## What it does

- Stores normalized email contacts with an accountable source.
- Records neutral email lifecycle events.
- Provides a deterministic readiness check before an external sender queues or sends mail.
- Makes unsubscribe and manual do-not-contact requests idempotent.

## What it does not do

- Discover, enrich, scrape, or import leads.
- Send email or provide legal advice.
- Store phone, address, call, website, recording, or transcript data.

## Quick start

```bash
python scripts/init_email_crm.py --db data/email_crm.sqlite
python scripts/upsert_contact.py --db data/email_crm.sqlite --email alice@example.com --source manual-review
python scripts/check_email_readiness.py --db data/email_crm.sqlite --email alice@example.com
```

Run the test suite with:

```bash
python -m unittest discover -s tests -v
```

## Data handling

This package deliberately ships with no database, exports, logs, or real contact fixtures. Keep runtime databases and backups out of source control. The `.gitignore` covers common SQLite, export, environment, and log artifacts.

Before using an external email sender, configure and satisfy the legal, consent, and policy requirements that apply to your jurisdiction and provider. The readiness result is a technical gate, not a compliance certification.

## License

MIT. See [LICENSE](LICENSE).
