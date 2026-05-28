# SPR-09 — Write: connect-to-research, persisted prose-provenance (X-ray), highlight-rewrite, voice-to-draft, open-ended type

Status: decided (caffen/lr-spr09)
Date: 2026-05-28

This sprint extended the already-shipped Write surface. Most of Write was
built across Product-Depth SPR-07 + specs/write SPR-01..06. This note records
the three load-bearing decisions whose rationale must survive turnover.

## D-1 — The piece↔research link reuses the SHIPPED `deliverables.investigation_root_id`

The orchestrator default named the field `deliverables.investigation_id`. The
substrate already ships the same 1:1 link as **`investigation_root_id`**
(`substrate/graph/schema.py` deliverables table; `insert_deliverable(...,
investigation_root_id=...)` in `substrate/graph/ops.py`; surfaced on
`DeliverableSummary.investigation_root_id` in `interfaces/research/api/app.py`
and `apps/reading/src/lib/api.ts`). Adding a second `investigation_id` column
would be a duplicate link (a second source of truth for the same fact) — a
defect. **Decision: reuse `investigation_root_id`. No schema change for M1.**

- "Connect to a project": pass the chosen `investigation_root_id` to
  `createDeliverable` (already supported). The blocks of that investigation
  import onto the SPR-03 Canvas (imported, not re-implemented).
- "Connect to none": auto-spawn an investigation via `startInvestigation`,
  then create the deliverable with that id as `investigation_root_id`. The link
  is verified by reading it back (`getDeliverable` → the canvas loads from it),
  not by a UI assertion.

Reverses if: the operator decides a piece may connect to MANY research
projects (then `investigation_root_id` becomes a join table). Not today — the
operator chose 1:1 ("every writing piece auto-spawns A research folder").

## D-2 — `section.draft_generated` (SECTION_DRAFT_GENERATED), schema 22→23

`prose_provenance` (paragraph_index → [block_ids]) was EPHEMERAL: the
`creative_writer` role returns it, `generate_section` carries it in the
`CitationReport`, but `POST /write/sections/{id}/generate` discarded it. The
deliverable_sections table already has a `prose_provenance` column and
`update_section_prose(...)` already persists it — but nothing called it after a
live generation, and a direct UPDATE alone leaves no audit event.

**Decision: after a live generation succeeds AND the voice gate passes, persist
through the single-writer funnel:** in one `connect_write` context,
`update_section_prose(con, section_id, prose_text, prose_provenance)` (the
table) THEN `emit_typed(SECTION_DRAFT_GENERATED, ...)` (the audit event),
mirroring `patch_section_prose` (Sprint 15) which already pairs an
`update_section_prose` with an `emit_typed`. The event carries
`{section_id, deliverable_id, prose_provenance, paragraph_count, cited_block_ids,
all_claims_cited, unsupported_paragraph_count, gate_score}`.

The X-ray reads the persisted provenance back from `deliverable_sections`
(already on `SectionResponse.prose_provenance` via `getDeliverable`) and resolves
each block → chunk → document via `resolve_provenance` (SHIPPED). The LINK thus
EXISTS in the graph (a persisted event + a persisted row), not just on screen.

§16 / single-writer: `emit_typed` only APPENDS a JSONL event; the table write is
the existing `update_section_prose` through `connect_write` (`runtime/db_lock`,
--workers 1). No second writer. `creative_writer` runs via
`substrate.dispatch.router.dispatch` (Hermes) only — no new model host.

Reverses if: paragraph-level granularity changes (e.g. sentence-level
provenance) — then the payload's map key changes and the version bumps again.

## D-3 — FloatMenu rewrite actions are MODE-GATED, not a fork

M4 needs rewrite actions ("rewrite this / make it stronger / spin a sub-agent")
on the SHARED `modes/shared/FloatMenu/FloatMenu.tsx`. The roadmap forbids a
second FloatMenu. **Decision: extend FloatMenu with an optional
`rewriteActions` prop (default absent).** When the host (only Write) supplies it,
the menu shows the rewrite items; Read/Research/Speak hosts pass nothing and are
byte-for-byte unchanged in behavior. "Rewrite"/"make it stronger" regenerate the
paragraph the selection sits in via the SHIPPED generate path (per-block,
cited). "Spin a sub-agent" reuses the SHIPPED `onDeepResearch` spawn
(`startInvestigation`) and returns an accept/reject proposal — no new spawn path.

The §9.0 `outboundText()` chokepoint guards any text sent to a model (a withheld
selection is refused), reusing the shipped pattern.

Reverses if: rewrite needs its own provider/role distinct from creative_writer
— then a dedicated endpoint replaces the regenerate-the-paragraph reuse.

## Net-new, not merged (the operator's standing choice)

Write stays a distinct surface over the ONE graph. The auto-spawned research
folder (D-1) is the BRIDGE, not a merge: a piece always has a backing
investigation, but the writing canvas, outline, and X-ray are Write's own
lenses. Steelman of the merge + why it was rejected: see the handoff packet.
