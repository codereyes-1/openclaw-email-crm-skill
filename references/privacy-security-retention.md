# Privacy, security, and retention

## Data minimization

- Use stable provider references, hashes, and short excerpts instead of full message bodies.
- Do not place credentials, tokens, attachments, raw headers, or sensitive content in metadata or action payloads.
- Use synthetic `example.com` fixtures in tests and demonstrations.
- Keep live databases, exports, logs, and backups outside source control.

## Security boundary

Database files and SQLite sidecars are owner-only (`0600`). The package has no network or transport dependency. A provider adapter is a separate, executable-code trust boundary: review it before installation, run it with least privilege and read-only provider scopes, retrieve credentials from an external secret store, and redact source references before logging. The core revalidates normalized records, rejects common secret/body metadata keys, limits metadata to 16 KiB, and stores the bundled synthetic input only as a content hash. These checks are defense in depth; they cannot make malicious adapter code safe.

## Retention

The default is no automatic deletion. This avoids silently destroying records under an invented universal policy, but it also means data is retained indefinitely until the operator configures and runs maintenance; that default is not a production retention policy. Before production use, define documented periods for excerpts, message metadata, proposal payloads, audit records, and backups, plus a review cadence and legal-hold process.

`purge_message_excerpts.py --before TIMESTAMP` reports eligible excerpts without changing data; add `--apply` only after reviewing the count. The cutoff must be a timezone-aware ISO-8601 timestamp and is normalized to UTC. The tool nulls excerpts while retaining hashes and source IDs. It does not delete message metadata, action payloads, audit records, or backups. Broader deletion should use a reviewed, referentially safe maintenance process tested against a backup.

## Operational controls

- Back up before schema migration.
- Run readiness immediately before any separate sender acts.
- Require a human approval boundary for proposals.
- Treat `transport_performed: false` as a design invariant, not permission for a caller to send.
