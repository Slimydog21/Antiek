# Run ledger — Antiek Deep Research Hardening (ADRH)

Spec: `~/specs/antiek-deep-research-hardening/` (master + sprint-01..08 HTML)
Repo: `~/Desktop/Antiek` · branch `adrh/spr01-provider-contract` (forked from `main` @ `1c4d5df9`)
Orchestrator: main conversation (co-CEO, holds five-values bar)
Builder: single Claude subagent inline (spec hint: one owning package, serial milestones, fan-out unit = None for build)
Critic: `grok` headless (Composer 2.5-fast) — independent verifier lenses, read-only

## Ground truth (verified 2026-06-26)

- `canonical_verify.sh deep-research` → **CANONICAL_VERIFY_OK** (P-11..P-17, 22 tests). In-scope DRL loop shipped.
- `canonical_verify.sh html-transport` → **CANONICAL_VERIFY_OK** (P-18, 18 tests). HTML transport shipped.
- `tests/research/` does NOT exist. 0/13 named ADRH test files present. No `ResearchProvider`/Exa/Parallel adapters in live tree. → **ADRH genuinely unexecuted.**
- `substrate/contracts/reading_surface.py` is PROVISIONAL ("DRW SPR-10 not yet implemented"). → reading-side goal #2 gap.
- Baseline runner tests: **28 passed** (`tests/test_research_runner.py` + drw lock + parent terminal).

## Operator constraints honored

- Operator deferred Exa/Parallel live calls (recorded in DRL ledger, 2026-06-12). ADRH adapters land as conformance-tested stubs/fixtures; no live API keys, no `live`-marked tests run. Provider code is interface + fixture shape only.
- Harness guardrail: `grok` with `--permission-mode bypassPermissions --always-approve` is DENIED by the auto-classifier. Workhorse used read-only (critic) — construction is a Claude subagent inline.

## Sprint progress

### SPR-01 — ResearchProvider interface & normalized contract (Wave 1)

| Milestone | Deliverable | Proof | Status |
|---|---|---|---|
| M1 | Locate runner + Exa client; document seam | below | done |
| M2 | Normalized result type | research/providers/types.py | pending |
| M3 | ResearchProvider interface | research/providers/base.py | pending |
| M4 | Conformance harness (+ negative) | tests/research/test_conformance.py | pending |
| M5 | One-owner CI lint | tests/research/test_one_owner_lint.py | pending |
| M6 | Stub + runner-seam test | tests/research/test_runner_seam.py | pending |
| Critic | grok 3-lens adversarial pass | verdicts below | pending |
| Gates | 4 verify gates + handoff packet | this file + commit | pending |

Critic rounds: floor=1 cap=4. Lenses: leak / rubber-stamp / smuggled-precision.

## M1 seam findings (verified path:line, 2026-06-26)

**Runner (SOLE OWNER, host-local):** `runtime/research_runner/host_local.py`
- Calls Exa directly via lazy import at `:564`: `from acquisition.search.exa import discover, promote_discovery` inside `make_exa_gather_loop` (`:525`). This is the **INV-1/INV-4 violation hardening fixes** — the runner reaches into a concrete provider and branches on `gather_mode="exa"`.
- Protocol at `runtime/research_runner/protocol.py` (205 lines); re-exported at `substrate/contracts/research_runner.py`. Unit of work = `investigation_id`; runner owns start/stream/steer/status/cost/cancel; step logic injected as `BrowseLoop`.
- Demo stub loop `:447`; contract-gather stub `:480`; exa gather loop `:521` (env-gated `ANTIEK_DRW_GATHER=exa`).

**Existing Exa client (reuse, don't duplicate):** `acquisition/search/exa/`
- `client.py` — typed `ExaClient` (httpx, `MockTransport` for tests, retry 429/5xx ×3, `EXA_API_KEY`, `EXA_BASE_URL`). Returns typed records only; emits no events, touches no graph.
- `adapter.py:73` `DiscoveryProposed` (frozen dataclass), `:108` `DiscoveryPromotionResult`, `:123` `DiscoveryBudgetExceeded`. `discover(...)` at `:187` returns `list[DiscoveryProposed]`.
- `budget.py` — daily spend cap `check_and_reserve`. `cache.py`, `lookup.py`.
- **Current pre-hardening return shape = DISPOSAL, not ANSWER:** `discover` yields `DiscoveryProposed` (URL + decision accept/reject/redirect) for promotion into the graph. It does NOT return structured fields + per-field citations + confidence answering a sub-question. The normalized `ResearchResult` type is the deliberate improvement: provider contract shifts from "here are sources" → "here is a grounded answer."

**Existing provider abstraction?** None for research. `substrate/dispatch/base.py` is LLM dispatch (different concern). → New `research/providers/` package is justified (reuse-before-invent passes).
