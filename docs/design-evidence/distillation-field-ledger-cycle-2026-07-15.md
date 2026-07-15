# Distillation field ledger — design evidence

Date: 2026-07-15  
Branch: `goal/distillation-field-ledger`  
Base: `goal/werner-note-filed-reaction` / PR #2406

## Product gap

`DistillView` already read durable insight and open-question graph nodes and preserved the correct challenge/chase contracts. Its two semantic classes nevertheless rendered as visually interchangeable generic lists. That made the completed research product harder to scan and weakened the distinction between what the investigation filed and what it left unresolved.

## Design decision

- Insights use a cool filed-finding ledger with stable numeric locators.
- Questions use a weathered-sun unresolved-thread ledger with `Q` locators.
- Styling never encodes model confidence or truth. Source grounding, escalation, refinement, challenge, and chase copy remain the authority.
- Counts are descriptive and accessible; they do not imply completeness.
- The generated Werner/index-drawer vignette appears only when the graph returned no distilled nodes. It is decorative to assistive technology; the existing honest status and retry action remain semantic.
- `MasterMdViewer`, `ArtifactOutlineShelf`, APIs, routing, backend contracts, and runtime mascot behavior remain outside this cycle.

## Generated asset provenance

`apps/reading/src/brand/werner/research/distillation-empty-v1.webp` was generated with the built-in ChatGPT Image path from a production prompt specifying one restrained scholarly Werner, one archival index drawer, blank cards, pale ice-paper ground, no text, no logo, no second mascot, and no UI chrome. The selected PNG was resized to 840px width and encoded as a 24 KB WebP for the product.

## Visual and accessibility proof

- Storybook: `Loop 1 / Distillation field ledger / Filed and unresolved`
- Storybook: `Loop 1 / Distillation field ledger / Nothing distilled`
- Six LostPixel baselines: both stories at 1280, 1024, and 768 px.
- Direct Playwright review confirmed the ledgers preserve dense reading rhythm at 1280 and 768 px.
- Direct axe scans report zero violations for both stories. The first pass found 3.96:1 contrast on 10px teal locators; the final blend was darkened and re-scanned clean.
- Generated-art weight in the production Storybook bundle: 24.06 KB.

## Rejected alternatives

- Confidence-colored cards: would visually overclaim epistemic certainty.
- A new graph visualization: duplicates more sophisticated graph/trajectory owners and adds interaction cost to a reading surface.
- Mascot animation inside every row: distracts during long-session research and creates a second reaction system.
- Reworking the synthesis reader or outline shelf: collides with mature, separately owned product surfaces.
