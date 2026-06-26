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
- **grok co-CEO review pending.** The goal explicitly names Grok/Composer 2.5 as co-CEO critic. Two blockers: (a) the harness classifier denies piping full source files to Grok (data-exfiltration — a correct guardrail); (b) a persistent classifier outage ("glm-5.2 temporarily unavailable") blocked even a source-free design-sketch review across multiple attempts. Resolution ready: run `grok --single` with a SOURCE-FREE prose sketch of the design (no file contents cross the trust boundary) once the classifier recovers. Three independent Claude lenses already CLEAN.
- Task-class taxonomy (SPR-02 M3) is DRAFT pending operator ratification — does the operator want `structured_extract`/`broad_gather`/`needle_in_haystack`/`multi_hop`/`unclassified`, or a different cut?

### Next sprint can start when
- SPR-02 (trajectory/measurement schema) can begin: interface + conformance harness exported and importable from `research.providers` — DONE. SPR-02 builds the measurement event that records the normalized `ResearchResult` (M1 already verified: `EVENT_SCHEMA_VERSION = 27` at `substrate/schemas/events.py:711`, bumps to v28).
- SPR-03/04 (Exa/Parallel adapters) can begin once the operator un-defers live provider calls (currently deferred per DRL ledger 2026-06-12); adapters will implement `ResearchProvider` and pass the conformance harness.

### Out-of-scope temptations encountered
- Wanted to wire the real Exa adapter behind the interface; instead built only the stub (SPR-03's job).
- Wanted to remove the existing `make_exa_gather_loop` in `host_local.py`; instead left it untouched (additive seam only — the existing exa import at `:564` is the allowlisted pre-existing violation a later sprint removes).
- Wanted to add retry/timeout/budget; instead left the interface unwrapped (SPR-05/06).
