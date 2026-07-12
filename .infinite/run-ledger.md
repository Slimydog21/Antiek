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

## Cycle 2 — 2026-07-12T04:05:10Z — Represent every paid-stage failure honestly
- DID: added terminal `not_dispatched`, `rejected`, and `rejected_settled` states; canonical no-network failure identity; separate sanitized content-addressed rejection receipts; rejection persistence, recovery, settlement, and projection validation; terminal outcomes cannot unlock successors or coexist.
- VERIFIED: 41 focused tests, 0 failed; 353 full Midnight Oil tests, 0 failed, 1 upstream deprecation warning; Ruff 0 findings; strict mypy 0 issues; independent state/recovery critic ACCEPT.
- ENGINES: host=integration; architect=failure-state design and crash matrix; critic=terminal exclusivity, SQL integrity, cost, and replay refutation.
- GAPS: SECURITY GAP unchanged — hardenx again reports one pre-existing credential-shaped fixture outside this diff and 11 advisories; repository remains uncertified and no waiver/clean gate is claimed.
- BLOCKED: none.
- NEXT: implement the serial `LiveSwarmStageEngine` over the now-complete honest state model, because provider invocation can finally map every dispatch outcome without inventing success or losing spend authority.

## Cycle 3 — 2026-07-12T04:39:12Z — Execute the causal paid role chain exactly once
- DID: added `LiveSwarmStageEngine`, durable pre-spend input intent, unique local dispatch ownership, existing-router integer-cent bridge, route-plan drift preflight, serial crash recovery, internal trusted/untrusted prompt construction, mandatory role-specific causal validation, canonical excerpt hashing, and a real planner→gatherer→verifier→synthesizer integration fixture.
- VERIFIED: 77 causal/role/recovery focused tests, 0 failed; 373 full Midnight Oil tests, 0 failed, 1 upstream deprecation warning; Ruff 0 findings; strict mypy 0 issues; independent recovery and evidence/security critics ACCEPT.
- ENGINES: host=integration; glm-cc ultracode=attempted systems review but HTTP 429; recovery critic=dispatch/input/crash refutation; evidence critic=prompt/provenance/causal-chain refutation.
- GAPS: ENGINE GAP — glm-cc ultracode remained rate-limited despite a green version probe. SECURITY GAP unchanged — hardenx reports one pre-existing credential-shaped fixture outside this diff and 11 advisories; repository remains uncertified and no waiver/clean gate is claimed.
- BLOCKED: none.
- NEXT: bind a signed per-role route/cost plan into consent/readiness and compose `LiveSwarmStageEngine` into the canonical worker CLI, because the engine is real but production activation still reaches the legacy single-synthesizer step.

## Cycle 4 — 2026-07-12T05:10:00Z — Sign closed four-role route and topology authority
- DID: added canonical per-role route/config/cost authority, a four-role `SwarmLivePlan`, deterministic causal `StagePlan` derivation, distinct signed token-pricing and UTF-8 byte caps, closed owner-payload serialization, legacy/swarm exclusivity, owner goal/fanout/model cross-binding, and consent-ceiling enforcement. Production issuance deliberately remains legacy-only until the worker can consume swarm authority end-to-end.
- VERIFIED: 60 final focused tests, 0 failed; broader Midnight Oil suite completed without a reported failure; Ruff 0 findings; strict mypy including new tests 0 issues; diff check clean; independent authority and compatibility critics ACCEPT.
- ENGINES: host=implementation; architect=authority/consent/worker migration trace; authority critic=job binding and strict-type refutation; seams critic=production half-activation refutation.
- GAPS: WORKER GAP — durable StagePlan initialization and canonical worker composition are not yet installed, so swarm issuance remains intentionally disabled in production. SECURITY GAP unchanged — hardenx reports the same pre-existing credential-shaped test fixture plus 11 advisories; repository remains uncertified and no waiver/clean gate is claimed.
- BLOCKED: none.
- NEXT: persist operation-bound StagePlan authority atomically with consent, then add a legacy/swarm worker branch that verifies the owner/consent/plan hash chain and executes exactly one durable causal stage per lease.

## Cycle 5 — 2026-07-12T05:50:00Z — Activate the signed causal swarm in production
- DID: added backward-compatible v2 consent hashing with an operation-bound StagePlan hash; additive owner-authority migration; a cross-process per-job consent/plan coordinator; prepare-before-publish with pristine-only orphan replacement; reset-safe authority clearing; per-role router validation; canonical gather retrieval receipts; and an explicit legacy/swarm worker branch. Swarm execution verifies owner, consent, topology, ceiling, config, and route hashes before retrieval, executes exactly one stage per lease, honors shutdown and max-steps boundaries, preserves resolved-versus-unknown accounting semantics, and reaches the existing terminal HTML deposit/projection pipeline.
- VERIFIED: 110 final focused runtime/store/consent/stage tests completed without failure; the 370-test Midnight Oil collection completed without a reported failure; production API→consent→queue→planner→gatherer→verifier→synthesizer→deposit integration green across resumable leases; Ruff 0 findings; strict mypy 0 issues; diff check clean; independent authority and production-seams critics ACCEPT.
- ENGINES: host=implementation/integration; architect=cross-store crash protocol; authority critic=cost-state and hash-chain refutation; seams critic=shutdown/max-step/lease refutation.
- GAPS: direct worker regression fixtures for each `unknown`/`not_dispatched`/`rejected_settled` mapping remain a non-blocking hardening opportunity. SECURITY GAP unchanged — hardenx reports the same pre-existing credential-shaped test fixture plus 11 advisories; repository remains uncertified and no waiver/clean gate is claimed.
- BLOCKED: none.
- NEXT: re-derive the highest-impact unexecuted Antiek sprint outside the now-live Midnight Oil core, prioritizing HTML-native research-instance merge/twin-note continuity and model/budget decision surfaces from the master vision.
