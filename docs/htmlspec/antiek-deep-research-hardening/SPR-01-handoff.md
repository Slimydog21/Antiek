## Sprint SPR-01 — Handoff

### Status
done (grok co-CEO review pending — see Open questions)

### Files touched
- `research/__init__.py` (new) — top-level package marker for the provider contract.
- `research/providers/types.py` (new) — `ResearchResult` frozen dataclass + `Source`, `RawRef`, `CostModel`. Provider-agnostic; INV-1/INV-4 stated verbatim; confidence normalization rule documented as UNVERIFIED ASSUMPTION; `raw_ref` opaque by construction.
- `research/providers/base.py` (new) — `ResearchProvider` Protocol (`runtime_checkable`) + `OutputSchema`. Capability metadata (`provider_id`, `supports_async`, `tiers`, `cost_model`). No SDK import, no provider name in a conditional, INV-1/INV-4 verbatim.
- `research/providers/conformance.py` (new) — provider-parameterized harness; `ConformanceError` names the violated invariant; negative `BrokenStub` case.
- `research/providers/stub.py` (new) — `StubResearchProvider` (in-memory, deterministic) passing the harness.
- `tests/research/test_conformance.py` — conformance positive + negative (already tracked; verified green).
- `tests/research/test_one_owner_lint.py` — ast-based one-owner lint (already tracked; verified green; allowlists the documented `host_local.py:564` pre-existing exa import).
- `tests/research/test_runner_seam.py` — runner calls stub via interface; runner path asserts no provider name (already tracked; verified green).
- `runtime/research_runner/host_local.py` (+ `__init__.py`) — additive `make_provider_gather_loop` seam; existing `make_exa_gather_loop` untouched (out of scope).
- `.gitignore` — un-ignored `research/providers/` + `research/__init__.py` (the `/research/` top-level dir is otherwise the operator's local-artifacts scratch dir; the provider contract is source code and must be tracked).

### Milestones
- [x] M1: Locate runner + Exa client — `runtime/research_runner/host_local.py` (SOLE OWNER); Exa client at `acquisition/search/exa/`; current return shape = DISPOSAL (`DiscoveryProposed`), not ANSWER — the normalized `ResearchResult` is the deliberate improvement.
- [x] M2: Normalized result type — confidence mapping rule: Exa high→0.9 / medium→0.6 / low→0.3 / unknown→0.3; Parallel pass-through clamped [0,1]; flagged UNVERIFIED ASSUMPTION.
- [x] M3: ResearchProvider interface — capability fields: `provider_id`, `supports_async`, `tiers`, `cost_model`.
- [x] M4: Conformance harness (+ negative test) — `BrokenStub` missing citations / out-of-range confidence / unpopulated cost; harness raises `ConformanceError` naming the invariant.
- [x] M5: One-owner CI lint — ast-walks repo; fails if a module outside `research/providers/` (and outside `acquisition/search/exa/`, the existing client owner) imports the exa SDK; allowlists the documented `host_local.py:564` pre-existing violation; proven to fire via scratch file (then removed).
- [x] M6: Stub + runner-seam test — additive `make_provider_gather_loop` seam in `host_local.py`; runner calls stub via interface; test asserts the new runner code path contains no provider name. Existing exa gather loop untouched.

### Verification gate results
- Conformance positive/negative: **pass** (negative raises `ConformanceError` naming invariant; positive green).
- One-owner lint: **pass** (ast-based; fires on misplaced import, green after scratch removed).
- Runner seam: **pass** (runner calls stub via interface; no provider name in new path).
- No regressions: **47 passed** (19 research + 28 regression; baseline 28 preserved).
- Adversarial verify (workflow `wf_37eaa7e8-662`, 4 lenses): **leak** CLEAN (1 minor doc defect — INV-1/INV-4 verbatim added to `types.py` — FIXED); **smuggled-precision** CLEAN (mapping documented + flagged + range-checked); **rubber-stamp** CLEAN (negative genuinely fails-and-names-invariant; agent adversarially confirmed repo stayed clean); **grok-co-CEO** PENDING (see Open questions).

### Decisions made mid-flight
- frozen-dataclass (not Pydantic) for `ResearchResult` — matches the Exa adapter idiom (`DiscoveryProposed`) and `runtime/research_runner/protocol.py` dataclasses; keeps the provider contract dependency-light.
- `raw_ref` is an opaque `RawRef{handle, provider}` (not `dict[str, Any]`) — prevents an adapter smuggling raw payload a caller could branch on (INV-4).
- `Protocol` + `runtime_checkable` (not `abc.ABC`) — matches `substrate/contracts/reading_surface.py` and the `ResearchRunner` declaration; structural typing keeps adapters decoupled.
- `.gitignore` negation (`/research/*` + `!/research/providers/` + `!/research/__init__.py`) — `/research/` is otherwise the operator's local-artifacts dir; the provider contract is source code and must be tracked. This was a latent defect in the prior half-committed attempt (tests tracked, source gitignored).

### Assumptions surfaced (rigor #1)
- Exa categorical confidence "high"/"medium"/"low" mapped to 0.9/0.6/0.3 — UNVERIFIED. Anchors are engineering guesses, not measured equivalents of Parallel's calibrated score. Would reverse if Exa publishes a calibration curve or the router needs provider-specific thresholds.

### Steelman of rejected alternative (rigor #2)
- Duck-typed dict contract (no formal interface; each adapter returns a dict the runner reads). Steelman: less ceremony, faster to add a third provider. Why it lost: INV-4 forbids the runner branching on raw payloads, and the router needs typed capability metadata to choose provider/tier without importing adapters — a dict provides neither. A formal `Protocol` is the minimum that satisfies both.

### Open questions discovered
- **grok co-CEO review COMPLETE** (Composer 2.5, source-free prose sketch — the harness data-exfiltration guardrail correctly denies piping source files to Grok, so the review used a design description with no file contents crossing the trust boundary). Verdict: **DEFECTS** — 2 blockers + 4 major + 4 minor. The review found a real defect all 4 Claude lenses missed (D4: nested mutability — `@dataclass(frozen=True)` does not freeze nested dicts/lists; a caller could mutate citations post-return and break INV-4). **D4 FIXED** (commit `5fe7f662`: `fields`/`field_citations` typed as `Mapping`, `__post_init__` freezes to `MappingProxyType`/`tuple`, immutability red test added). D1 (allowlist — intentional transitional debt, SPR-03 removes), D2 (confidence_kind metadata — SPR-07 router scope), D5/D6 (router/resilience metadata — SPR-05/06/07 scope) judged out-of-SPR-01-scope by orchestrator. D3 (generic lint rule for all engines, not just Exa) and D8 (unknown confidence aliased to low — undefended) noted for follow-up. Full verdict at `/tmp/grok-spr01-verdict.txt`.
- Task-class taxonomy (SPR-02 M3) is DRAFT pending operator ratification — does the operator want `structured_extract`/`broad_gather`/`needle_in_haystack`/`multi_hop`/`unclassified`, or a different cut?

## Grok co-CEO review — defect disposition (2026-06-27)

| # | Severity | Defect (Composer 2.5) | Disposition |
|---|----------|----------------------|-------------|
| D1 | blocker | INV-1 not held while runner allowlist exists | **Out of scope (transitional).** The allowlisted `host_local.py:564` exa import is the documented pre-existing violation SPR-01 explicitly defers to SPR-03 (the real adapter wires behind the interface and removes it). Intentional transitional debt, not a violation. |
| D2 | blocker | Cross-provider confidence treated as comparable float without semantics | **Out of scope (SPR-07).** The design documented the mapping as an UNVERIFIED ASSUMPTION; encoding `confidence_kind` in capability metadata is the router's (SPR-07) job. The assumption is surfaced, not hidden. |
| D3 | major | Lint only covers Exa, not Parallel/symmetric | **Noted for follow-up.** Parallel SDK doesn't exist yet (operator deferred live calls). The lint rule should be generic (any engine SDK) when Parallel lands. |
| D4 | major | Frozen result still mutable nested dicts | **FIXED** (`5fe7f662`). `fields`/`field_citations` → `Mapping`/`tuple`, frozen in `__post_init__`, immutability red test added. |
| D5 | major | Router metadata too thin for accuracy/$ | **Out of scope (SPR-07).** SPR-01 is the contract; the router enriches metadata (p50/p95 latency, cost bands, rate limits, schema limits) in its own sprint. |
| D6 | major | answer() vs async engine semantics underspecified | **Out of scope (SPR-05/06).** Resilience/async/poll-loop is the resilience sprint's job; the interface defines the call, it does not wrap it. |
| D7 | minor | tier strings provider-native | Noted — normalize to internal tier enum in SPR-07 metadata. |
| D8 | minor | unknown Exa confidence → 0.3 aliases to low | **Noted for follow-up.** Undefended choice; should use a distinct sentinel. |
| D9 | minor | Conformance round-trip vague | Noted — spec `adapter.resolve_raw(raw_ref)` in SPR-03. |
| D10 | minor | No INV-4 control-flow guard | Noted — style test that runner doesn't branch on `result.provider` (beyond logging) in a follow-up. |

### Next sprint can start when
- SPR-02 (trajectory/measurement schema) can begin: interface + conformance harness exported and importable from `research.providers` — DONE. SPR-02 builds the measurement event that records the normalized `ResearchResult` (M1 already verified: `EVENT_SCHEMA_VERSION = 27` at `substrate/schemas/events.py:711`, bumps to v28).
- SPR-03/04 (Exa/Parallel adapters) can begin once the operator un-defers live provider calls (currently deferred per DRL ledger 2026-06-12); adapters will implement `ResearchProvider` and pass the conformance harness.

### Out-of-scope temptations encountered
- Wanted to wire the real Exa adapter behind the interface; instead built only the stub (SPR-03's job).
- Wanted to remove the existing `make_exa_gather_loop` in `host_local.py`; instead left it untouched (additive seam only — the existing exa import at `:564` is the allowlisted pre-existing violation a later sprint removes).
- Wanted to add retry/timeout/budget; instead left the interface unwrapped (SPR-05/06).
