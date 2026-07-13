## Sprint SPR-07 — Handoff

### Status
COMPLETE

### Files touched
- `acquisition/oai_pmh/*`, `tests/test_oai_pmh.py` — paged OAI harvest, cache, durable cross-process Retry-After sentinel, and wiring note.
- `acquisition/openalex/*`, `tests/test_openalex.py` — cursor-paged cached works client and injected-clock per-second and daily ceilings.
- `acquisition/s2_enrich/*`, `tests/test_s2_enrich.py` — optional/authenticated-key batch enrichment, non-leaking representation, and five-minute budget.
- `acquisition/substack_feed/*`, `tests/test_substack_feed.py` — RSS/multi-page archive ingestion, persisted backoff, explicit paywall inaccessibility.

### Milestones
- [x] M1: OAI-PMH harvester (arXiv) — paging/cache and two-instance persisted-ban red-proof pass.
- [x] M2: OpenAlex client — cursor fixture/cache plus pre-HTTP per-second and daily ceiling red-proofs pass.
- [x] M3: S2 enrichment client — optional/authenticated-key behavior, secret non-disclosure, and request 101 refusal pass.
- [x] M4: Substack ingestion — feed, three-page archive offsets/aggregation, two-instance persisted-ban, and no-fallback paywall red-proofs pass.
- [x] M5: Shared test suite + WIRING.md — all four owned test files carry an autouse socket guard; owned tests and wiring complete.

### Verification gate results
- pytest ×4: pass — `9 passed in 0.32s`
- no-network proof: pass — autouse `socket_guard` present in all four owned test files (lines 13, 12, 10, and 12 respectively); included in the green pytest ×4 run.
- mypy strict: pass — `Success: no issues found in 9 source files`
- ruff: pass — four owned packages plus all four owned test files: `All checks passed!`
- diff hygiene: pass — `git diff --check` emitted no output.
- seam purity: pass by `git diff --name-only origin/campaign/research-reading-spine-2026-07-09-main`; committed changes are confined to the four acquisition packages and their four owned tests. This handoff is the only additional committed deliverable.

### WIRING.md entries added (frozen-file needs documented, not edited)
- `acquisition/arxiv` → acquisition owner should switch bulk discovery to OAI-PMH; retain governed point-fetch paths.
- SPR-06 corpus contract → adapt cached records with `fetched_at`; preserve Substack inaccessible state.

### Decisions made mid-flight
- Decision: treat both 429 and 503 as durable provider bans because OAI-PMH commonly communicates backoff with 503 and Retry-After; reverse if provider documentation withdraws that contract.
- Decision: keep fixtures hand-written and label them here; replace with sanitized recorded responses if an operator-approved capture becomes available.
- Decision: enforce OpenAlex's documented 100,000-request daily bound in addition to the conservative nine-request per-second ceiling. The day window is derived from Unix time and resets at UTC day boundaries; both ceilings refuse before HTTP.

### Assumptions surfaced (rigor #1)
- The 30-day zero-429 operational bar remains pending deployment; this sprint proves only mechanical refusal, paging, caching, and local ceilings.
- Substack publishes no numeric public API quota used here; Retry-After is authoritative.

### Steelman of rejected alternative (rigor #2)
- Keeping the existing poller is less code and its current implementation now has durable throttling. It remains the wrong bulk path because the original process-local design caused the May 2026 ban and arXiv designates OAI-PMH for bulk metadata harvesting.

### Open questions discovered
- Should the campaign repair the repository-wide `ruff ... tests/` baseline or narrow the sprint gate to owned tests? — campaign maintainer.

### Next sprint can start when
- The acquisition owner accepts the OAI switchover wiring and SPR-06 exposes its corpus adapter contract.

### Logical commits
- `edb1fe747` — OAI-PMH
- `2f4bb9ca1` — OpenAlex
- `be7d0ea33` — Semantic Scholar
- `44cbe4bfc` — Substack
- `d267bfe71` — review remediation: socket guards, paging/auth/ban red-proofs, and OpenAlex daily ceiling
- `docs(sprint): refresh SPR-07 handoff after rework` — this handoff update (local commit; no push)
