# interfaces/

The server-side surface packages plus pointers to the mounted web surfaces.
This directory is not the whole UI: the current Read and Write product loops
live in `apps/reading/src/modes/`, while API routers live under
`interfaces/research/api/`.

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
- **Read web surface** — mounted in the app, not in this package. The
  canonical Reader route is `apps/reading/src/modes/Reading` at
  `/read/:documentId`, reached through `apps/reading/src/lib/openDocument.ts`
  and guarded by `interfaces/research/api/books.py` +
  `substrate.books.serve_guard.serve_full_text_guarded`. This closes the old
  "empty reading package" claim; it does not declare the full Loop 2
  document-wrestling vision complete.
- **Write web surface** — mounted in the app, not in `interfaces/creation/`.
  The Write door is `apps/reading/src/modes/Write/WriteHome.tsx` at `/write`,
  backed by `interfaces/research/api/write_routes.py` and `substrate/write/`.
  This closes the old "empty creation package" claim; graph depth, provider
  configuration, and dogfood still gate product maturity.

## Scaffolded, deferred

- **`reading/`** — Historical package marker only. Do not infer current
  Read product state from this directory; use the mounted app surface above.
  Missing Loop 2 pieces remain tracked in the Read/activation docs, not here.
- **`creation/`** — Historical package marker for the old creation surface.
  Do not infer current Write product state from this directory; use
  `/write` and the Write router above. The strategic create-after-consume
  constraint still applies to product quality, even though the surface exists.

## Discipline

Surface applications are replaceable. The substrate is what compounds.
If a choice has to be made between surface polish and substrate
correctness, choose substrate. See architecture_notes §8.
