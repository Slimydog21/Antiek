# S7 follow-up · TipTap notebook editor

**Status:** the S7-light pass landed on main (visual sweep + panel-kind
verification + cross-mode workspace actions). The full S7 — TipTap block
editor + 9 Antiek block kinds + slash menu + autosave + conflict
detection — is **deferred** until the in-flight notebook track lands on
main.

## Why deferred

Three notebook commits exist on staging branches but not main:

  * `ec16682` — spr-08 m1-m4-m5-m8: per-doc notebook surface + tests + storybook
  * `ea62ada` — spr-09 m6-m7: AntiekPersistence default + SaveAs surface + e2e suite
  * `aa65aca` — spr-11 m1-m7: Tier-3 per-theme notebook + auto-suggest stub

Doing the spec's full TipTap rebuild on main now would create a hard
merge conflict whenever the notebook track merges. The honest move is
to ship the panel-system integration in S7-light and resume the full
build once the notebook track is on main.

## What's deferred

Per `docs/ui_redesign_posthog/sprint_07_notebook.html`:

  * WP-7.1 — substrate `notebooks` table + REST endpoints
  * WP-7.2 — TipTap install (`@tiptap/react @tiptap/starter-kit
    @tiptap/extension-placeholder`)
  * WP-7.3 — block extensions for: prose · heading · region-embed ·
    claim-card · note · question-card · cross-doc-link · chat-exchange ·
    master-section · image · latex
  * WP-7.4 — slash-command block menu (type `/` to insert)
  * WP-7.5 — full Notebook surface + index route polish
  * WP-7.6 — autosave (2 s idle) + conflict detection via etag
  * WP-7.7 — cross-mode "Add to notebook" CTAs from MasterMdViewer,
    PdfViewer, ClaimCard, NotesPanel

The cross-mode workspace action (`openNotebook` in
`src/workspace/actions.ts`) is the connect point — WP-7.7 will wire
CTAs across the legacy modes to it once the editor is real.

## What S7-light shipped on main

  * `src/modes/Notebook/{index,NotebookCanvas}.tsx` — token sweep
    (stone-* → ink/ice/sun + dark variants).
  * `src/modes/Notebook/Notebook.stories.tsx` — verifies the legacy
    notebook renders inside a panel frame.
  * `src/workspace/actions.ts` — `openNotebook` / `openPdfPanel` /
    `openClaimInspector` helpers for clean cross-mode CTAs once
    consumer surfaces opt in.
  * `src/api/notebooks/by-doc.ts` — stub already landed in S6 to keep
    the SPR-09 `SaveAs.tsx` import resolvable when that track merges.

## Resumption playbook

When the SPR-08/09/11 merges into main:

  1. `git merge` (or rebase) brings the TipTap surfaces + per-doc
     notebook + AntiekPersistence into the tree.
  2. Replace `src/api/notebooks/by-doc.ts` stub with the real client.
  3. Wire `openNotebook` (in `src/workspace/actions.ts`) to whatever
     new entry component the notebook track shipped.
  4. Add stories for each block kind under `Notebook / Blocks / *`
     (per the spec template).
  5. Add autosave + conflict (if not already handled by AntiekPersistence).
  6. Verify Lost-Pixel baselines for the new block-kind stories.
  7. Lift S7 to "fully shipped" in the master plan.

## Cross-references

  * Spec: `docs/ui_redesign_posthog/sprint_07_notebook.html`
  * Staging tracks (for the merge target): `wrestle-evolution/wave-2-spr08-staging`,
    `wrestle-evolution/wave-3-spr09-staging`
  * Brand: notebook prose remains in Charter serif (per
    `docs/ui_redesign_posthog/brand_werner.html` §8 — the reading
    feel survives inside the panel that renders prose).
