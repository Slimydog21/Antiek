# interfaces/creation/

Historical package marker for the old creation-side interface. **The current
Write product is no longer represented by this empty package.**

## Current Write surface

The current Write loop lives in the web app and the research API:

- Door: `apps/reading/src/modes/Write/WriteHome.tsx` at `/write`
- Legacy power surface: `apps/reading/src/modes/CreationStudio` at `/create`
- API router: `interfaces/research/api/write_routes.py`
- Substrate primitives: `substrate/write/`
- Typed client: `apps/reading/src/modes/Write/writeApi.ts`

The mounted Write flow supports repository search, outline placement, section
draft generation through the `creative_writer` dispatch path, edit capture, and
trace-to-source through the one Reader route. This is a scoped implementation
claim, not a claim that graph-backed creation has reached product maturity.
Live generation still depends on provider configuration; the route surfaces
honest failures when dispatch is not available, and the create-after-consume
strategy still depends on a populated graph and dogfood.

## What this package owns now

Nothing executable. Keep this package only as a compatibility marker for old
architecture references. New Write work belongs in `apps/reading/src/modes/Write`,
`interfaces/research/api/write_routes.py`, or `substrate/write/`.

Do not add a second writing surface here.
