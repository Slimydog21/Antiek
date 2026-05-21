# Sprint 17 — Interview Voice Mode + Dispatch Tier Measurement + Integration-Spec Half-Day Items

**Status**: execution-ready sprint spec, authored 2026-05-19 from
`master-product-spec.md` §14.1 row. This sprint is the immediate work
following the Sprint 16 chaos-test and IP-attribution-telemetry ship.
**Scope**: one mainline workstream (interview voice mode) +
substrate-wide measurement gate (dispatch tier-differentiation) +
three half-day integration-spec items + one operator-preferred
product surface (Brainstorming Workstation, may slip to Sprint 18).
**Predecessor docs**:
  - `master-product-spec.md` (the canonical source — every item below
    cross-references a master-spec section; do not re-derive from
    scratch)
  - `integration_posthog.md` (Wedge 1a + 1b, half-day each)
  - `integration_autoresearch.md` (`program.md` per role, INTEGRATE NOW)
  - `integration_prime_intellect.md` (F + D debt items per §15.8)
**Sub-document**: per-role `program.md` files at
`roles/<role>/program.md` (shipped this sprint).

---

## 1. Workstreams

### 1.1 Mainline — Interview voice mode (master §11.5, §11.6)

WebRTC capture + TTS dispatch tier + streaming Whisper transcription.
Adds a new orchestration loop (Loop 4 — Interview) parallel to Loops
1 (research) and 2 (wrestling). Per §11.5, the realistic round-trip
latency is 3-5s end-to-end. Sprint 17 ships async; synchronous voice
(OpenAI Realtime API or equivalent) deferred to Sprint 23+ per
master-spec §15.3.

**Acceptance**: operator can send an interview link to themselves,
record a 5-minute conversation in voice mode, receive a transcript
that flows through `acquisition/voice/` into the note-taking pipeline,
and see insights + open questions surface in the workstation.

### 1.2 Substrate — Dispatch tier-differentiation measurement gate (master §14.4)

The Hermes-primary posture is correct for flash/pro/verify tiers but
under measurement for synthesis. Synthesis is the operator-facing
artifact and voice/style discipline (§5) is synthesizer-level; Grok
4.3 has not been benchmarked on long-form English research writing
the way Opus 4.7 has.

**Protocol** (verbatim from master §14.4):

1. Pin synthesizer tier to Opus 4.7 via OpenRouter primary, Hermes
   fallback. Edit at `substrate/dispatch/config.yaml`.
2. Run 2 weeks of normal investigation traffic.
3. Measure verifier pass rates per provider on synthesis outputs.
4. Verdict at Sprint 20:
   - Within 5pp of Opus → flip back to Hermes primary on cost grounds
   - Larger gap → keep Opus on synthesis as primary; the cost
     savings on synthesis are illusory because they convert to
     additional verifier and re-synthesizer dispatch

**Acceptance**: dispatch config edited; investigation traffic for 2
weeks captured under the new routing; verifier-pass-rate query
runnable; verdict landing in Sprint 20.

### 1.3 INTEGRATE NOW — `program.md` per role (integration_autoresearch.md)

Half-day. Each of the 12 roles at `roles/<role>/` gets a `program.md`
file written in plain markdown. The format follows the autoresearch
pattern: lightweight operator-editable instructions naming what the
role does, what good output looks like, what to avoid, and what
hypotheses to try when iterating.

**Why this lands first**: it is the mutation target for the prompt
autoresearch loop (autoresearch Wedge 1, Sprint 19+ parallel
side-track). Without `program.md` per role, the autoresearch Wedge 1
runner has no surface to write the hypothesis against.

**Roles to ship** (12 total): decomposer, evidence_retriever,
parameter_extractor, connector, synthesizer, challenger, grounder,
note_taker, user_agent, creative_writer, interviewer,
voice_note_followup.

**Acceptance**: 12 `program.md` files committed; the synthesizer's
`program.md` explicitly codifies the voice/style discipline from
master §5.1-§5.5; codegen and tests still passing.

### 1.4 INTEGRATE NOW — Storybook scaffold (integration_posthog.md Wedge 1a)

Half-day. Add Storybook to `apps/reading/` and write a `*.stories.tsx`
for each existing custom component (`ClaimCard`, `NotesPanel`,
`ChatInput`, `MasterMdViewer`, `NotesFeed`, `CrossDocSidebar`,
`PdfViewer`). No component-API changes; this is documentation work.

**Why this lands now**: it is the design-system source of truth in
lieu of a separate Figma library. Visual regression catches structural
breakage during the larger Wedge 2 notebook surface work in Sprint
18-19. Future contributors (and Claude Code) can read the component
contract without inferring it from usage.

**Acceptance**: `npm run storybook` boots; one story per existing
custom component; production `npm run build` still passes.

### 1.5 DECIDE NOW — Lemon UI evaluation (integration_posthog.md Wedge 1b)

Half-day spike. `npm i @posthog/lemon-ui` in a branch; replace one
component (`ChatInput` is lowest-risk) and measure against the four
decision criteria from `integration_posthog.md` §5.1b:

- Bundle size delta < 80 KB gzipped
- TypeScript strict compile clean
- Tailwind interop verified
- Operator's visual-fit eye test passes (researcher's-notebook
  aesthetic preserved per master §5.5)
- At least 60% migration coverage projection across the existing
  component surface

**Verdict**: adopt if all four pass; keep custom components if any
fails. **Either outcome is defensible.** The evaluation is the
deliverable, not the adoption.

**Acceptance**: spike branch with one component migrated; bundle-size
diff captured; operator's visual judgment recorded; written verdict
in this sprint's notes.

### 1.6 PRODUCT SURFACE — Brainstorming Workstation scaffold (master §4.5, may slip to Sprint 18)

Per master-spec §4.5, this is the operator's stated preferred product
direction. Sprint 17-18 product surface; substrate primitives already
exist (voice notes from Sprint 13, `question.identified` events).

**Scope for Sprint 17** (scaffolding only; full ship in Sprint 18):

- New route `app.antiek.ai/brainstorm/`
- Watch-for-later folder UI on top of `question.identified` events
  filtered by an `unsharpened` state
- Launch-investigation button per parked question (POSTs to
  `/investigations` with the parked question as the seed)
- Voice-note input affordance (reuses Sprint 13 voice acquisition)

**Deferred to Sprint 18**: thought-partner workflow (new role
`thought_partner` under `roles/`); Lego-block insight slotting from
private graph; full UI polish per PostHog notebook patterns
(`integration_posthog.md` Wedge 2 referenced for visual reference).

**Why scaffold rather than full ship**: operator's preferred direction
warrants getting the substrate hooks right before the surface polish.
The `unsharpened` state for `question.identified` events is a substrate
addition; once in production it can be iterated against in Sprint 18.

**Acceptance**: `/brainstorm/` route renders the watch-for-later
folder; parked questions are clickable; launch-investigation
affordance posts to the existing endpoint.

### 1.7 ABSORB IF CAPACITY — Prime F + D debt (integration_prime_intellect.md, master §15.8)

If the first real-LLM evaluation cycle ships in Sprint 17, absorb
the Prime Intellect F + D debt items here. Otherwise defer to
Sprint 19 when prompt autoresearch (Wedge 1) needs the same
compat-test infrastructure.

- F: trajectory → verifiers schema compat test
- D: `prime eval run` runner for Antiek rubrics with
  `parameter_extractor_v0.jsonl` 50-example set

**Verdict**: operator-decided. Don't force-fit if the voice-mode
mainline work + the four integration-spec items already exhaust
sprint capacity.

---

## 2. Order of operations

Operator-recommended sequence (each item's failure modes are
independent; sequencing is by leverage + risk):

1. **`program.md` per role** (§1.3) — half-day, no production impact,
   unlocks Sprint 19 autoresearch Wedge 1. **Lowest risk, highest
   unlock value.**
2. **Storybook scaffold** (§1.4) — half-day, no production impact,
   unlocks Sprint 18 notebook surface work. **Pure-upside hygiene.**
3. **Lemon UI evaluation spike** (§1.5) — half-day on a branch, no
   merge required to mainline. **Decision-making work.**
4. **Dispatch tier-differentiation measurement begins** (§1.2) —
   one config edit; 2-week measurement window starts. **Substrate
   change, low risk, gates Sprint 20 verdict.**
5. **Interview voice mode** (§1.1) — mainline sprint work, the
   substantive build. **Highest engineering complexity in the
   sprint.**
6. **Brainstorming Workstation scaffold** (§1.6) — operator-preferred
   direction; may slip to Sprint 18 if voice-mode work consumes more
   capacity than projected.

Items 1-4 are designed to land in the first 2 days. Item 5 takes
the remainder of the sprint. Item 6 lands in the last 1-2 days OR
slips to Sprint 18.

---

## 3. Open questions for this sprint

### 3.1 Lemon UI verdict — adopt or keep custom?

Driven by the §1.5 evaluation. Operator decides at end of Sprint 17.
No design call needed before the spike.

### 3.2 Voice-mode latency tolerance

§11.5 cites 3-5s round-trip. The operator's biography use case is
the validation target. If the latency feels unworkable at operator
self-test, escalate to master-spec §15.3 (synchronous voice model
options) — but Sprint 23+ is the realistic timeline for the
synchronous switch.

### 3.3 Brainstorming Workstation scope creep

The thought-partner workflow (new `thought_partner` role) is
deferred to Sprint 18 to keep Sprint 17 scope honest. If the
operator wants thought-partner in Sprint 17, voice-mode work
slips one sprint. **Don't bundle**.

### 3.4 Prime F + D debt

Absorb in Sprint 17 only if the real-LLM eval cycle ships. Defer
to Sprint 19 otherwise. Either is defensible per master-spec §15.8.

---

## 4. What this sprint does NOT do

- **Multi-user pivot** — deferred to Sprint 22+ per master-spec
  §13.4. Six months of operator-graph accumulation must demonstrate
  the compounding curve first.
- **Publisher dashboard / Stripe Connect** — Sprint 18 work.
  Sprint 17 doesn't touch publisher onboarding.
- **Synquery integration** — slips to Sprint 21 per master-spec
  §14.3 sequencing discipline (creation surface PMF signal required
  first).
- **Loop 3 unlock work** — gated by `loop_3_unlock_criteria.md`.
  Don't pre-build the SFT loop, the verifiers envs, or hosted RL.
- **Autoresearch Wedge 1 prompt mutation runner** — Sprint 19+
  parallel side-track. Sprint 17 ships the mutation TARGETS
  (`program.md` per role) but not the runner itself.
- **Pricing-page template** — Sprint 18 work when the publisher
  dashboard ships. Sprint 17 keeps pricing as substrate config
  only.

---

## Final note for the implementing agent

This sprint's work is intentionally distributed across one
mainline workstream + one substrate measurement gate + four
integration-spec items. **Failure modes are independent.** A blocker
on voice-mode (mainline) does not block Storybook, `program.md`,
or the Lemon UI spike. A blocker on Lemon UI does not block voice
mode. Sequence per §2 above; do not bundle.

If the operator picks one item to start with: **`program.md` per
role** (§1.3). Half a day. Zero production risk. Unlocks the
Sprint 19 autoresearch Wedge 1 mutation runner directly. Every
hour spent here is leverage for every iteration of every role
prompt in Sprints 19+.

If the operator picks two: add Storybook (§1.4). Same shape — no
production risk, unlocks Sprint 18.

If the operator wants to start with the operator-preferred direction
instead: §1.6 Brainstorming Workstation scaffold. This is the surface
operator named as preferred; everything else slips one sprint.
