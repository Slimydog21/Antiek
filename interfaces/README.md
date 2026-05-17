# interfaces/

The surface applications. Two are in scope for this build; two are
scaffolded only.

## In scope

- **`research/`** — Research workflow CLI and API. Ingests sources,
  builds the graph, runs the 9-phase protocol, archives syntheses.
  This is the Researchmaxx descendant.
- **`interview/`** — Interview capture web interface. Shareable link,
  voice and text capture, transcription, attribution. Funnels output
  into the same knowledge-graph substrate as the research workflow.
  An interview becomes a primary source on the same footing as a
  paper or book. This is the DeepBlu lineage; the biography product
  layer on top (subscription flows, ads, revenue sharing) is
  explicitly deferred — see architecture_notes §5.

## Scaffolded, deferred

- **`reading/`** — Consumption-side PDF reading interface
  (highlight-to-query, mini-briefer pop-ups). Stub components and
  documented data flow live here; the actual UI is 8–12 weeks of
  focused frontend work, separate project.
- **`creation/`** — Outline-plus-tab-completion writing interface.
  Same status: scaffolded, deferred.

## Discipline

Surface applications are replaceable. The substrate is what compounds.
If a choice has to be made between surface polish and substrate
correctness, choose substrate. See architecture_notes §8.
