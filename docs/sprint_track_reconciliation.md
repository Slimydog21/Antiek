# Sprint-track reconciliation — master-spec vs UI-redesign

**Status:** Authoritative as of 2026-05-22. Resolves the two-track tension
flagged in the 2026-05-22 audit. Both sprint sequences run against the
same codebase and need a single mental model.

## The problem

Antiek currently has two sprint sequences in flight:

1. **Master product spec** (`docs/master-product-spec.md` §14) sequences
   Sprints 11 → 22+ on **product** axes (research workstation, multimodal
   acquisition, voice notes, creation surface, IP attribution, publisher
   dashboard, multi-user pivot, etc.).
2. **UI redesign** (`docs/ui_redesign_posthog/`) sequences Sprints 0 → 12
   on **visual / interaction** axes (Werner brand, Lemon primitives,
   Storybook, panel layout, navigation, notebook editor, command palette,
   AI sidecar, workspace persistence, a11y, release plumbing).

These are not competing tracks. They are **orthogonal axes** on the same
codebase. The master spec is the product roadmap; the UI redesign is
the chrome+visual upgrade. Both can ship concurrently because they touch
mostly disjoint subsystems.

## The mapping

The UI redesign sprints land **alongside** master-spec sprints, not
inside them. Calendar alignment by approximate ship date:

| UI-redesign sprint | Lands in master-spec window | What it produced |
|---|---|---|
| S0 — foundations (tokens, palette) | Sprint 17 | `src/design/tokens.ts`, `tailwind.config.js`, Werner brand |
| S1 — Lemon primitives | Sprint 17 | `src/components/lemon/` — 10 primitives |
| S2 — Storybook + Lost-Pixel baseline | Sprint 17 (satisfies PostHog Wedge 1a) | `.storybook/`, regression baseline |
| S3 — panel layout shell | Sprint 17–18 | PanelLayout 3D window manager |
| S4 — navigation re-shell | Sprint 17–18 | AppShell + NavRail + Topbar + ProjectTree (replaces HeaderBar) |
| S5 — ResearchWorkstation on PanelLayout | Sprint 18 | First-mode port to PanelLayout |
| S6 — WrestleApp on PanelLayout | Sprint 18 | Heavy-embed stress test |
| S7-light — notebook panel integration | Sprint 18 | Routing + panel placement |
| S7-full — TipTap editor + 5 custom blocks | Sprint 18–19 | **Satisfies PostHog Wedge 2** notebook surface (linchpin) |
| S8-light — keyboard shortcuts | Sprint 19 | Palette + AI-sidecar wire-up |
| S8-full — CommandPalette workspace actions | Sprint 19 | **Satisfies PostHog Wedge 3** command palette |
| S9 — workspace persistence | Sprint 19 | Deep-linking + popout |
| S10-light — bulk visual sweep | Sprint 19–20 | stone-* → brand tokens across remaining modes |
| S10-full — wrap status doc | Sprint 20 | Opt-in route wraps; rollout policy |
| S11 — a11y + responsive | Sprint 20 | Reduced-motion guards |
| S12 — release plumbing | Sprint 20–21 | `VITE_ANTIEK_UI` flag + bundle budget |

## The substantive conflicts and their resolutions

### Conflict 1 — Master-spec §5.3 (yellow accent verdict reversal)

Master-spec §5.3 originally read: *"adopting a yellow accent would hurt the
product proposition."* The UI redesign commit `de52534` explicitly reverses
this with rationale: *"the new yellow is sharper + cooler than PostHog's,
and the serif feel survives in MasterMdViewer prose (Charter) rather than
the chrome."*

**Resolution:** §5.3 is **superseded**. The brand decision is sun-yellow
`#F5DF24` as the constant outline; serif Charter typography survives at
the prose level (MasterMdViewer, Notebook editor content area). When the
master spec is next revised, fold this in as §5.3.1 "Brand outline
reversal 2026-05-21".

### Conflict 2 — Notebook editor: TipTap state vs notebook_blocks substrate

UI-redesign S7-full shipped a TipTap editor at
`apps/reading/src/modes/Notebook/Editor.tsx` that originally autosaved to
localStorage. Master-spec §4.2 specifies `notebook_blocks` as the
substrate-of-truth with one row per block.

**Resolution (committed 2026-05-22):** the H7 stitch wires the TipTap
editor's autosave to `PUT /notebooks/{id}/content`, which decomposes the
TipTap ProseMirror JSON into `notebook_blocks` rows via
`substrate/notebooks/tiptap_codec.py`. Substrate-citation block IDs
(claim_id, document_id, etc.) populate the `ref_id` column; the
renderer's fetch-at-render-time path stays intact. localStorage remains
as offline-fallback only. The Wedge 2 linchpin is now genuinely
substrate-backed.

### Conflict 3 — Command palette: chrome vs substrate-aware

UI-redesign S8 shipped a CommandPalette. Master-spec PostHog Wedge 3
specifies a *substrate-event-aware* Cmd+K that updates within seconds of
new content landing in the graph.

**Resolution:** the existing palette IS substrate-aware in code (reads
from the workspace store which mirrors substrate state). The wedge
ratification has not been formally recorded; that's a docs gap, not a
code gap. The next sprint should add a Wedge 3 verdict doc at
`docs/decisions/posthog-wedge-3-verdict.md` confirming acceptance.

### Conflict 4 — AI sidecar: chrome vs undo-via-event-log

UI-redesign S8 wired AISidecar across surfaces. Master-spec PostHog Wedge 4
specifies UI-action capability *with undo via the event log*.

**Resolution:** scaffolded but not closed. Each AI-driven UI action must
emit a typed `ai.action.applied` event with sufficient payload to invert
the action. The undo button reads the most-recent `ai.action.applied`
and replays the inverse via the substrate. **This is task #13 on the
2026-05-22 task list and remains open.**

### Conflict 5 — Status dots on `docs/sprint-breakdown.html`

The sprint-breakdown HTML's status dots reflect the master-spec sprint
sequence. The UI-redesign sprints are not represented. **Future revision:**
add a "Parallel UI track" group to the breakdown nav with sprints 0–12,
linked to `docs/ui_redesign_posthog/sprint_NN_*.html`. Out of scope for
2026-05-22.

## What this implies for the audit

The 2026-05-22 audit's "Section E — two-track tension nobody named yet"
is resolved by this document. Future sprint planning should reference
this mapping when sequencing new work — UI-redesign sprints continue
through S12 (release plumbing) and then graduate to a steady-state
"visual hygiene" cadence; master-spec sprints continue 17 → 22+ on the
product axis with the gates from §14.3 intact.

## Single source of truth going forward

When master-spec and UI-redesign conflict in the future:

1. **Substrate-level commitments** (`architecture_notes.md`) — always win.
2. **Loop 3 unlock criteria** (`docs/loop_3_unlock_criteria.md`) — gate
   all training work regardless of either track's wishes.
3. **Master spec** — product vision + sprint sequencing.
4. **Voice & style discipline** (`strategy/voice-and-style-discipline.md`) —
   prose AND UI quality bar.
5. **Integration specs** — peer documents with their own verdicts.
6. **UI redesign track** — chrome + visual concerns. When master-spec and
   UI redesign conflict on a UI/visual decision, **UI redesign wins for
   visual presentation; master spec wins for behavior, naming, and
   substrate contracts.**
7. **Per-sprint specs** — execution detail for the active sprint.

This precedence extends the original §17.2 ordering by inserting the UI
redesign track at level 6.
