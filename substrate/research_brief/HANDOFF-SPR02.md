## Sprint SPR-02 — Handoff

### Status
DONE

Rework round complete: the independent reviewer demonstrated three forgeable approval
paths in the original implementation. Both mandatory major findings and all four
cheap minor findings are now addressed and covered by regression tests.

### Files touched
- `substrate/research_brief/model.py` — validated immutable brief, budget placeholder, and structurally consistent lifecycle event trails.
- `substrate/research_brief/project_html.py` — standalone editable HTML projection and draft-only round-trip parser; HTML edits cannot set lifecycle state.
- `substrate/research_brief/clarifier.py` — injected 2–3-question generator contract and answer fold.
- `substrate/research_brief/lifecycle.py` — injected transitions and approval gate requiring a final approval event pinned to current content.
- `substrate/research_brief/provenance.py` — stable content-only canonical hash and local linked run record.
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
- pytest: pass — `16 passed in 0.25s`.
- mypy strict: pass — `Success: no issues found in 6 source files`.
- ruff: pass — `All checks passed!`.
- seam purity: pass — the exact command emitted only Git's aggregate `9 files changed, 495 insertions(+)` footer; no outside-owned file path was emitted. A path-only structural check was also empty.

### WIRING.md entries added (frozen-file needs documented, not edited)
- `substrate/engagement_spine/spawn.py:83` → mint/approve brief before a reserved highlight spawn becomes runnable.
- `substrate/midnight_oil/product_path.py:106,365` → copy approved ceiling into unattended brief and require its token at run.
- `apps/reading/src/modes/ResearchWorkstation/StartResearch.tsx:160` → revise/approve projected brief before non-trivial submit.

### Decisions made mid-flight
- Decision: reject clarifier outputs outside 2–3, rather than clamp; silent truncation could discard the operator's material question.
- Decision: `deep`, `wrestle`, fan-out, and unattended runs are non-trivial; one-shot non-fan-out `fast` answers may skip the gate to preserve quick-answer latency. W0 evidence would reverse it.
- Decision: use a local `BudgetTuple` and `BriefRunRecord`; SPR-01 has not landed an importable type on this branch.
- Rework decision: editable HTML owns content only and must remain draft; approval remains an explicit lifecycle operation.
- Rework decision: approval events pin the content-only SHA-256 digest. State and events are excluded so HTML round trips reconstruct the same identity, while post-approval content replacement invalidates authorization.
- Rework decision: `RunToken` validates digest shape, but remains a reference whose authorization is meaningful only when verified against the approved brief.

### Rework red proofs
- Tampering projected HTML from `data-state="draft"` to `approved` is rejected before a brief can be parsed.
- Direct construction/replacement into `APPROVED` without an event trail is rejected.
- Token minting rejects approved content that no longer matches the final approval event's pinned hash.
- Approved briefs cannot transition again, and malformed token hashes are rejected.

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
