# Privacy, security, and retention

## Data minimization

- Use stable provider references, hashes, and short excerpts instead of full message bodies.
- Do not place credentials, tokens, attachments, raw headers, or sensitive content in metadata or action payloads.
- Use synthetic `example.com` fixtures in tests and demonstrations.
- Keep live databases, exports, logs, and backups outside source control.

## Security boundary

Database files and SQLite sidecars are owner-only (`0600`). The package has no network or transport dependency. A provider adapter is a separate trust boundary and must be read-only, retrieve credentials from an external secret store, and redact source references before logging.

## Retention

This candidate does not auto-delete records because retention policy is operator- and jurisdiction-specific. Before production use, define retention periods for excerpts, message metadata, audit records, and backups. `purge_message_excerpts.py --before TIMESTAMP` reports eligible excerpts without changing data; add `--apply` after review to null those excerpts while retaining hashes and source IDs. Broader deletion should use a reviewed, referentially safe maintenance process tested against a backup.

## Operational controls

- Back up before schema migration.
- Run readiness immediately before any separate sender acts.
- Require a human approval boundary for proposals.
- Treat `transport_performed: false` as a design invariant, not permission for a caller to send.
