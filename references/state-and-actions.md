# State, obligations, and actions

## Deterministic state precedence

1. A manual override wins with confidence `1.0` and explicit reason evidence.
2. An open obligation owned by `me` yields `awaiting_me` (`0.98`).
3. An open obligation owned by `them` or `third_party` yields `awaiting_them` (`0.96`).
4. No messages yields `new` (`1.0`).
5. Latest inbound yields `awaiting_me` (`0.90`).
6. Latest outbound yields `awaiting_them` (`0.85`).
7. Internal or unknown latest direction yields `needs_review` (`0.35`).

The stored evidence identifies the deciding message or obligation. Clearing a manual override recomputes state from current facts.

## Action lifecycle

`proposed -> approved -> reconciled` or `proposed -> rejected`. Reconciliation is intentionally a local no-op and writes `reconciled_noop`; it never sends or calls a provider. A repeated identical proposal or reconciliation returns the prior result without duplicating audit effects. Reusing an idempotency key with different content fails closed.
