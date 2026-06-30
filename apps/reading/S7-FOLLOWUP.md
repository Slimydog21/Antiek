# S7 follow-up · TipTap notebook editor

**Status:** S7-full is now landed on `reader/integration`. The current tree has
the TipTap editor, Antiek block extensions, slash menu, substrate notebook
endpoints, autosave, local offline mirror, and the cross-mode workspace entry
point.

## What is live

Per `docs/ui_redesign_posthog/sprint_07_notebook.html`:

| Work package | Current evidence |
|---|---|
| WP-7.1 — substrate `notebooks` table + REST endpoints | `substrate/notebooks/`, `/notebooks`, `/notebooks/{id}/blocks`, `/notebooks/{id}/content`, `/notebooks/by-doc/{document_id}/save` in `interfaces/research/api/app.py` |
| WP-7.2 — TipTap install | `apps/reading/package.json` + `src/modes/Notebook/Editor.tsx` |
| WP-7.3 — Antiek block extensions | `src/modes/Notebook/blocks/` covers note, claim-card, region-embed, question-card, cross-doc-link, chat-exchange, master-section, image, and latex |
| WP-7.4 — slash-command block menu | `src/modes/Notebook/SlashMenu.tsx` wired from `NotebookEditor` |
| WP-7.5 — Notebook surface + index route | `/notebooks`, `/notebook/:notebookId`, `NotebookCanvas`, `EditorPanel`, and stories |
| WP-7.6 — autosave + conflict signal | `NotebookEditor` saves via `PUT /notebooks/{id}/content`, mirrors locally, and surfaces offline/conflict states |
| WP-7.7 — cross-mode entry point | `openNotebook` and `PanelKind = "NotebookEditor"` open the editor as a workspace panel |

## Remaining follow-ups

- Add individual Storybook stories for each custom block under
  `Notebook / Blocks / *` if visual regression coverage needs per-block
  baselines beyond `NotebookEditor / WithSampleContent`.
- Replace any remaining local-only "add to notebook" affordances with explicit
  editor-open flows or backend-backed append flows only when undo semantics are
  proven. The current AI sidecar path intentionally updates the editor mirror
  and relies on the editor's canonical full-document autosave when it is open.
- Update broader roadmap/status pages only when they still cite this file as a
  live deferral.

## Cross-references

- Spec: `docs/ui_redesign_posthog/sprint_07_notebook.html`
- Notebook editor: `apps/reading/src/modes/Notebook/Editor.tsx`
- Notebook substrate: `substrate/notebooks/`
- API routes: `interfaces/research/api/app.py`
