## Sprint SPR-02 — Handoff

### Status
DONE

### Files touched
- `substrate/research_brief/model.py` — validated immutable brief, budget placeholder, lifecycle event shapes.
- `substrate/research_brief/project_html.py` — standalone editable HTML projection and round-trip parser.
- `substrate/research_brief/clarifier.py` — injected 2–3-question generator contract and answer fold.
- `substrate/research_brief/lifecycle.py` — injected transitions and sole run-token approval gate.
- `substrate/research_brief/provenance.py` — canonical content hash and local linked run record.
- `substrate/research_brief/__init__.py` — public package API.
- `substrate/research_brief/WIRING.md` — exact frozen integration needs and triviality policy.
- `tests/test_research_brief.py` — red proofs and milestone contract tests.

### Milestones
- [x] M1: Brief model + HTML projection — complete, including required-field rejection and editable-field round trip.
- [x] M2: Clarifier contract — complete with injected stub coverage and explicit count rejection.
- [x] M3: Lifecycle + approval gate — complete; both mandated tests failed before the package existed, then passed.
- [x] M4: Provenance linkage — stable canonical hash and local SPR-01-compatible record seam complete.
- [x] M5: Tests + WIRING.md — complete.

### Verification gate results
- pytest: pass — `11 passed in 0.17s`.
- mypy strict: pass — `Success: no issues found in 6 source files`.
- ruff: pass — `All checks passed!` (initial import-order finding was repaired, then the exact gate passed).
- seam purity: pass — the exact command emitted only Git's aggregate `9 files changed, 495 insertions(+)` footer; no outside-owned file path was emitted. A path-only structural check was also empty.

### WIRING.md entries added (frozen-file needs documented, not edited)
- `substrate/engagement_spine/spawn.py:83` → mint/approve brief before a reserved highlight spawn becomes runnable.
- `substrate/midnight_oil/product_path.py:106,365` → copy approved ceiling into unattended brief and require its token at run.
- `apps/reading/src/modes/ResearchWorkstation/StartResearch.tsx:160` → revise/approve projected brief before non-trivial submit.

### Decisions made mid-flight
- Decision: reject clarifier outputs outside 2–3, rather than clamp; silent truncation could discard the operator's material question.
- Decision: `deep`, `wrestle`, fan-out, and unattended runs are non-trivial; one-shot non-fan-out `fast` answers may skip the gate to preserve quick-answer latency. W0 evidence would reverse it.
- Decision: use a local `BudgetTuple` and `BriefRunRecord`; SPR-01 has not landed an importable type on this branch.

### Assumptions surfaced (rigor #1)
- I-9's ≥65% blind preference bar is pending W0 and is not measured by this sprint.
- Injected `occurred_at` values are opaque event-log timestamps; validating a timestamp format belongs to the eventual shared event contract.

### Steelman of rejected alternative (rigor #2)
- Skipping briefs for fast answers is a coherent Perplexity-style choice: added approval latency can cost more user value than it saves. The chosen threshold therefore exempts only genuinely quick, one-shot, non-fan-out work and gates material scope/spend.

### Open questions discovered
- Which exact SPR-01 `TierBudget` and run-record types become authoritative after integration — campaign integration owner.
- How the UI/server transport carries `RunToken` without creating a second authorization path — StartResearch and API owners.

### Next sprint can start when
- The integration owner accepts the additive API and assigns the three frozen wiring changes; W0 remains responsible for the preference done-bar.
