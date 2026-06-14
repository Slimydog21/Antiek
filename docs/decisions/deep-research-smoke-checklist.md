# Deep research smoke DRW #1 — operator checklist (SPR-DRL-09)

**Status:** Active
**When:** After P-17 green and `ANTIEK_DRW_GATHER=exa` on prod. Before sessions 2–10.

This is the operator-live counterpart to the hermetic P-17 gate
(`tests/test_drw_parent_terminal.py`, run by
`./scripts/canonical_verify.sh deep-research`). The gate proves
parent-terminal observability *hermetically* (mocked, no network); this
checklist proves the **real** session-parent `DeepResearchComplete` on smoke
DRW #1 — the live-only delta the gate cannot reach.

## Preconditions

- [ ] `./scripts/canonical_verify.sh deep-research` → `CANONICAL_VERIFY_OK: deep-research` (P-11..P-17)
- [ ] `EXA_API_KEY` set in operator `.env` (rotated if ever pasted in chat)
- [ ] `ANTIEK_DRW_GATHER=exa` (the Exa Wedge-1 gather path; stub is hermetic-default, see `deep-research-exa-gather.md`)
- [ ] **G2 counsel packet dispatched (parallel track).** The Sprint 18 retrieval-time
      legal gate / publisher opt-in (`docs/operator_gate_actions.md`, §9.0) is the
      operator-bound G2 item. It runs as a **parallel track** to this smoke — counsel
      review proceeds independently and does **not** block launching smoke DRW #1.
      Exa-discovered URLs hit the retrieval-time gate exactly as manually-typed URLs do
      (`deep-research-exa-gather.md` scope note), so this smoke does not advance G2 and
      G2 does not gate this smoke. Confirm the packet is out before relying on smoke
      results for any payout-adjacent decision.

## Launch

1. Approve plan on a **real** research question (not fixture text).
2. `POST /research/plans/{root_id}/launch`
3. Poll `GET /research/sessions/{session_id}` until every research `state` is terminal
   (`all_terminal: true` on the recovery shape), then let background completion run the
   Loop 1 synthesis tail on the session parent.

## Falsifiers (session fails smoke if any unchecked)

### Parent terminal (not leaf terminal)

- [ ] `session_status` reports `deep_research_complete: true` when the product path
      succeeded (sourced from `CascadeSession.is_deep_research_complete()` —
      the **session-parent** postcondition, not a per-leaf `DONE`).
- [ ] `synthesis_tail_error` is **null** (`CascadeSession.synthesis_tail_error`;
      if non-null → P0, do not run sessions 2–10).
- [ ] Session **parent** trajectory contains **`investigation.completed`** — the
      single terminal spine on `session_id` (Path A, `deep-research-convergence-a.md`),
      not only the leaf terminals. This is the one falsifier that distinguishes a real
      `DeepResearchComplete` from a cascade that merely reached leaf `DONE` via the old
      `make_demo_loop` split-brain (`deep-research-terminal-contract.md`).

### Pack fidelity

- [ ] `SessionEvidencePack` chunks cite **`doc-url-*`** document ids (real ingested
      documents) — **not only `doc-gather-*` placeholders**. A pack built entirely from
      `doc-gather-*` ids means the gather loop never promoted a real source: synthesis
      ran on placeholder provenance, the chunk → document → `ip_holder` chain is
      vacuous, and the session must fail smoke.
- [ ] At least one ingested document with `promotion_decision=ingested` in leaf step
      provenance, carrying a `discovery_id → document_id` link (Exa Wedge-1 contract,
      `deep-research-exa-gather.md`).

### Synthesis quality (operator judgment)

- [ ] Operator grades synthesis: **accept** / **reject** + one-line why
- [ ] If reject: file `tests/regression/agent_failures/<slug>.yaml` before fix
      (per CLAUDE.md agent-failure regression library)

## Record (spreadsheet or handoff table)

| Field | Value |
|-------|-------|
| session_id | |
| wall time | |
| Exa spend estimate | |
| # DiscoveryProposed | |
| # ingested doc-url-* | |
| pack chunk count | |
| deep_research_complete | |
| synthesis_tail_error | |
| operator grade | |

## Not proved (still operator-live after smoke)

- Exa index blind spots on your query shapes
- Partial-ingest / budget-cap mid-stream raise (single leaf), and budget exhaustion
  under cascade concurrency (`deep-research-exa-gather.md` "Failure isolation")
- SSE reconnect after session eviction
- Full HTTP TestClient cascade profile (deferred sprint)
- **Audit durability window:** if the process is killed AFTER a completion failure
  is captured in memory but BEFORE the `cascade.synthesis_tail.failed` JSONL append
  flushes, the recovered (from-event-log) status shows `synthesis_tail_error: null`
  + `deep_research_complete: null` — indistinguishable from an in-flight session.
  Narrow window inherent to append-audit; still flagged by `all_terminal` + a
  missing parent `investigation.completed`. Verify both on a real restart.
