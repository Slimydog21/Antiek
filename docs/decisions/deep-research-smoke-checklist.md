# Deep research smoke DRW #1 — operator checklist (SPR-DRL-09)

**Status:** Active  
**When:** After P-17 green and `ANTIEK_DRW_GATHER=parallel` on prod. Before sessions 2–10.

## Preconditions

- [ ] `./scripts/canonical_verify.sh deep-research` → `CANONICAL_VERIFY_OK` (P-11..P-17)
- [ ] `PARALLEL_API_KEY` set in operator `.env` (rotated if ever pasted in chat)
- [ ] `ANTIEK_DRW_GATHER=parallel`
- [ ] G2 counsel packet dispatched (parallel track — not blocked by this DRW)

## Launch

1. Approve plan on a **real** research question (not fixture text).
2. `POST /research/plans/{root_id}/launch`
3. Poll `GET /research/sessions/{session_id}` until `gather_complete: true`

## Falsifiers (session fails smoke if any unchecked)

### Parent terminal (not leaf terminal)

- [ ] Response includes `deep_research_complete: true` when product path succeeded
- [ ] `synthesis_tail_error` is **null** (if non-null → P0, do not run sessions 2–10)
- [ ] Session parent trajectory contains `investigation.completed` (not only leaf terminals)

### Pack fidelity

- [ ] `SessionEvidencePack` chunks use `doc-url-*` document ids (not only `doc-gather-*` placeholders)
- [ ] At least one ingested document with `promotion_decision=ingested` in leaf step provenance

### Synthesis quality (operator judgment)

- [ ] Operator grades synthesis: **accept** / **reject** + one-line why
- [ ] If reject: file `tests/regression/agent_failures/<slug>.yaml` before fix

## Record (spreadsheet or handoff table)

| Field | Value |
|-------|-------|
| session_id | |
| wall time | |
| parallel spend estimate | |
| # DiscoveryProposed | |
| # ingested doc-url-* | |
| pack chunk count | |
| deep_research_complete | |
| synthesis_tail_error | |
| operator grade | |

## Not proved (still operator-live after smoke)

- Parallel index blind spots on your query shapes
- SSE reconnect after session eviction
- Full HTTP TestClient cascade profile (deferred sprint)