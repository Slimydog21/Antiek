# Spec stub — Write mode lands draft_combined HTML (future residual fl+)

## Intent
North star: merged research drafts and written analysis open as HTML in the
reading flywheel; operators should also be able to **land** a draft_combined
HTML document into Write mode for human editing without PDF.

## Non-goals (this stub)
- Live LLM rewrite of drafts
- Auto-overwrite of parent assets
- PDF export as canonical view

## Proposed product residual
1. Write mode surface: "Open draft HTML as writing project" from
   hosted_html_document host or SpawnMergePanel result.
2. Import HTML body into Write outline/canvas as HTML-first sections.
3. Preserve parent_asset_id + draft document_id linkage for provenance.
4. Tests: open from merge result document_id; refuse non-html view_format.

## Honesty
Does not invent live multi-agent writing. Offline-honest path first.
