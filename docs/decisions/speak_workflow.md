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
- **Write (`OutlineBlock`, `creative_writer`) — LANDED + WIRED (2026-05-25,
  commit `44907c0`).** SPR-08 built against the `contracts.OutlineComposer`
  Protocol with `biography.SpeakOutlineComposer` (legacy `section_blocks`).
  `substrate/write/` has since shipped, so `substrate/speak/write_composer.py`
  supplies the contract's real implementation: `WriteOutlineComposer` composes
  through Write's canonical `outline_blocks` layer (which supersedes
  `section_blocks`) via `substrate.write.place_block`, now
  `assemble_outline`'s default (`default_outline_composer`, falls back to the
  legacy composer if Write is absent). A speak_claim maps to a `synthesized`
  block with `source_block_id`=claim_id + contributor provenance in metadata —
  **not** promoted to a shared graph node (same operator-gated consent
  boundary as the DRW seam). Speak no longer forks onto the legacy substrate.
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
not-found → 404). `tests/test_speak_api.py` runs the full operator +
invitee journeys end-to-end through the REAL wired app (TestClient over
`create_app`) + every gate refusal — a true end-to-end for the API. The
browser UI surfaces that call it now exist too (see the two sections
below).

## The GapSource seam paid off

DRW SPR-07's real gap detector landed during this work and wired itself
into Speak SPR-04 via the `contracts.GapSource` Protocol —
`interviewer_context.build_conditioning_context` now defaults to
`drw_gap_source.default_gap_source(con)` (DRW shared-graph gaps +
Speak's consent-aware local source). Zero changes to Speak's call sites
or tests; all 8 SPR-04 tests stayed green. This is the contract-first
design doing its job.

## UI surfaces (built 2026-05-25, continuation)

The browser surfaces now exist, wired to the `/speak` REST API:
- **`modes/SpeakIndex`** — project list + create form (publish-intent
  surfaces the legal-gate note).
- **`modes/Speak`** (operator console) — per-project workspace: economics,
  the live Invites surface, and corroborate / draft / publish / book-order
  controls, each surfacing its specific gate-refusal reason. Routes
  `/speak` + `/speak/:projectId` (authed).

## Invitee surface — token-authorized, unauthenticated (the demand side)

The product thesis is "send a link to friends and family." That page is
**`modes/SpeakInvite`** at the **unauthenticated** route
`/speak/invite/:token` (top-level, before the `RequireAuth` catch-all).

Architectural call: an invitee is a SOURCE, not an account (real
contributor accounts are gated on G7), so the URL TOKEN is the
credential. A dedicated token-authorized API surface
(`/speak/invite/{token}` — landing / consent / answer / followups /
decline) is keyed by token, never a caller-supplied interview_id,
verifies the token resolves, and operates only on that one interview —
SEPARATE from the operator-authed `/speak/...` endpoints. The
operator-auth middleware lets the `/speak/invite/` prefix through (the
token authorizes, not an operator session); a test asserts the operator
surface stays auth-gated while the invitee surface is reachable. Lock
discipline: token-resolve under one write lock, released before
`resume()`/`submit_answer()` acquire their own (no nesting). Consent is
scoped + honest in the UI (`record` required to take part;
`attribute`/`publish` optional, declining publish shown as "still helps,
just not public"). `tests/test_speak_api.py` now runs the invitee flow
end-to-end (23 API tests total).

## Voice loop, hardening + gate surface (2026-05-25, continuation)

Four commits closed the invitee VOICE experience and locked the
invariants — all on already-committed deps (no parallel-stream coupling):

- **Voice notes for invitees + nav** (`ce7938e`). Token-gated
  `POST /speak/invite/{token}/transcribe` reuses `WhisperTranscriber`
  (503 when unconfigured) + a `VoiceNoteRecorder` that records →
  transcribes → fills the answer box, which the invitee CORRECTS before
  submit (distill-from-corrected, SPR-02 M5). A microphone "Speak" entry
  in NavRail's main group — the fourth workflow is now discoverable.
- **Spoken turn-taking** (`3c5c2a1`). Token-gated
  `POST /speak/invite/{token}/speak` reuses the committed
  `OpenAITTSProvider.synthesize` (the same provider Read SPR-07's
  `/speech/tts` uses — one TTS path, not a fork; 503 without a key). A
  "🔊 hear this question" control completes the ASYNC two-way voice
  loop: hear the question ↔ answer by voice. (Real-time roundtrip + the
  dispatch-tier `openai_tts.call()` stub stay deferred — see D10.)
- **Invariant hardening** (`82c0ed5`). The CLAUDE.md-mandated agent-
  failure fixture for the DuckDB-FK-blocks-`interviews`-UPDATE gotcha
  (`tests/regression/agent_failures/speak-duckdb-fk-blocks-interview-update.yaml`
  + `tests/test_speak_fk_regression.py`; fix_commit `e1c10ee`) + hypothesis
  property tests locking the binding split rule, corroboration≠truth, the
  independence guard, and the fair split
  (`tests/properties/test_speak_properties.py`).
- **Gate-readiness surface + POD seam** (`43b0926`). `GET /speak/gates`
  REPORTS each gate's status / what it unlocks / the operator closure
  action — and NEVER closes one (a test asserts `POST /speak/gates` →
  404/405). The `PhysicalBookProvider` seam gained a vendor-agnostic
  registry (drop a vendor in by name, no call-site change) + a gated
  `fulfill()` raising `PodVendorUnconfigured` — the chokepoint proving
  nothing prints/ships before a vendor is chosen.

Judgment recorded explicitly: G2/G3/G7/G8 were NOT closed in code (that
would bypass counsel + the consent/accrual architecture), and no live
POD vendor was wired (the spec rejects v1 POD). The honest engineering
*around* each — the readiness report + the drop-in seam — is what
shipped. ~169 Speak tests green; tsc clean; codegen in sync; pushed to
`origin/read/workflow-execution`.

## Deferred (NOT built — honest scope)

- **A running-server browser e2e** (voice capture for invitees: ✅ BUILT
  `ce7938e`/`3c5c2a1` — token-gated transcribe + speak + recorder UI).
  The full operator + invitee journeys are end-to-end tested in
  `test_speak_api.py` (TestClient); the Storybook e2es
  (`speak-biography.spec.ts`, `speak-publish.spec.ts`) smoke the UI
  surfaces and `test.skip` the live-API browser journey (Storybook has
  no live `/speak` server). Only a running-server browser e2e remains.
- **Live POD fulfillment.** Still deferred (spec rejects v1 POD until a
  vendor is chosen) — but the seam is now drop-in ready: a vendor-
  agnostic registry + a gated `fulfill()` (`43b0926`). Tracked as
  `engineering_deferrals.md` **D14**. `StubPhysicalBookProvider` quotes
  and fulfils NOTHING; a Lulu/IngramSpark adapter registers by name with
  no call-site change.
- **Real-time spoken turn-taking.** The ASYNC spoken loop (hear question
  ↔ voice answer) is ✅ BUILT (`3c5c2a1`, reusing the committed
  `OpenAITTSProvider.synthesize`). What remains deferred is the
  REAL-TIME roundtrip (talk-to-the-AI, ~3–5s latency) and the dispatch-
  tier `openai_tts.call()` (still `NotImplementedError`) — see
  `engineering_deferrals.md` **D10** (sync voice model).

## Operator-gated, not code (the unlocks)

- **G2 (lawyer review) + G3 (opt-in)** → public publishing
  (`ANTIEK_SPEAK_PUBLIC_PUBLISHING`) + disbursement (`ANTIEK_STRIPE_PROVIDER=real`).
- **G7** → the public interview ecosystem (`ANTIEK_SPEAK_PUBLIC_ECOSYSTEM`).
- **Loop-3/G8** → the RL-tuned interviewer (`ANTIEK_LOOP3_UNLOCKED`).
- **A POD vendor decision** → physical fulfillment.

This is not legal advice; G2 counsel review is the binding gate. The
implementation reduces legal exposure and makes the system defensible;
it does not make publishing safe.
