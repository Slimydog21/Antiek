# Biography is a TEMPLATE over Research + Write + Speak — NOT a fifth graph

**Date:** 2026-05-28
**Branch:** `caffen/lr-spr11`
**Source spec:** Antiek SPR-11 (Biography = a TEMPLATE composing
Research + Write + Speak over the ONE graph + onboarding + invite-to-talk)
**Status:** built. The composition is real (it provisions all three
surfaces over the shared substrate); it adds NO new store/graph.

## The decision

Creating a biography is a **template**: it provisions a Research folder
(SPR-05 `startInvestigation`), a Write deliverable scaffold (SPR-09
`createDeliverable` with `investigation_root_id`), and a Speak interview
project (SPR-10 `create_project`) — **all on the same DuckDB substrate and
the same insight/open-question graph**. A biography is the *composition* of
those three, not its own entity:

- there is **no `biography_id`** and **no `biography_*` table/store**;
- the three surfaces share **one identity** — the `investigation_id`. The
  Write deliverable's `investigation_root_id == investigation_id`; the
  Speak↔investigation link (the one real gap — `create_project` takes no
  investigation arg) is held by a single **`speak.biography.composed`**
  event recorded through the shared funnel
  (`record_speak_event` → `log_event`), keyed on the `investigation_id`,
  whose payload carries `{investigation_id, deliverable_id, project_id}`.
  **An event in the shared trajectory log is NOT a store.**

Files: `substrate/speak/biography_composition.py` (the composition),
`interfaces/research/api/speak_routes.py` (`POST /speak/biography`),
`apps/reading/src/modes/Biography/` (the landing + onboarding),
`apps/reading/src/lib/speakApi.ts` (`createBiography`).

## Steelman of the rejected alternative (rigor #2): biography-as-its-own-graph

A dedicated biography graph — one tuned for the things biographies are
*about*: a chronological spine (life-chapters/timelines), a who-knew-whom
relationship structure, a canonical "the subject" node — is genuinely
appealing. It would make biography-specific structure a **first-class
schema** rather than an emergent view over generic insight/question nodes,
it could be **marketed independently** ("DeepBlu, the biography product"),
and it would let the biography UI lean on shape the generic graph does not
guarantee. For a product whose whole pitch is "remember a person," a graph
built for people-over-time is the obvious-looking move.

## Why the template held

A separate graph **kills the cross-corpus value §16 protects**. The moat
is the *one* shared insight/question graph that compounds across all four
surfaces: an interview captured for a biography is **also a reusable
source** for any research, and a research finding is reusable in the
biography draft. Put the biography on its own graph and that interview
becomes a **dead silo** — it can never be the source that corroborates a
research claim elsewhere, and a research finding can never feed the
biography without a copy. Two graphs also re-introduce exactly the
**separate-graphs anti-pattern §16 rejects** (four lenses over ONE graph,
never separate products with separate graphs), and they would fork the
provenance chain (claim → chunk → document → ip_holder_id) the §9
economics depend on.

Biography-specific *structure* (a timeline view, a relationship view) is
not lost by this decision — it is deferred and can be built as a **view /
derived projection** over the one graph, the same way the auto-notebook
(SPR-06) is a derived view, never a second store. That is out of scope for
SPR-11 (the composed preset only) but is not foreclosed.

## The executable form of this decision (rigor #5)

The one-graph assertion is not a code-review judgment — it is a mechanical
test, **named so a future refactor cannot silently undo it**:

> `tests/test_speak_biography_composition.py::test_biography_creates_no_new_store`

It snapshots the full `information_schema` table set before composing a
biography and asserts the set is **unchanged** afterward (in particular, no
`biography_*` table), and that the composition link lives in the **shared
event funnel** (the `speak.biography.composed` event in the
investigation's trajectory), not a store. If anyone later adds a
biography-specific store/graph to hold the composition, **this test
fails** — which is exactly where the reversal of this decision must
surface.

## Reconsider-if

If the operator decides biographies need a **tuned standalone graph** —
e.g. a measured case where the generic insight/question graph cannot carry
the chronological/relationship structure biographies require, and a
derived view over the one graph is demonstrably insufficient — then this
decision reopens. The reopening **must** start by changing
`test_biography_creates_no_new_store` (the guard is the contract); a
standalone biography graph then has to be justified against the
cross-corpus value it gives up (a biography interview ceasing to be a
reusable source for any other research). Until then: template over the one
graph.

## New event

`SPEAK_BIOGRAPHY_COMPOSED` (`speak.biography.composed`) is added as a
**Speak-local string constant** in `substrate/speak/events.py`, NOT a
central `ActionType`. Per that module's standing doctrine this keeps the
codegen-staleness gate green with no TS drift (no `EVENT_SCHEMA_VERSION`
bump) — the same posture as `SPEAK_INTERVIEW_GRADED` (SPR-10).

## Nav placement

Biography is reachable from the **home's "Start a biography" feature
card** (`modes/Home/Home.tsx`, repointed from `/speak` to `/biography`),
NOT from the four-door Research/Read/Write/Speak rail. A fifth rail door
would imply a fifth product/graph — the opposite of this decision. In the
taxonomy (`shell/workflowTaxonomy.ts`) the Biography mode is classified
under the **Speak** workflow (the talk/voices surface it leads into), so it
is honestly inventoried + reachable via More/⌘K without becoming a rail
destination.
