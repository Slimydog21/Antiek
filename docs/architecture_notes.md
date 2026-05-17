# Antiek architecture notes

This document preserves the reasoning behind the architecture so future
sessions and operators don't have to re-derive it. It pulls together
three threads: the Researchmaxx audit findings that motivated the
consolidation, the non-negotiable substrate decisions from the spec, and
the design principles drawn from the Agent paradigm shift that reshape
how the substrate is built.

The implementation is the *what*; this document is the *why*.

---

## 1. Why consolidation, not rename

Researchmaxx (research-agent infrastructure) and DeepBlu (interview
capture for biography-as-a-service) developed in separate branches but
share more substrate than the separate histories suggest. Both depend
on the same primitives:

- Structured event capture
- Typed knowledge-graph operations
- Multi-model LLM dispatch with cross-family verification
- Content-addressed source attribution

The consolidation is the recognition that the consumption side of
research (Researchmaxx) and the primary-source acquisition side
(DeepBlu's interviews) are two acquisition paths into the same
substrate. An interview is a primary source on the same footing as a
paper or a book; it just enters through a different door.

This is also the reason `acquisition/` is path-specific (each source has
different mechanics) while `processing/` is shared (chunking, embedding,
extraction don't care where the content came from).

### 1.1 The graph is the product, not a substrate detail

The deeper unification — added 2026-05-16 once the consume and create
loops were articulated together: **the knowledge graph is the product
the user manipulates, not an internal artifact.**

- Consume populates the graph. Wrestling with a document produces
  distilled facts (nodes), grounding evidence (attributed edges), and
  emergent questions (nodes of a different type). Deep research does
  the same thing autonomously across sources.
- Create renders subsets of the graph. The "lego block" assembly the
  user describes for the research deliverable is graph-node selection
  + traversal-as-outline; the prose, charts, and figures are
  generated *after* the truth-flow is determined.
- Interview (DeepBlu's path) is the same graph-population mechanic
  with a different acquisition surface. The AI interviewer is
  superhuman precisely because it queries the project's graph between
  turns — it knows what's already covered, what's missing, and what
  the next question should probe.

This is why §2's substrate decisions are non-negotiable: if the graph
is the product, the graph's schema, attribution discipline, and event
provenance are not implementation details — they are the user-visible
contract.

---

## 2. The non-negotiable substrate decisions

These are load-bearing. Everything downstream depends on getting them
right. They are documented here separately from the spec so the
reasoning persists even when the spec gets revised.

### 2.1 Typed event log as the unit of work

Every action that mutates the graph or advances an investigation is a
typed event:

```
(event_id, timestamp, investigation_id, phase, role, action_type,
 payload, parent_event_id, parameter_version)
```

The log is append-only. The log is the source of truth; the graph state
is derived from replaying events.

**Why this is non-negotiable.** Without it you cannot:

- Do supervised fine-tuning on captured trajectories (no curated training data).
- Reliably resume failed investigations (no checkpoint to restart from).
- Audit what the system actually did versus what it claims to have done.
- Validate that the compounding-skill layer is growing (no growth signal).

The Researchmaxx architecture had this implicitly inside its phase
logic but not explicitly as a first-class substrate object. The
migration to Antiek is the right window to fix this; carrying the gap
forward poisons every downstream property.

**Action vocabulary** (minimum, stable, enumerated in
`substrate/schemas/actions.py`):

```
ingest_chunk, extract_node, attach_edge, assign_tier,
advance_sub_question, run_retrieval, propose_synthesis,
fail_constraint, mark_stale, archive_synthesis,
capture_interview_response, attribute_source,
invoke_skill, update_skill, dispatch_subagent
```

Heartbeat-fired events and context-pack-assembled events are also typed
events, which makes autonomous behavior auditable by query rather than
guess.

### 2.2 Phase orchestration as code, not prose

The 9-phase autonomous research protocol previously lived as English
instructions in `autonomous-deep-research/SKILL.md`. The Researchmaxx
audit explicitly called this "the single biggest gap in the
architecture."

**The fix.** `orchestration/phase_runner/` owns transitions. A
`phase_log` table records every entry, exit, and verification status
per investigation. Transitions are explicit function calls, not
implicit model behavior.

Phase 8 (graph merge into compounding-domain skills) cannot be marked
complete unless `phase_log[8]["verified"] == True` based on an actual
diff of the skill files showing growth. This is mechanical
verification, not rhetorical assertion.

**Why this is non-negotiable.** Prose enforcement is a documented
failure mode. The system claims to compound; mechanical verification is
the only way to know whether the claim is true.

### 2.3 DuckDB write coordination

Three writers operate against a single-writer database with no
coordinator: daily cron, weekly monitor, on-demand kanban workers.
Adding the interview-capture path multiplies collision scenarios.

**The fix.** A write-lock file at `~/.antiek/duckdb.lock` with PID and
acquisition timestamp. Each writer acquires before writing, releases on
completion or timeout. Robuster alternatives (Redis-backed queue, SQLite
job table) are documented but the simplest correct implementation
ships first.

**Why this matters now.** The current system hasn't broken because
cadences are spread out. Adding interview capture plus on-demand
kanban research plus scheduled ingestion creates collision windows the
current architecture doesn't handle.

### 2.4 Role implementation consolidation

The existing Researchmaxx has two role implementations (`roles.py` and
`role_orchestrator.py` + `role_prompts.py`) that may have diverged. The
migration consolidates to one canonical implementation in `roles/`. If
both have valuable code, merge selectively with explicit reasoning.

The centralized-constants discipline only works if there's one consumer
of `constants.py` per role.

### 2.5 Multi-model dispatch with context packing

`substrate/dispatch/` exposes a single signature:

```python
dispatch(prompt, role, max_tokens, verification_required, context_pack) -> response
```

Internally it routes to:

- Local inference (deferred; no backend in this build)
- DeepSeek V4 Pro / Xiaomi MiMo V2.5 Pro for primary work where
  reasoning depth dominates
- Grok 4.3 via Hermes for cross-family verification
- Claude via API for high-stakes synthesis
- Xiaomi MiMo V2.5 Flash / DeepSeek V4 Flash for bulk cost-optimized work

Configuration lives in `substrate/dispatch/config.yaml`. Changing
routing is a config change, never a code change. When local hardware
eventually arrives, it's one new backend behind the same interface.

**The Pro/Flash split is deliberate.** The MoE flash variants (309B
total / 15B active for MiMo V2.5 Flash; 284B / 13B for DeepSeek V4
Flash) are the right tool for bulk processing — low per-token cost,
manageable compute footprint. The Pro variants (DeepSeek V4 Pro at
1.6T / 49B active; MiMo V2.5 Pro at >1T) earn their premium on
synthesis where reasoning depth and multi-hop coherence matter more
than throughput. Treating them as interchangeable cost tiers is the
failure mode. The router makes the choice explicit at the role level
rather than hiding it in a default.

**The context-pack argument is new and load-bearing.** The router
accepts not just a prompt but a `context_pack` assembled by
`substrate/context_pack/`. The pack contains hierarchical memory
(recent session context plus relevant long-term skill content plus
retrieved graph evidence), active phase metadata, and the parameter
version stamp. The pack itself is a typed event in the log, so "what
did the model actually see when it made this decision" is a queryable
property rather than a guess.

This pattern — Luo's "精细编排的context" (meticulously orchestrated
context) — is what makes the Agent paradigm shift work. Context isn't
whatever fits in the window; it's deliberately layered information
assembled with awareness of what each layer contributes.

### 2.6 Long context as tactical resource, not default

Most role invocations run on 32K–128K context with carefully assembled
packs. The 1M context window is reserved for synthesis steps that
genuinely require it, and even then the pack is curated rather than
dumped.

This is the same insight that drove MiMo V2's Hybrid Attention design:
the question isn't "how do we support long context" but "how do we
make long context efficient enough to actually use." For Antiek, the
equivalent is: keep most operations short-context (cheap, fast,
predictable) and reserve long-context for operations that need it.

---

## 3. Design principles from the Agent paradigm shift

This section captures the deeper architectural shift that reshapes how
the substrate is built, not just how surface applications behave.

### 3.1 The framework is the agent

The largest single shift from the original spec: the framework — the
orchestration, the dispatch router, the context packing, the
heartbeats, the Skills layer — isn't infrastructure under the agent.
It *is* the agent, or close enough that the distinction stops
mattering. The model is one component the framework orchestrates
alongside tools, memory, and accumulated procedural knowledge.

This is why the commitments around typed events and Skills-as-first-class
are non-negotiable: they're what make the framework substantive rather
than ornamental.

### 3.2 Skills as compounding substrate

The Skills layer has three distinct categories:

- **Domain skills** — accumulated facts and frameworks (quantum, defense,
  AI infrastructure, semiconductor). Updated via Phase 8 after each
  research cycle. Verification: diff against snapshots, alert on
  non-growth.

- **Process skills** — how to do specific research workflows ("how to
  evaluate a Series B deep-tech investment", "how to conduct a
  falsification round"). Procedural artifacts refined through use.
  When the system encounters a pattern three times, propose codifying
  it as a skill.

- **Verification skills** — how to verify specific claim classes ("how
  to verify a claim about quantum hardware specifications"). The
  deterministic-rubric-plus-judged-rubric combinations from the
  constraint middleware, captured as reusable artifacts rather than
  embedded in role prompts.

Skills are versioned alongside `ANTIEK_PARAM_VERSION` and stamped into
archived syntheses. When a synthesis is produced under skill version
Q3.7 of quantum-domain-knowledge plus version P2.1 of evaluate-Series-B
plus version V1.4 of verify-quantum-hardware-claims, that's what gets
archived. Backtests can then correlate skill versions to outcomes;
skill quality becomes measurable.

Skills can be proposed by the system itself when patterns are observed
multiple times, but promotion requires human review. Fully autonomous
skill writing is deferred — the proposals route to review until the
substrate has been operational long enough to establish whether the
proposals tend to be good.

### 3.3 Heartbeats: the autonomous-behavior layer

Luo's distinction between code agents (no heartbeat) and daily-life
agents (heartbeat required) applies directly. A research agent that
compounds across months needs autonomous behaviors that aren't
triggered by user action.

- **Daily** — ingest new arXiv papers in tracked themes; check active
  investigations for staleness; diff domain skill files to catch silent
  Phase 8 skips early.

- **Weekly** — run the skill-growth audit; generate a token-volume
  report by role and provider; check synthesis consistency against
  backtest cohorts.

- **Monthly** — generate the hardware-decision metrics report; diff
  the four criteria against the previous month; check whether any
  process skills have been derived three times and propose codification.

- **External-event-triggered** — re-evaluate tier classification when
  tracked subjects appear in news media; flag syntheses for staleness
  review when contradicting papers publish.

Heartbeats are themselves typed events. `heartbeat_fired` at 8am
Tuesday triggering a skill diff produces an event followed by downstream
events, all queryable.

### 3.4 The User Agent role

For the interview workflow specifically, the User Agent is load-bearing.
Testing interview flows against real subjects is slow, expensive, and
ethically constrained. A User Agent that can play "elderly family
member being interviewed about their early career" with realistic
conversational patterns lets us iterate without burning real subject
time.

This is the same insight Luo describes spending two hours co-designing:
reliable multi-turn interaction depends on being able to simulate the
other side of the conversation. The role belongs in `roles/user_agent/`
and is exercised heavily during interview-workflow development.

### 3.5 Group intelligence across time

"Group intelligence" in a single-operator system doesn't mean a
community of contributors. It means the Skills layer accumulating
procedural knowledge across investigations, the event log preserving
institutional memory across model upgrades, the User Agent enabling
iteration cycles without real subjects. The architecture compounds
knowledge across time the way an open-source community compounds
knowledge across contributors.

---

## 4. Preserved strengths of the existing codebase

The Researchmaxx audit identified these as good bones. Preserve them
through the migration:

- **Centralized constants.** One file, one set of parameters, versioned.
- **Tier policy asymmetry.** Rule-based source-tier assignment with
  LLM-downward-only adjustment. The LLM can argue a source is *less*
  reliable than the rules say, never *more*. This is asymmetry by
  design — it prevents the LLM from rationalizing weak sources upward.
- **Cross-domain connector grounded in embedding search.** The
  connector role finds links between domains via actual embedding
  proximity, not LLM imagination. The LLM proposes connections only
  among candidates retrieved from the embedding index.
- **TTL-per-claim-class staleness handling.** Different claim classes
  have different time-to-live values (market data goes stale fast;
  fundamental-physics constants don't). The temporal middleware applies
  the right TTL based on claim class.

The single architectural debt to pay down in this migration is
prose-enforced phase orchestration. Don't carry it forward.

---

## 5. Build priority — consume first, create second

Revised 2026-05-16 once the operator articulated the consume-first
direction explicitly. The earlier scaffolding pass deferred *both*
surfaces; that was wrong. Consume is the priority because (a) it
populates the graph that create later renders from, and (b) the
human-AI wrestling on documents is itself the on-policy trajectory
data that makes the autonomous version of the same loop trainable.

**P0 — substrate (no surface).** Event log, constants, db_lock,
graph operations, attribution, dispatch router. Direct migration from
Researchmaxx with one extension: the wrestling event vocabulary added
to `substrate/schemas/actions.py` (see §9 below) lands at substrate
time, not surface time.

**P1 — Loop 1: cold deep research.** The Researchmaxx 9-phase
autonomous flow ported to Antiek. Two-question input → defensible
synthesis output. Roles, middleware, orchestration, archive — direct
migrations with the `orchestrate.py` monolith split.

**P2 — Loop 2: document wrestling.** This is the new surface and the
differentiator. PDF render + chat panel + selection-to-question +
streaming background note panel + question-highlight overlay +
cross-document question→answer linking. `interfaces/reading/` and
`processing/note_taking/` are the homes; both are net-new code.

**P3 — Loop 3: trajectory consumption (RL).** No surface — the event
log captured during Loops 1 and 2 is the training data. SFT first,
hosted RL via Prime Intellect second. Deferred until enough wrestling
trajectories accumulate to be worth training on.

**Deferred until consume is in production:**

- **DeepBlu interview surface** (`acquisition/interview/`,
  `interfaces/interview/`, `skills/interview/`, `roles/user_agent/`,
  the Rust prosody crate, voice-realtime integration). The same
  graph-population mechanic as document wrestling, but on a different
  acquisition surface. Wait until the graph + create loop is stable.
- **Creation surface** (`interfaces/creation/` — outline editor with
  lego-block assembly, instant prose/chart generation). Deferred not
  because it's hard but because there's nothing in the graph to
  assemble until Loop 2 has populated it for a while.
- **Training and fine-tuning.** Event logs are captured (they are the
  eventual training data) but no training happens in this build.
- **Local model hosting.** All calls go through APIs. The dispatch
  router has the abstraction in place for local backends later.
- **Compounding-skill content quality verification.** The audit
  verifier in `compounding/verification/` diffs file sizes and alerts
  on non-growth, but does NOT evaluate the quality of what was added.
- **Self-improving skills.** Infrastructure exists for system-proposed
  codification, but proposals route to human review.
- **Public-facing monetization.** Attribution infrastructure exists
  (needed for honest synthesis anyway). No monetization logic.

---

## 6. The validation criteria for the eventual hardware decision

This build runs on rented compute for 9–12 months. The decision to
purchase hardware depends on validated criteria, not projected workload.
The system is instrumented to measure five criteria automatically:

1. **Token volume.** Daily consumption by role and provider. Break-even
   for Sparks ownership is roughly 50M tokens/month sustained on
   workloads two Sparks can serve. Three consecutive months above the
   threshold strengthens the case.
2. **Latency sensitivity.** Per-investigation wall-clock time by phase.
   If subscription-routed verification adds enough latency to break
   workflows, the local-verification case strengthens.
3. **Multi-tenant pressure.** Concurrent investigation count and
   rate-limit-hit frequency. Binding rate limits strengthen the
   local-hosting case (removes the rate-limit dependency).
4. **Skill development.** Has the operator developed enough technical
   fluency to extract value from owned hardware? Subjective but real.
5. **Skill compounding (new).** Are domain and process skills actually
   growing in usefulness, not just in size? Measured by the average
   constraint-check pass rate, synthesis archive rate, and backtest
   outcome correlation per skill version. If skills compound correctly,
   newer versions produce better outcomes. Mechanical growth without
   substantive improvement is a red flag.

Monthly reports against these criteria go to a stable location for
operator review. The build's job is to produce empirical data, not to
validate any particular hardware outcome.

---

## 7. Schema discipline

The structured schemas in `substrate/schemas/` are the eventual training
data format. Underspecified schemas now produce uncurated event logs
later, which produce bad training data, which produce bad models.

Spending an extra week getting the schemas right is high-leverage work.
Treat schema changes as load-bearing API changes: they require version
bumps, migration paths for prior events, and explicit reasoning.

---

## 8. The substrate matters more than any surface

If we ever have to choose between shipping a polished interview
workflow with a weak substrate versus a clean substrate with a
functional-but-rough interview workflow, choose the second. The
substrate is what compounds. The surface applications are replaceable.

---

## 9. The wrestling loop and its event vocabulary

Loop 2 (document wrestling) is what Antiek differs from Researchmaxx on:
the user pastes a PDF, asks for distillations, pushes with specific
questions, challenges the grounding of facts. A background note-taker
captures emergent truths into a compressed reminder doc. Questions
identified mid-wrestling get highlighted on the source. When a question
in document A is answered by wrestling with document B later, the graph
records the link.

The wrestling loop is not a UI feature glued on top of Researchmaxx —
it is a new acquisition path into the graph, and it earns the same
event-log discipline as everything else. **Neither Researchmaxx nor
DeepBlu has this vocabulary today.** Adding it at substrate time, not
surface time, is what makes Loop 3 (RL trajectory consumption) viable
from day one.

### 9.1 Wrestling event action types

Added to the `ActionType` enum alongside the inherited Researchmaxx
vocabulary. Stable string values; never repurposed.

```
# Document loading and surface state
document.loaded                 a PDF or pasted text entered the workstation
document.region_selected        user highlighted a region (chunk anchor)

# Distillation and challenge
distillation.requested          "distill this section/document for me"
distillation.delivered          model returned a distillation
claim.challenge_raised          "is that really true?" / "show me where"
claim.grounding_check_passed    grounder role located the claim in source
claim.grounding_check_failed    claim could not be located in source — flag

# Emergent notes (the background note-taker)
note.emerged                    a new compressed-truth note crystallized
note.refined                    an existing note was rewritten as understanding grew
note.compressed_doc_written     the per-document reminder doc was materialized

# Questions as first-class artifacts
question.identified             a question arose mid-wrestling; highlighted on doc
question.escalated_to_research  user launched deep research on this question
question.resolved_by_doc        an answer note was created with the question linked

# Cross-document graph linkage
cross_doc.question_answered     question from doc A answered by note from doc B

# RL signal capture
user.accept_distillation        user accepted the distillation as-is
user.reject_distillation        user rejected — counter-trajectory data
user.edit_distillation          user edited — preference signal
```

These are emitted by `interfaces/reading/` into the same Parquet
trajectory store as Loop 1 events. Policy_id stamps the model that
produced each artifact, which is what lets the eventual RL pipeline
exclude closed-weight trajectories from open-weight training.

### 9.2 Why this is RL training data, not just telemetry

The Cursor-for-code analogy is exact: a developer accepting,
rejecting, or editing a code suggestion is on-policy supervised data
for the model that produced the suggestion. Antiek's equivalent: a
user accepting, rejecting, or editing a distillation, challenging a
claim, or escalating a question to research is on-policy supervised
data for the model that did the wrestling. The pipeline:

1. Loops 1 and 2 emit typed events with `policy_id` stamping.
2. Successful trajectories (synthesis archived, distillation accepted,
   question resolved) → positive trajectory.
3. Rejected/edited steps → negative or contrastive trajectory.
4. Filter by `policy_id` to keep open-weight training data clean.
5. SFT first (the open-weight policy mimics successful trajectories);
   RL via Prime Intellect when the SFT plateau is observable.

The substrate is built so that turning this on later is a query
against the existing event store, not a re-instrumentation pass.

---

## 10. The unified create loop — lego blocks from the same graph

Create (deferred per §5) is the same graph rendered out, not a separate
data path. Spelling this out now so the substrate decisions stay
coherent with it later:

1. **Graph as truth set.** Notes emerged from wrestling (§9), facts
   extracted from sources, syntheses archived from deep research —
   all are graph nodes with attribution, tier, and TTL. The graph is
   the comprehensive note-taking layer the operator described.
2. **Outline as traversal, not authoring.** The user (or an LLM, or
   both collaboratively) selects starting nodes and arranges them as
   a flow. The outline is a sequence of graph-node references plus
   transitions, not prose. This is the lego-block assembly.
3. **Prose/charts/figures generated post-flow.** Once the truth-flow
   is determined, generation is fast and reproducible — the model is
   filling in language, not deciding substance. The substance is
   already locked in the graph.
4. **Interview is the same flow, different acquisition.** DeepBlu's
   future surface is identical to this except the lego blocks come
   from interview-turn nodes. The "superhuman interviewer" property
   the operator described is the interviewer querying the
   project-scoped graph between turns to know what's covered and
   what's missing — i.e., the AI interviewer is itself a consumer of
   the same graph the deliverable is built from.

This is why creating a polished create surface before the graph is
populated would be premature: there is nothing to assemble. Loop 2
fills the graph; create renders from it.

---

## 11. Polyglot seam: where Python meets TypeScript

Decided 2026-05-16. Antiek is polyglot — Python for the substrate,
TypeScript + React for the reading surface — and the seam is the
event stream, not a shared business-logic layer.

**Why not Python-only.** NiceGUI/Reflex are React-under-the-hood with
Python ergonomics on top. They trade away the leverage the reading UI
specifically needs (selection geometry, streaming overlays, multi-region
updates synchronized across chat/notes/highlights) without buying back
operational simplicity — their escape hatch is still TS, so a future
polish pass spills out of the wrapper. HTMX is brilliant for inspection
surfaces but overstretched for the concurrent choreography Loop 2
requires.

**Why not tRPC / GraphQL.** Over-machinery for the shape of the seam.
WebSocket-for-events plus REST-for-mutations stays closest to the
event-log discipline and prevents a second source of truth from
emerging in a TS schema layer.

### 11.1 The boundary

- **Python substrate** runs as a FastAPI app at
  `interfaces/research/api/`. Surface area:
  - One typed WebSocket: the live event feed. Clients subscribe per
    investigation and receive every event as it lands.
  - A small REST surface: POST wrestling actions (which translate
    to typed events), GET graph queries, GET archived syntheses.
- **TypeScript surface** lives at `apps/reading/` as a sibling to the
  Python packages, *not* inside `interfaces/`. Vite build, Vitest tests,
  React + pdf.js + Tailwind. The surface does exactly two things:
  1. Translate DOM events (selection, click, keypress) into typed
     substrate events posted to the API.
  2. Render substrate events into DOM updates (PDF highlights, chat
     bubbles, streaming note panel).
- **Schema source of truth: Pydantic models in `substrate/schemas/`.**
  A codegen script at `tools/codegen/` reads them and emits
  `apps/reading/src/generated/types.ts`. CI fails when the generated
  file is stale. There is no second schema definition on the TS side.
- **`pyproject.toml` stays Python-only.** `apps/reading/package.json`
  is its own workspace. A top-level `justfile` exposes `just dev` to
  bring both processes up.

### 11.2 The discipline

The polyglot decision survives only if the seam stays narrow. The
rule: if a TS function cannot be described as "translates DOM events
into typed substrate events" or "renders substrate events into DOM
updates," it does not belong in the TS package. No Prisma sharing
types with Pydantic, no business logic crossing the seam in either
direction, no clever helpers that mediate between the two languages.

This is the framework/product distinction applied at the language
boundary: Python is the framework (where intelligence compounds), TS
is the product surface (where the human acts), the seam is auto-
generated and narrow. Swapping React for Tauri later — or for a CLI,
or for a Reflex prototype — should not require a substrate change.

---

## 12. Build sequencing — the next four weeks

This is the concrete sequence Loops 1 and 2 follow from the just-landed
substrate (constants + db_lock + event_log).

### Week 1 — Dispatch + context pack

`substrate/dispatch/` and `substrate/context_pack/` land in parallel,
meeting only at the role call site. Build order inside dispatch:

1. The signature: `dispatch(prompt, role, max_tokens, verification_required, context_pack) -> response`.
2. Provider ABC plus two adapters — one OpenAI-compatible (base URL →
   DeepSeek / MiMo / Prime / OpenAI), one Anthropic.
3. Role → tier lookup against `constants.DEFAULT_ROLE_TIER` overridden
   by `dispatch/config.yaml`.
4. Cost-tracking decorator that emits `ActionType.DISPATCH_CALL` with
   provider, model, tier, role, input_tokens, output_tokens, cost_usd,
   latency_ms.
5. Fallback chain exercised from config.
6. Three tiers wired: flash, synthesis, verify-as-synthesis-alias.
   Pro and local alias to synthesis until they earn separation.

`context_pack` does not import dispatch. Dispatch does not import
context_pack. Verified by an import-cycle test in CI.

Exit criterion: a role can call `dispatch()` and a `dispatch.call`
event lands in the log with full cost payload.

### Week 2 — FastAPI substrate + codegen

`interfaces/research/api/` exposes the WebSocket event feed and the
small REST surface. `tools/codegen/` emits `apps/reading/src/generated/
types.ts` from `substrate/schemas/`. CI gate on staleness.

Exit criterion: `just dev` brings up the Python backend. `curl` can
POST a wrestling action; subscribing to the WebSocket shows the
matching event arrive.

### Weeks 2–3 (parallel) — Reading surface bare-bones

`apps/reading/` scaffold: pdf.js render, selection emits
`document.region_selected`, chat panel posts `distillation.requested`,
streaming response is rendered. Not polished — proves the loop closes.

Exit criterion: paste a PDF, highlight a paragraph, ask for a
distillation, see streaming output, confirm the full event trail
lands in the trajectory store.

### Weeks 3–4 — orchestrate.py extraction (serial, with golden traces)

Capture 2–3 historical investigation traces from the existing
Researchmaxx end-to-end. Hash every input and output. These become
integration tests. Then extract one role at a time and assert the
trace still replays (bit-identical where deterministic, structural
equivalence where LLM nondeterminism intrudes).

Order: decomposer (smallest seam, learn the pattern) → evidence_retriever
→ parameter_extractor → connector → synthesizer (last; most state).
**Do not parallelize.** The first extraction teaches the seam pattern;
each subsequent one is cheaper if you wait.

Exit criterion: Loop 1 runs end-to-end through `roles/*/` instead of
`orchestrate.py`. Golden traces match.

### Weeks 5–6 — Wrestling roles

`roles/challenger/`, `roles/grounder/`, `roles/note_taker/`. These are
event-driven, single-purpose, no multi-step orchestration — simpler
than the four embedded in `orchestrate.py`. They can be built in
parallel with the orchestrate.py extraction since they share no code
and no contention. Calling them out in their own week here only
because Loop 2 cannot demonstrate the full wrestling experience until
they exist.

### Week 7 — Cross-document question→answer linking

The graph already supports it (search.py, traverse.py migrated as
part of substrate). What's net-new is the watcher that listens for
`question.identified` events on doc A and emits
`cross_doc.question_answered` when a `note.emerged` on doc B answers it.

Exit criterion: a question raised while wrestling doc A and answered
later while wrestling doc B is rendered as a connection in the graph
view, and the linkage was emitted as a typed event captured in the
trajectory.

### What this budget assumes

7 weeks to "Loops 1 and 2 in production with wrestling trajectories
accumulating" is realistic only if the polyglot boundary holds at the
event stream. Move it anywhere else — tRPC, GraphQL, Prisma sharing
types with Pydantic, shared business logic in either direction — and
the same work takes twice as long. The substrate decisions in §2 are
correct precisely because they treat the framework as the compounding
artifact. The reading UI of December 2026 will look nothing like the
one built in week 3. The event vocabulary, if locked correctly now,
will look exactly the same — which is what makes the trajectories
captured this month worth training on next year.

---

## 13. HTML and rendering — four layers, four answers

The argument for HTML-as-agent-output (Thoric / Karpathy on the
one-shot interactive artifact) is correct for the use case they
describe: a presentation artifact that opens in a browser, is shared
via S3 link, read once, thrown away. Antiek has a *different* problem,
which is that the agent's outputs are simultaneously:

- event payloads (training data for tomorrow's policy),
- graph contributions (compounding substrate),
- shareable artifacts (the surface a user reviews).

HTML-as-agent-output dissolves all three. A distillation stored as
``<div><h2>...</h2><p>...</p></div>`` cannot have its claims extracted
into typed nodes, cannot be diffed against another distillation,
cannot be replayed, cannot be trained on. The schema-discipline
argument in §7 applies verbatim: HTML inside an event payload is the
same failure mode as ``dict[str, Any]`` inside an event payload.

**The rule.** Structured everywhere the agent touches; HTML everywhere
the human looks. The two meet at exactly two boundaries — the React
surface and the archive export — and never blur in the substrate.

### 13.1 The four layers

**Layer 1 — Substrate payloads. Pydantic, never HTML.**

The wrestling roles emit ``Distillation(claims=[Claim(text=...,
confidence=..., attribution_region_ids=[...])])``, not an HTML string.
``DistillationDeliveredPayload`` carries ``claims: list[Claim]`` plus a
``rendered_text: str`` for the prose rendering and a
``rendered_text_hash`` for dedup. The structured claims are what gets
extracted to the graph; the rendered_text is what the reading UI
displays. This is non-negotiable.

**Layer 2 — Reading-surface rendering. HTML by virtue of React.**

The wrestling roles return typed payloads; React components render
them. Charts, side panels, highlight overlays, streaming note panels
— all HTML by construction because the surface IS HTML. No separate
decision; the polyglot seam in §11 already settled this. The flow is
Pydantic → JSON via the WebSocket event feed → TypeScript types
generated from the same Pydantic models → React renders.

**Layer 3 — Shareable exports. HTML, generated at the archive
boundary.**

Every archived synthesis has an HTML export pathway in
``middleware/archive/``. The Pydantic object is canonical; the HTML
is a view over it. The export renders the full attribution chain,
stamps the skill versions, and puts ``ANTIEK_PARAM_VERSION`` in the
footer. When the operator wants to send a synthesis to a colleague
or pin it on S3, the export step serializes — never the reverse.

**Layer 4 — Throwaway exploration artifacts. HTML referenced by ID,
not inlined.**

This is where the Thoric / Karpathy pattern is most powerful for
Antiek's specific build. Mid-wrestling, the agent generates an
interactive HTML playground — "six different framings of this
question" as a comparison grid, a knob-and-slider exploration of
how three competing claims weight, a Linear-style triage view for
the questions emerging from a document. These live on disk at
``~/.antiek/artifacts/<hash>.html``. The event log records the
structured intent:

```
artifact.generated(
    artifact_id=..., artifact_kind="comparison_grid",
    intent="show the four candidate distillations side-by-side",
    generating_role="note_taker",
    artifact_path="~/.antiek/artifacts/abc123.html",
    content_hash=..., size_bytes=..., source_event_ids=[...]
)
```

The HTML itself is opaque to the substrate. The user opens it in a
browser, interacts, and the interactions emit typed events back into
the log — ``user.accept_distillation``, ``claim.challenge_raised``,
``question.identified``, etc. The artifact's own lifecycle
(opened/closed/dismissed) emits ``artifact.interacted``. The HTML is
the canvas; the events are the signal.

### 13.2 Why Layer 4 is structurally distinct from Layer 1

The temptation will be to collapse Layer 4 into Layer 1 — "just store
the HTML in the event payload and call it a structured event." Resist
this. The structured intent (what the artifact is, why it was made,
what events it was generated from) is permanent and queryable. The
HTML rendering is ephemeral and replaceable — tomorrow it might be
React-rendered, the day after it might be interactive video (Karpathy's
direction). The substrate doesn't care; the renderer swaps without a
schema change. That property only holds if the HTML lives on disk and
the event holds the structured intent.

### 13.3 What this means for the schemas

The schemas in ``substrate/schemas/events.py`` enforce Layer 1
directly: ``DistillationDeliveredPayload.claims`` is a typed list,
not a string. The artifact pattern lives as two new action types:

- ``ActionType.ARTIFACT_GENERATED`` with ``ArtifactGeneratedPayload``
- ``ActionType.ARTIFACT_INTERACTED`` with ``ArtifactInteractedPayload``

Artifacts may be document-scoped or project-scoped, so artifact
events are NOT in ``WRESTLING_ACTION_TYPES`` — their envelope
``document_id`` is optional, set when the artifact references a
specific document, null otherwise.

The mental model to keep: structured intent in the log, HTML on
disk, React in the browser. The substrate never knows what HTML
looks like.
