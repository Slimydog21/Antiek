# Infinite run ledger

Append-only execution record. The active native goal predates this local ledger; cycle 1 begins at provider orchestration after accepted commit `4cd62e247`.

## Cycle 1 — 2026-07-12T03:51:37Z — Make paid stage effects honestly recoverable
- DID: added content-addressed integer actual cents to `StageEffectReceipt`; added verified durable effect/evidence recovery reads; bound job projection to the same verification; added a pre-dispatch checkpoint hook and atomic idempotent open→unknown keyed exposure transition.
- VERIFIED: 36 focused tests, 0 failed; Ruff 0 findings; strict mypy 0 findings; independent recovery critic ACCEPT. A full Midnight Oil run before the final read-path repair was 348 passed and is being rerun on final bytes.
- ENGINES: host=integration; architect=state-machine/crash audit; codex=read-only architecture sweep; grok=probe returned no substantive report; glm-cc ultracode=HTTP 429; critic=adversarial recovery review.
- GAPS: ENGINE GAP — glm-cc ultracode rate-limited (HTTP 429); ENGINE GAP — grok returned only an investigation preface. SECURITY GAP — hardenx reported one pre-existing credential-shaped fixture outside this diff plus 11 advisories; installed hardenx could not corpus-certify this repository, so no clean security claim or waiver is recorded.
- BLOCKED: none.
- NEXT: specify and implement honest `reserved→released` pre-dispatch failure and known-paid invalid-output states before provider orchestration, because the current five-state contract cannot represent either outcome without lying or stranding authority.

## Correction to Cycle 1 — 2026-07-12T03:53:00Z
- VERIFIED: the full Midnight Oil suite on the final accepted read-path bytes completed with 348 passed, 0 failed, and 1 upstream deprecation warning.
