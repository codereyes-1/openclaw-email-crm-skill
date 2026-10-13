# Adapter contract

Provider adapters implement `MessageAdapter.iter_messages()` and yield `NormalizedMessageRecord` values. The contract is deliberately pull-only: an adapter may read a provider, archive, export, or fixture, but must not mutate, mark read, delete, draft, or send.

Required fields are provider/account message identity, conversation identity, event timestamp, and direction. Optional fields are normalized addresses, subject, RFC Message-ID, excerpt, content hash, and non-sensitive metadata.

Core guarantees:

- `(provider, account_ref, external_id)` is idempotent.
- Provider secrets are not accepted or persisted by the ingestion CLI.
- Direction outside `inbound`, `outbound`, `internal`, or `unknown` fails closed.
- Addresses are validated and normalized before storage.
- Excerpts are capped at 500 characters; full message bodies and attachments are not stored.
- Classification is rerun only for conversations touched by the ingestion batch.

The bundled synthetic adapter is the executable reference implementation. A real provider adapter should live in a separate integration package and translate provider records into this contract.
