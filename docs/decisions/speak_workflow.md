# Speak workflow — execution record (2026-05-25)

**Status:** Substrate built + tested on branch `speak/execution`. 102
Speak tests green; full suite green; codegen in sync; latency lock held
(p95 186.82 µs ≤ 194.85 µs). Activation of the public/paid paths is
operator-gated (G2/G3/G7/G8) — none of those gates is a code change.

Spec: `specs/speak/` (master `index.html` + 9 sprint pages). Speak is
the fourth Antiek workflow (Research · Read · Write · Speak) and the
DeepBlu origin idea (master-spec §11): interview-as-acquisition feeding
the shared insight/question graph, authored with Write, published with
Read, with the 70% ad slice routed to contributors by contribution.

## What was built

All net-new code lives in `substrate/speak/` (additive; no edits to the
hot shared `schemas/events.py` or `graph/schema.py`). Per sprint:

| Sprint | Module(s) | Test |
|---|---|---|
| Foundation | `schema.py` (12 tables), `events.py`, `ids.py`, `contracts.py` | (covered below) |
| SPR-01 consent/rights | `consent.py`, `third_party.py`, `publish_gate.py`, `subject_consent.py`, `takedown.py`, `gate_status.py` | `test_speak_consent.py` (20) |
| SPR-02 async voice | `async_interview.py` + `Interview/InterviewTranscript.tsx` | `test_async_interview.py` (12) |
| SPR-03 project/invites | `project.py`, `invitations.py` + `Speak/Invites.tsx` | `test_speak_project.py` (12) |
| SPR-04 compounding interviewer | `interviewer_context.py`, `interviewer_capture.py` | `test_compounding_interviewer.py` (8) |
| SPR-05 corroboration | `corroboration.py`, `independence.py` | `test_cross_interviewee.py` (8) |
| SPR-06 economics | `contributor.py` | `test_contributor_economics.py` (9) |
| SPR-07 economics matrix | `economics_mode.py` | `test_economics_matrix.py` (14) |
| SPR-08 authoring | `biography.py` | `test_biography_authoring.py` (9) |
| SPR-09 publishing | `publish.py`, `physical_book.py` + `e2e/speak-biography.spec.ts` | `test_speak_publish.py` (10) |

## Binding invariants honored (and where enforced)

- **Consent before substance, verification before publish.** Scoped
  consent (`consent.py`); a third-party claim is publishable only if
  multiply-attested or operator-attested (`publish_gate.check_claim_publishable`);
  the per-project public gate refuses unless G2/G3 + subject consent +
  no takedown + all third-party claims publishable, first failing reason
  wins (`publish_gate.check_public_publish`). Enforced at the DATA layer
  — tests bypass the UI.
- **Corroboration ≠ truth.** `corroboration.confidence_for` is capped at
  **0.95** — no amount of attestation yields certainty. The label is
  `multiply_attested`, never `true`. A shared rumor (same independence
  key) counts as one attestation (`independence.py`).
- **Public ⇒ algorithmic 70% split always.** `economics_mode.resolve_policy`
  sets `split_applies == (publishing == public)` with NO override
  parameter — a creator cannot pocket contributor economics on a public
  work, even for private invitations.
- **Accrue now, disburse later.** `contributor.accrue_contributions`
  routes the 70% slice to escrow (zero-buyer safe — tracks the share,
  shows no fictional balance); `contributor.attempt_disbursement`
  refuses pre-G2/G3 (`gate_status.disbursement_allowed`). Slop earns $0.
- **Public ecosystem gated on G7.** `invitations.open_public_contribution`
  raises `PublicEcosystemGated` unless `ANTIEK_SPEAK_PUBLIC_ECOSYSTEM`;
  invitees are sources, not accounts.
- **RL-tuned interviewer deferred to Loop-3/G8.** `interviewer_capture`
  captures trajectories; `harvest_for_rl` gates on `check_unlocked`.
- **Single-writer.** Every mutation goes through a `LockedConnection`
  (`ensure_speak_schema` asserts it).

## Cross-spec contract decisions

- **Read (servable corpus / `platform_authored`) — EXISTS, used directly.**
  `substrate.books.servability` shipped (parallel stream) during this
  execution. A public biography is `content_class='user_public_contribution'`
  → `servability_of` → `PLATFORM_AUTHORED` → servable. No fork.
- **Write (`OutlineBlock`, `creative_writer`).** The `creative_writer`
  role + `deliverables`/`section_blocks` substrate exist; `substrate/write/`
  does not yet. SPR-08 builds against the `contracts.OutlineComposer`
  Protocol with `biography.SpeakOutlineComposer` as the default (writes
  `section_blocks`); Write's composer drops in later.
- **DRW (`gap_detection`) — LANDED + WIRED (2026-05-25, commit `e865fad`).**
  SPR-04 built against `contracts.GapSource` with
  `interviewer_context.SpeakGraphGapSource` as the default. DRW SPR-07 has
  since shipped (`substrate/gap_detection/`), so `substrate/speak/drw_gap_source.py`
  supplies the contract's intended real implementation: `DRWGapSource`
  (centrality-ranked, **project-scoped** via `metadata.speak_project_id`) +
  `CompositeGapSource` (DRW shared-graph gaps + Speak consent-aware
  project-local), now `build_conditioning_context`'s default via
  `default_gap_source`. Behavior is unchanged today (DRW contributes `[]`
  until Speak content is promoted to the shared graph) — and that promotion
  is deliberately NOT done here: cross-workflow shared-graph visibility is
  G2/G3-class consent/legal weight, operator-owned. The module defines the
  convention (`SPEAK_PROJECT_NODE_KEY`) a sanctioned promotion follows.

## Integration choices worth recovering later

- **Speak events are namespaced strings via the free-form `log_event`
  path** (`substrate/speak/events.py`), NOT new `ActionType` enum members.
  Reason: `schemas/events.py` is concurrently edited by the parallel
  stream (collision hazard per CLAUDE.md), and this keeps the codegen-
  staleness gate green with zero TS drift. Promote to the enum in a
  dedicated codegen-regenerated commit if Speak events need TS types.
- **No DB-level FK constraints in `speak/schema.py`.** DuckDB blocks
  `UPDATE` of a referenced parent row (its documented FK limitation), and
  `interviews` rows are updated constantly. Provenance is held by column
  discipline + the audit-event trail, per the existing `graph/ops.py`
  convention.

## REST surface (built 2026-05-25, continuation)

`interfaces/research/api/speak_routes.py` — a standalone `APIRouter`
(`prefix=/speak`) wiring the whole substrate into the FastAPI app, kept
out of the 5k-line `app.py` factory (collision safety) and included with
one documented line before `return app`. Carries no auth (the app's
global operator-auth middleware covers it). Covers the full journey:
projects, invites (+ token resolve, + G7-gated open-public), consent,
answers, **claims** (the explicit answer→claim bridge — third-party
tagging is a confirmed judgment, never inferred), corroborate,
subject-consent, contributors, draft, publish, book-orders, takedowns.
Domain exceptions map to HTTP (consent/G7 → 403, publish/disburse → 409,
not-found → 404). `tests/test_speak_api.py` (6 tests) runs the full
operator journey end-to-end through the REAL wired app (TestClient over
`create_app`) + every gate refusal — this IS a true end-to-end for the
API; the only thing still missing is a browser UI PAGE.

## The GapSource seam paid off

DRW SPR-07's real gap detector landed during this work and wired itself
into Speak SPR-04 via the `contracts.GapSource` Protocol —
`interviewer_context.build_conditioning_context` now defaults to
`drw_gap_source.default_gap_source(con)` (DRW shared-graph gaps +
Speak's consent-aware local source). Zero changes to Speak's call sites
or tests; all 8 SPR-04 tests stayed green. This is the contract-first
design doing its job.

## Deferred (NOT built — honest scope)

- **Browser UI page for the authoring/publishing journey.** The REST
  surface it would call now EXISTS and is end-to-end tested
  (`test_speak_api.py`); only the React page is missing.
  `e2e/speak-biography.spec.ts` smoke-tests the extant Speak surfaces
  (Invites, transcript correction) and `test.skip`s the full *browser*
  journey with that reason.
- **Live POD fulfillment.** `physical_book.StubPhysicalBookProvider`
  quotes a cost and fulfils NOTHING. A vendor adapter (Lulu/IngramSpark)
  drops into the `PhysicalBookProvider` seam later.
- **Live spoken turn-taking / TTS.** Out of scope per SPR-02;
  `openai_tts.py` still raises `NotImplementedError`.

## Operator-gated, not code (the unlocks)

- **G2 (lawyer review) + G3 (opt-in)** → public publishing
  (`ANTIEK_SPEAK_PUBLIC_PUBLISHING`) + disbursement (`ANTIEK_STRIPE_PROVIDER=real`).
- **G7** → the public interview ecosystem (`ANTIEK_SPEAK_PUBLIC_ECOSYSTEM`).
- **Loop-3/G8** → the RL-tuned interviewer (`ANTIEK_LOOP3_UNLOCKED`).
- **A POD vendor decision** → physical fulfillment.

This is not legal advice; G2 counsel review is the binding gate. The
implementation reduces legal exposure and makes the system defensible;
it does not make publishing safe.
