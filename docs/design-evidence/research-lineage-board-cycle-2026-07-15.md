# Research lineage board — design evidence

Date: 2026-07-15

Branch: `goal/research-lineage-board`

Base: `goal/distillation-field-ledger` / PR #2407

## Product gap

`MyResearch` already used the substrate's durable `parent_investigation_id`, but generic rows flattened cascades and recursive chases into a log. A researcher could not scan which investigation originated a family, which questions were chased from it, or whether a chase spawned a deeper question without rereading every title.

## Design decision

- Build one recursive forest directly from the substrate relationship. Every investigation renders exactly once; missing parents become honest standalone roots.
- Family headers name the origin and count all descendants, not only direct children.
- Restrained CSS-only trunks, branch arms, depth offsets, and labels expose lineage without introducing a graph renderer or decorative generated art.
- Status, real cost, replay, navigation, and the `found by the loop` provenance badge retain their existing authority.
- Standalone investigations remain flat cards so the interface does not imply relationships that do not exist.
- At phone width, questions wrap above status metadata and connectors collapse into legible left-edge accents.

## Visual and accessibility proof

- Storybook: `ResearchWorkstation / MyResearch / LineageBoard / FullLineage`
- Storybook: `ResearchWorkstation / MyResearch / LineageBoard / StandaloneOnly`
- Six LostPixel baselines: both stories at 1280, 1024, and 768 px.
- Story fixtures pass a fixed render clock, so relative-time labels cannot drift between CI runs.
- Direct Playwright inspection covered 1280, 768, and 390 px. The 390 px pass prompted a final stacked metadata layout so long questions remain readable.
- Direct axe scans report zero violations for both shipped stories.
- A focused three-generation test proves the grandchild stays inside the original family, carries depth 2, contributes to the descendant count, and is not duplicated as a second family.

## Rejected alternatives

- A force-directed knowledge graph: too much interaction cost for a monitoring ledger and overlaps separately owned graph surfaces.
- Session-colored families: would invent meaning not present in the substrate.
- Generated mascot art in the row chrome: distracts during dense monitoring and adds no lineage information.
- A direct-child-only grouping: the first visual proof exposed that it duplicated an intermediate child as a new family when a grandchild existed.
