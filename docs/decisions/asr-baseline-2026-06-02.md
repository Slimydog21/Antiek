# ASR baseline decision — 2026-06-02

**Status:** Accepted (SR-00 ledger pin)  
**Baseline SHA:** `2b59fed130c700368f4736189b8c94af4d78050f` (`origin/main`)  
**Spec root:** `~/specs/antiek-substrate-reconciliation/`

## What landed on main before ASR

| item | SHA / PR | note |
|------|----------|------|
| Personal-Reading Lane | **PR #43** merged | `personal_reading` fourth rights state; search gate; ops deny-default; serve/attribution tests |
| Corpus-value kill-gate (P3) | **PR #42** merged @ `abde67e` | `tools/lint/source_gate.py` + `tools/source_census.py` wired in CI |
| Reframe P1 register chokepoint | **held local-only** | Branch `caffen/reframe-p1` — **not** on main; forward-incompatible without `personal_reading` in `VALID_CONTENT_CLASSES` |

## Open seams at baseline (byte-verified)

Documented in `docs/asr-traceability-matrix.md`:

- **`retrieval_substrate`**: RESTRICTED-only NOT IN @ `retrieval_substrate.py:443-445` — does not union `PERSONAL_ONLY_CONTENT_CLASSES` like `search.py:291-297`.
- **`get_chunk`**: RESTRICTED-only withhold @ `app.py:2207-2213` — NULL grandfather; no `personal_reading` withhold.
- **NULL OR**: `search.py:295` — legacy `content_class IS NULL OR …` until SR-06 backfill + SR-07 flip.
- **`source_gate`**: CI wired; live census (P3b) absent → gate exits 0 with no row (**PARTIAL** until SR-10).

## Reconciliation sequencing rule

**SR-01 through SR-03 must complete (`GATE-RETRIEVAL-LINT`) before SR-04 (P1 register reconcile).**

Rationale:

1. SR-01..03 touch the same retrieval predicate surface as post-#43 `search.py` (single emitter + lint + VSS/chunk alignment).
2. Merging held P1 (`caffen/reframe-p1`) before retrieval parity risks declaring §9.0 done while VSS/chunk still leak `personal_reading` (failure mode in `index.html`).
3. SR-04 explicitly requires `personal_reading ∈ VALID_CONTENT_CLASSES` and must rebase P1 onto post-#43 main — not ebfb36a / not as-is.

Forbidden parallel (from `grok-execution-brief.md`):

- **SR-04 ∥ SR-01** (same files / gate drift).
- **SR-07** without `GATE-BACKFILL-DONE`.
- **P1 merge** without vocabulary fix.

## Pillar ledger (reframe run)

Authoritative pillar status: `~/specs/antiek-arxiv-ingest/.caffenagent/reframe-run.json`

| pillar | status @ baseline |
|--------|-------------------|
| **P1** | Reviewable diff on `caffen/reframe-p1` — **held**, operator merge pending; reconcile in **SR-04** |
| **P3** | **MERGED** @ PR #42; CI live |
| **P2** | pending — **SR-06** / **SR-07** |
| **P4** | pending — **SR-09** |
| **P5** | pending — **SR-09** (depends P1 reconcile) |

Companion architecture: `~/specs/antiek-arxiv-ingest/ARCHITECTURE-corpus-reframe.md`

## SR-00 verification

| gate | command | result |
|------|---------|--------|
| GATE-BASELINE | `pytest tests/test_personal_reading_lane.py -q` | exit **0** (23 passed, SR-00 handoff) |
| GATE-MATRIX | `test -f docs/asr-traceability-matrix.md` | present |