# Adapter contract

Provider adapters implement `MessageAdapter.iter_messages()` and yield `NormalizedMessageRecord` values. The contract is deliberately pull-only: an adapter may read a provider, archive, export, or fixture, but must not mutate, mark read, delete, draft, or send.

Required fields are provider/account message identity, conversation identity, event timestamp, and direction. Optional fields are normalized addresses, subject, RFC Message-ID, excerpt, content hash, and non-sensitive metadata.

Treat every adapter as an untrusted integration boundary even when it is maintained by the same operator. The core validates records again before persistence: identifiers must be non-empty and bounded, timestamps must include a timezone and are canonicalized to UTC, addresses and directions fail closed, and metadata must be a JSON object no larger than 16 KiB. Credential, token, raw-body, body, HTML, and attachment metadata keys are rejected recursively. Adapter code still executes with the caller's process permissions, so install and run only reviewed adapters in a least-privilege environment.

Core guarantees:

- `(provider, account_ref, external_id)` is idempotent.
- Reusing that identity with different normalized content or a different conversation fails the entire ingestion transaction.
- Provider secrets are not accepted or persisted by the ingestion CLI.
- Synthetic inputs are persisted only as a SHA-256 content reference, never as a plaintext local path.
- Direction outside `inbound`, `outbound`, `internal`, or `unknown` fails closed.
- Addresses are validated and normalized before storage.
- Aware ISO-8601 timestamps are converted to UTC before storage so ordering and retention comparisons are deterministic.
- Excerpts are capped at 500 characters; full message bodies and attachments are not stored.
- Classification is rerun only for conversations touched by the ingestion batch.

The bundled synthetic adapter is the executable reference implementation. A real provider adapter should live in a separate integration package and translate provider records into this contract. It must use read-only provider scopes, fetch credentials from an external secret store, avoid logging source records, and be tested to prove that iteration does not acknowledge, label, mark read, draft, delete, or send.
