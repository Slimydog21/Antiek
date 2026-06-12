# Egghead₂ — execution review (ANT-DRL exec-1)

**Thesis under review:** Did exec-1 deliver PostHog-level substrate/engine/harness for deep research convergence, excluding Exa?

**Confidence:** moderate-high for *convergence contract*; low for *product perfection*.

## What survived scrutiny

- **Split-brain closed:** `DeepResearchComplete` on session parent; DRW-only paths fail P-12.
- **Typed bridge:** `SessionEvidencePack` with provenance validation; not raw StepEvent pipe.
- **Harness honesty:** P-11..P-15 + `canonical_verify deep-research`; regression fixture for gather-without-synthesis.
- **Prod honesty:** `make_contract_gather_stub` replaces `make_demo_loop` in factory.
- **Path A wired:** `build_evidence_pack` → `run_synthesis_tail_from_pack` (hermetic convergence test).

## Strongest remaining objection

Architecture closure ≠ research product. Stub gather produces thin/synthetic evidence; synthesis can pass phases 6–9 on placeholder `doc-gather-*` chunks. Gates prove **wiring**, not **quality under real evidence**.

## Residual gaps (in-scope, no Exa)

1. No HTTP profile: `POST launch` → background synthesis → parent `investigation.completed` in `canonical_verify`.
2. Pack bridge with `doc-url-*` from seeded `ingest_url` not E2E-tested through cascade HTTP.
3. Failure paths: partial leaves, budget exceeded, process restart + reconstruct + tail idempotency.
4. P-15 proves event emission, not economic compounding (documented honestly in benchmark README).

## Verdict

**Exec-1 meets the htmlspec for Waves 1–5** at engineering precision. **Does not meet "perfect research product experience"** — correctly deferred with operator Exa exclusion, but naming should say *convergence substrate complete*.