# interfaces/reading/

Historical package marker for the reading interface. **This README used to
describe Read as unimplemented; that is no longer true.**

## Current Read surface

The current Read product lives in the web app, not in this package:

- Reader route: `apps/reading/src/modes/Reading` at `/read/:documentId`
- One-door resolver: `apps/reading/src/lib/openDocument.ts`
- Typed body renderer: `apps/reading/src/components/reader/Reader.tsx`
- Serve gate: `interfaces/research/api/books.py` calling
  `substrate.books.serve_guard.serve_full_text_guarded`
- Conformance guard: `apps/reading/src/__tests__/oneReader.conformance.test.ts`

The Read surface opens gated/servable documents through the one Reader route,
supports the shared FloatMenu highlight actions, and routes citations/source
opens through `openDocument`. This is a scoped implementation claim, not a
"Loop 2 is finished" claim: activation dogfood, live provider-backed dialogue,
research spin-out feel, background note-taking depth, question-highlight
polish, and cross-document Q→A workflows remain governed by
`docs/specs/antiek-reader/handoff-to-activation.md` and the activation sprints.
Live AI actions remain honest INERT-without-keys until provider configuration
is present.

## What this package owns now

Nothing executable. Keep this package only as a compatibility marker for old
architecture references. New Read work belongs in `apps/reading/src/modes/Reading`
or the shared reader/FloatMenu modules, with backend serve changes in the
research API or substrate packages named above.

Do not add a second Reader implementation here.
