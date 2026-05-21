# Antiek — Master Product Spec

**Status**: execution-ready master spec consolidating the operator's product
  vision across four voice-memo dictations on 2026-05-17, sharpened
  2026-05-18 with the four ratified integration specs (§17), reoriented
  to faithfully absorb the operator's vision on 2026-05-19 with the
  personal-graph-as-memory framing (§13.2), Surface E as operator's
  preferred product direction (§4.5), PostHog's design and UI philosophy
  as Antiek's design philosophy (§5.6), and the watch-for-later folder as
  curiosity-capture-as-primitive (§2.6). Sprint-by-sprint sequence at the
  end. Each sprint is independently scoped; each builds on what the prior
  sprints made possible.
**Audience**: any agent (or human) picking up Antiek's product work cold.
  After reading this spec, you should know what Antiek is, why it exists,
  what's already built, what comes next, and which decisions are
  load-bearing vs. cosmetic.
**Predecessor docs**: `architecture_notes.md` (substrate-level commitments),
  `strategy/voice-and-style-discipline.md` (voice + UI discipline),
  `sprints/sprint11-web-app-mvp.md` (first web-app sprint).
**Integration specs** (peer documents — each owns a ratified verdict
matrix for one external system or framework):
  - `integration_posthog.md` — UI/design/product/website patterns
    (Lemon UI, Notebooks, command palette, Max-style AI, trajectory
    replay, pricing-page template, handbook discipline)
  - `integration_autoresearch.md` — Karpathy's propose-execute-measure-gate
    loop applied to prompt mutation, Phase 8 gate, config sweeps
  - `integration_prime_intellect.md` — Verifiers env + GEPA + hosted RL
    (gated by `loop_3_unlock_criteria.md`)
  - `rlm_integration_spec.md` — Recursive Language Models for
    long-doc wrestling, long-corpus synthesis, RLM-mode orchestration
**Companion**: `infrastructure/SKILL.md` (production operations).
**Sub-document**: `loop_3_unlock_criteria.md` (5 gates for any
  training-time work).

---

## Table of contents

1. [Product thesis](#1-product-thesis)
2. [Conceptual primitives](#2-conceptual-primitives)
3. [What's already built](#3-whats-already-built)
4. [The five surfaces](#4-the-four-surfaces)
5. [Voice and style — non-negotiable quality bar](#5-voice-and-style--non-negotiable-quality-bar) *(includes §5.6 PostHog design philosophy as load-bearing)*
6. [Primary source connection](#6-primary-source-connection)
7. [Continuous research mode](#7-continuous-research-mode)
8. [Multimodal acquisition](#8-multimodal-acquisition)
9. [IP attribution + ad economics](#9-ip-attribution--ad-economics)
10. [Creation surface — writing tool](#10-creation-surface--writing-tool)
11. [DeepBlu — interview-as-acquisition](#11-deepblu--interview-as-acquisition)
12. [Voice note ingestion](#12-voice-note-ingestion)
13. [Account model + network effects](#13-account-model--network-effects)
14. [Sprint sequence (11 → 30+ mainline + parallel tracks)](#14-sprint-sequence-11--22-mainline--parallel-tracks)
15. [Strategic open questions](#15-strategic-open-questions)
16. [What we explicitly do NOT do](#16-what-we-explicitly-do-not-do)
17. [Integration spec hierarchy and precedence](#17-integration-spec-hierarchy-and-precedence)

*Section §2.6 (watch-for-later as curiosity-capture primitive), §4.5
(Surface E — Brainstorming Workstation as operator's preferred product
direction), §5.6 (PostHog design philosophy as Antiek's design philosophy),
§9.0 (legal gate binding now), §9.0.1 (operator's pay-as-you-go
token-budget pricing), §13.2 (personal-graph-as-memory architecture),
§13.6 (substrate transition matrix), §13.7 (consumer privacy compliance),
§13.8 (Antiek Memory developer surface), §14.4 (dispatch tier measurement)
were added or sharpened in the 2026-05-18 → 2026-05-19 evolution to
faithfully reflect the operator's voice notes and the four integration
specs (PostHog, autoresearch, Prime Intellect, RLM).*

---

## 1. Product thesis

**Reading-for-understanding has a different cognitive shape than
reading-for-pleasure, and LLMs make it possible to compress hundreds of
sources at speed without losing the per-source provenance that makes
research trustworthy. Antiek is the workstation that operationalizes
this — Cursor for knowledge work.**

Operator's framing (2026-05-17): *"It's effectively operating with a
thesis that reading, the experience of reading and information
ingestion could be thought of very, very differently and the
information economy could be really, really transformed with a very
cursor-like experience to research and knowledge work."*

Three things distinguish Antiek from the existing landscape:

**1. Recursive note-taking as the core engine.** Every document the
substrate touches gets distilled into two buckets — `insights`
(verified takeaways) and `open questions` (gaps the document didn't
address). The open questions become new triggers for new research
chains. The graph grows compoundingly across investigations.

**2. Voice and style discipline as a quality gate.** Most LLM-mediated
research tools produce em-dash–laden bulletized slop that the reader
skims rather than absorbs. Antiek's prose has to feel like a
researcher's notebook entry, absorbing the source corpus's vocabulary
and argumentation. This is non-negotiable; product fails without it.

**3. Two products in one substrate.** Consumption (research from a
question or document) and creation (writing books / memos / biographies
from accumulated insight blocks). Both share the same underlying graph,
the same insight/question note structure, the same source attribution.
The DeepBlu AI interviewer is the multi-party acquisition channel for
the creation surface.

The eventual economics layer — banner ad attribution that pays IP
holders for the chunks contributing to insights — is novel mechanism
design and a strategic call. Documented in section 9. Not the
immediate path.

**The architectural analog is Cursor, but only at the inference layer.**
Antiek's substrate is the moat (§2.5); Cursor's substrate is Anysphere's
own IDE plugin. The analogy holds at the inference layer (route to
external providers via dispatch with Hermes-primary + OpenRouter fallback
per §3.1, charge for workflow value, do NOT train foundation models)
but breaks at the substrate layer (Antiek's typed event log + graph +
dispatch + verifier-shaped roles + skill-patching is what compounds;
Cursor's IDE plugin is replaceable in a quarter). Treating Antiek as
"Cursor for research" misses that the substrate IS the product. Treating
Antiek as "Spotify for knowledge" pulls Phase 3 IP economics forward
into Phase 0, which is the failure mode the Bartz precedent now prices
at $3,000 per ingested work (§9.0).

---

## 2. Conceptual primitives

These are the load-bearing concepts every feature in the spec reduces
to. Understanding them in this order is the fastest way to internalize
why Antiek's architecture is shaped the way it is.

### 2.1 The insight/question structure

Every document the substrate processes — academic paper, textbook
chapter, YouTube transcript, podcast, X thread, interview transcript,
operator voice note — produces structured notes in exactly two
categories:

- **Insights**: distilled claims with chunk-level citations to the
  source. Each carries a confidence assessment, a source tier (1=peer-
  reviewed primary, 5=anonymous/aggregator), and the specific chunks
  supporting it.
- **Open questions**: gaps the document raises but doesn't answer.
  Tagged with category (parameter_extraction, mechanism, cross_domain,
  etc) and evidence type needed (quantitative, qualitative, mixed).

This is the substrate's mental model of "what does it mean to read a
document?" The same shape applies regardless of source type. The same
shape applies regardless of whether the trigger was a cold question
or a document drop.

Substrate today: `evidence_retriever` role produces this shape per
sub-question (`supporting_claims` + `evidentiary_gaps`). The
note_taker role produces it on wrestling events. The `Claim` and
`Question` Pydantic schemas in `substrate/schemas/events.py` are the
canonical type definitions.

### 2.2 The recursive chase loop

Open questions don't just sit there. They become triggers for new
research chains:

```
                  question or document
                          │
                          ▼
                  ┌───────────────┐
                  │ Investigation │
                  │  (Loop 1)     │
                  └───┬───────────┘
                      │ produces
                      ▼
        ┌─────────────────────────┐
        │ insights + open questions │
        └─────────┬───────────────┘
                  │
       ┌──────────┼──────────┐
       │          │          │
       ▼          ▼          ▼
   ┌───────┐ ┌───────┐  ┌───────┐
   │ child │ │ child │  │ child │
   │ inv 1 │ │ inv 2 │  │ inv 3 │
   └─┬─────┘ └─┬─────┘  └─┬─────┘
     │         │          │
     │  (each spawns its own insights + open questions)
     │         │          │
     ▼         ▼          ▼
   more     more       more
   children children   children
```

The chase can be operator-driven (highlight a paragraph in a synthesis,
click "chase this") OR autonomous (continuous mode in section 7 walks
the open-question backlog automatically until a stop condition).

Substrate today: `cross_doc.question_answered` events already link
questions to answering documents. The chase mechanic is partially
there; what's missing is (a) UI to surface the chase tree and (b)
substrate config to drive autonomous chasing.

### 2.3 The graph as accumulating product

Every investigation contributes nodes, edges, chunks, and tier-scored
claims back into a shared graph. The graph is the operator's
*compounding asset* — investigation N+1 is faster, cheaper, and more
substantive than investigation N because it can draw on what
investigations 1...N already produced.

Storage: DuckDB on the production VM. Tables: `documents`, `chunks`,
`nodes`, `edges`, `syntheses`, `synthesis_substrate_manifest`,
`outcomes`, `chunk_tier_overrides`. Plus the append-only typed event
log at `~/.antiek/research_events/*.jsonl`.

This means **the radar corpus the operator ingested on their Mac is
different from the corpus on the production VM**. Each instance has
its own graph. Cross-graph network effects come later (section 13).

### 2.4 Synthesis as the human-facing artifact

The end of every investigation is a `MASTER.md` — a structured
synthesis with thesis components, falsification conditions, execution
risks, citations to specific chunks. This is what the operator
reads. This is the rendering target for the consumption-side web app
in section 4.1.

The substrate already produces this via `skills/domain/master_md.py`.
The MASTER.md is generated from the archived `SynthesisArchivedPayload`
+ the role outputs along the trajectory. **The rendering can be
non-destructive (markdown for reading) while the underlying structure
stays first-class (claim spans with chunk IDs).** See section 5 on
voice and style for how the prose itself gets shaped.

### 2.5 The substrate is the moat, not the UI

Twelve sprints of work went into the substrate. The web app
(Sprint 11) is a thin renderer over an API. The substrate's
defensibility is:

- **Recursive note-taking with provenance preserved** through chunk-
  level citation graphs. Most "AI research" tools produce ungrounded
  output; Antiek can always answer "where did this come from?"
- **The accumulating graph**. Investigation N+1 is genuinely cheaper
  and better than N because the substrate composes prior work.
- **The compounding skill layer** (Phase 8 auto-patches domain
  knowledge skills). Each investigation makes the operator's
  knowledge skill in that domain stronger.
- **The voice and style discipline** that makes the output something
  the operator actually wants to read.

UI competitors are months away. Substrate competitors are years away
because building the typed event log + dispatch routing + 8-phase
orchestration + verifier-shaped role environments takes the
12-sprint cycle Antiek already paid.

The UI is how the operator interacts with the moat.
`integration_posthog.md` (§17) is the best-in-class reference for
that interface layer specifically. Borrow its patterns where they
fit the researcher's-notebook identity; reject loudly where they
don't (§16.1). The substrate is the end; UI patterns are the means.

**The Cursor architectural analog applies to inference routing, not to
the substrate.** Cursor pays OpenAI and Anthropic for inference, wraps
the workflow, charges users for the wrap. Antiek does the same at the
inference layer via dispatch with Hermes-primary + OpenRouter fallback
(§3.1). Cursor has no substrate — the IDE plugin is its product. Antiek
has a substrate that compounds across investigations, and that substrate
is what defends the product against the "ChatGPT can do this now"
question that every Cursor competitor faces. Adopting the Cursor mental
model wholesale would mean treating the dispatch layer as the product,
which is exactly the inversion that the substrate-is-moat thesis
prohibits. Cursor reached gross-margin profitability in April 2026 only
after shipping its own inference model (Composer); at Antiek's scale
owning the inference model is not feasible in Phase 1. The available
levers are routing intelligence (cheap models for routine steps,
expensive models for synthesis only — see §14.4 tier-differentiation
measurement) and aggressive prompt caching.

### 2.6 The watch-for-later primitive — research is curiosity-gated

Operator vision (voice notes 2026-05-17): a brainstorming workstation
where the operator parks unsharpened questions throughout the day,
talks to their notes, slots insights like Legos, and on the operator's
go-ahead launches a research chain on a parked question.

This is a product insight, not a feature. **Research is gated by
curiosity, not by tooling.** Curiosity surfaces in fragments throughout
the day — reading another paper, in a conversation, in a voice note.
Currently the operator parks those fragments in a notes file, a browser
tab, or nothing. The platform that solves the parking problem captures
the moment curiosity becomes investigable.

Operator verbatim on the deeper insight: *"having that folder of
rough ideas that are not sharpened yet can help a user extract their
curiosity and encode it in technology."* **The watch-for-later folder
is curiosity-capture-as-primitive**, not just a UI affordance. The
mechanism the platform provides is: a place to put a half-formed
thought, the ability to refine it later via voice or thought-partner
workflow, and the ability to launch a full research chain on the
sharpened version when ready. The curiosity is the operator's; the
encoding-in-technology is what Antiek provides.

**Substrate mapping**: voice notes already work (Sprint 13). Open
questions are already first-class objects in the graph
(`question.identified` events). The "watch-for-later" folder is a UI
on top of `QuestionIdentified` events filtered by an `unsharpened`
state. The "launch investigation" affordance posts to `/investigations`
with the parked question as the seed. The thought-partner workflow
(slot notes, challenge them, voice-note follow-up) is a new role
under `roles/` that takes a set of operator-selected notes plus a
prompt and produces challenges, syntheses, or extensions.

**Why this matters strategically**: the brainstorming workstation is
where private graph usage happens. Research workstation drives public
graph contribution. Brainstorming workstation is where users park
their actual thinking, which is what they don't want to share.
**This is the surface that justifies the 50% margin on private tokens
(§13.5) because it's the surface where users will pay to keep their
thoughts private.**

Sprint placement: Sprint 17 or 18 product surface depending on
mainline-work capacity. Builds on existing voice notes + open-question
events; no new substrate primitives required.

---

## 3. What's already built

This section is **status as of 2026-05-17** so any agent reading
this spec knows what doesn't need to be re-derived.

### 3.1 Substrate (1386 tests passing as of commit cd602c9, 2026-05-18)

- **Event log**: typed Pydantic schema with 61 ActionTypes; canonical
  source `substrate/schemas/events.py`; append-only `.jsonl` storage.
- **Dispatch**: provider-agnostic routing via `substrate/dispatch/`.
  **Hermes-primary posture (Sprint 12+):** all flash/pro/synthesis/verify
  tiers route to `hermes / grok-4.3` (xAI via the Hermes Agent OAuth
  bridge — see `antiek-hermes-bridge` memory) with OpenRouter (DeepSeek-Flash,
  DeepSeek-Pro, Claude Opus 4.7) as fallback. Verify-tier fallback
  chaos-tested at `tests/test_dispatch_fallback_chain.py` (Sprint 16,
  commit cd602c9). Cost tracked per call, emitted as `dispatch.call`
  events. Fallback chain with `--workers 1` enforced.
- **Context pack**: layered prompt assembly with budget enforcement
  in `substrate/context_pack/assembler.py`. 3 truncation strategies.
- **Graph schema**: DuckDB with `documents`, `chunks`, `nodes`,
  `edges`, plus Sprint-10 additions for `syntheses`,
  `synthesis_substrate_manifest`, `outcomes`, `chunk_tier_overrides`.
- **12 roles**: decomposer, evidence_retriever, parameter_extractor,
  connector, synthesizer (the 5 orchestrate.py originals) +
  challenger, grounder, note_taker, user_agent + creative_writer
  (Sprint 13), interviewer (Sprint 16), voice_note_followup (Sprint 13).
- **Loop 1**: 8-phase autonomous research chain via
  `orchestration/loop_one/orchestrator.py`. End-to-end validated on
  real LLMs.
- **Loop 2**: document wrestling (region-select → distillation →
  claim cards → challenge → grounder → note-taker → cross-doc
  linking). Existing `apps/reading/` TS surface.
- **Middleware**: source_tier, temporal staleness, archive,
  supersession, constraint_check (loop machinery), backtest,
  cohort, outcomes.
- **Skills**: domain (extract + auto-patch + MASTER.md generator),
  verification (rubric registry + RLM-style claim verification).
- **Phase 8 compounding**: `skill.auto_patch_applied` mechanism
  writes extracted knowledge back into `<domain>-knowledge/SKILL.md`
  templates.
- **Acquisition**: arXiv + URLs + books (PDF). YouTube + podcasts
  + X + social are net-new (section 8).

### 3.2 Infrastructure

- **Production VM**: Hetzner CCX23 at 167.235.202.98, Falkenstein.
- **DNS**: `api.antiek.ai` direct, `app.antiek.ai` CNAME to
  Cloudflare Pages.
- **TLS**: Let's Encrypt via Caddy reverse proxy, 900s timeouts.
- **Backups**: nightly DuckDB EXPORT DATABASE + event log rsync to
  R2 (`antiek-backups`, EU region), 14-day retention.
- **IaC**: Terraform + Ansible at `infrastructure/`. Single
  `ansible-playbook deploy.yml` ships a code change end-to-end with
  health-check assertion.

### 3.3 The reading UI (`apps/reading/`)

- Vite + React 18 + TypeScript strict + Tailwind + pdf.js.
- Loop 2 workflow: load PDF → region-select → distillation request
  → claim cards with confidence badges → challenge button →
  grounder verdict (✓/⚠) → note-taker insights → cross-doc question
  links.
- Codegen at `tools/codegen/emit_types.py` produces TS types from
  Pydantic. CI gate via `check_staleness.py`.

### 3.4 What's NOT yet built

Status as of 2026-05-18, organized by which spec covers each item.

**Covered by this master spec's sprint sequence (§14):**

- Interview voice mode — WebRTC + TTS + streaming whisper (Sprint 17)
- **Dispatch tier-differentiation measurement gate** — synthesizer pinned
  to Opus primary for 2-week measurement against Hermes/Grok on verifier
  pass rates (Sprint 17, §14.4)
- **Watch-for-later folder / brainstorming workstation** (§2.6;
  Sprint 17 or 18 product surface — voice notes + open-question events
  already exist as substrate primitives)
- Publisher dashboard + Stripe Connect (Sprint 18, §9 Phase 2)
- **Retrieval-time gating for restricted content** (Sprint 18
  PREREQUISITE per §9.0 legal gate — restricted-class content cannot
  be retrieved into syntheses that trigger attribution)
- **Operator's pay-as-you-go pricing model** — three-tier token-budget
  pricing (free public capped DeepSeek-Flash / above-cap paid public
  10% margin / private 50% margin) + 70% creator rev-share on ads +
  Antiek Memory developer API/MCP/CLI usage-based (§9.0.1 / §13.5;
  Sprint 19+). OpenRouter-style "user sets budget, billed for actual
  usage." Audience: anyone doing knowledge work — researchers, writers,
  students, journalists, analysts, founders, hobbyists, curious
  individuals
- **Antiek Memory MCP server** as primary developer surface — three
  resources (private notes, public notes, books) + four tools, signed
  tool descriptions, prompt-injection envelopes (Sprint 19-20, §13.6)
- Synquery expert-network integration (Sprint 20-21, **NOT Sprint 18**
  per §14.1 split — gated on creation surface PMF signal)
- Trajectory replay viewer (Sprint 20, PostHog Wedge 5)
- **Multi-user accounts + two-graph architecture (private + public + shared
  substrate)** with substrate stage transition (Sprint 22+, **NOT
  Sprint 19**; gated on six months of demonstrated solo compounding
  per §13.4)
- Phase 4 lead-gen ad inventory (Sprint 21-22)
- IP attribution payouts (telemetry shipped Sprint 16; payouts ship
  ONLY after retrieval-time gating in production AND first publisher
  opt-in per §9.0)
- **Ad-supported public-tier consumption with 70% creator + 70%
  publisher rev-share** (operator's three-tier pricing model §13.5;
  free public tier ships Sprint 19, ad inventory live Sprint 25+)
- **Pre-onboarded IP holder escrow framework — Kalshi pattern**
  (operator-decided per §9.10). Architecture ships Sprint 18 alongside
  publisher dashboard. First-cohort notification outreach Sprint 19
  (MIT Press, Cambridge University Press, Princeton University Press
  first; Big Five last per §9.10). Cash-only, segregated regulated
  accounts, opt-in only, costless 30-day opt-out. **Payouts gate
  strictly on publisher opt-in** — escrow accrues from Sprint 19 but
  no money routes until first opt-in
- **Consumer privacy compliance + Trust Center** — GDPR + CCPA notice;
  Trust Center publication by Sprint 22; engineering-grade privacy
  architecture (DP, two-graph, privacy dashboard per §13.3). Substrate
  trust controls (encryption-at-rest, access logging, change management,
  vulnerability scanning, backup testing) ship Sprint 16-18 hygiene
  regardless. **SOC 2 Type II is deferred** unless enterprise procurement
  ever becomes relevant — not required for consumer Phase 1 (§13.7)
- Cross-graph network effects + federation (Sprint 30+)

**Covered by `integration_posthog.md`:**

- Storybook scaffold for design-system documentation (Wedge 1a,
  Sprint 17 half-day)
- Lemon UI evaluation decision (Wedge 1b, Sprint 17 spike)
- **Notebook surface for Loop 2 — the linchpin** (Wedge 2,
  Sprint 18-19 main work, ~10 days)
- Universal Cmd+K command palette (Wedge 3, Sprint 19-20)
- Max-style ubiquitous AI assistant with UI-action capability
  (Wedge 4, Sprint 19-20, requires undo affordance through the
  event log)
- rrweb-concept trajectory replay viewer (Wedge 5, Sprint 20,
  requires Wedge 2 block renderers as render target)

**Covered by `integration_autoresearch.md`:**

- `program.md` per role module (INTEGRATE NOW, Sprint 17 half-day)
- Prompt autoresearch loop for synthesizer (Wedge 1, Sprint 19
  parallel side-track, local-only)
- Phase 8 skill-patch accept/reject gate (Wedge 2, Sprint 20+
  shadow-mode → Sprint 21+ enforcing, gated on Wedge 1 ratifying)
- Context-pack + dispatch config sweeps (Wedge 3, DEFER until
  ≥500 graded outcomes in cohort)
- Local SFT loop using autoresearch's shape (Wedge 4, DEFER behind
  `loop_3_unlock_criteria.md`)

**Covered by `integration_prime_intellect.md`:**

- Trajectory→verifiers schema compat test (item F, debt — absorb
  Sprint 17 or 19)
- `prime eval run` runner for Antiek rubrics with
  `parameter_extractor_v0.jsonl` 50-example set (item D, debt)
- GEPA on `parameter_extractor` (item A, Phase 2 of Prime track)
- `verifiers` env stub for `parameter_extractor` (item B, Phase 2,
  substrate only, training forbidden until unlock)
- Hosted `prime rl run` (item E, DEFERRED behind
  `loop_3_unlock_criteria.md`)

**Covered by `rlm_integration_spec.md` (RLM track, parallel to mainline):**

- Long-doc wrestling RLM bridge (RLM-1, ~600 LOC, load-bearing)
- Long-corpus synthesizer RLM mode (RLM-2, ~250 LOC)
- `investigation_kind="rlm"` orchestrator (RLM-3, ~500 LOC, net-new)
- Verifiers envs for the other four roles + `rlm_env.py` (RLM-4,
  ~2000 LOC)
- Trajectory harvest CLI for `prime-rl` (RLM-5)

The integration-spec items run alongside (not blocking) the mainline
sprint sequence except where explicitly noted (Wedge 2 notebook is
mainline Sprint 18-19 work).

---

## 4. The four surfaces

Antiek's product is four distinct user surfaces, each grounded in the
same substrate. Build order is sections 4.1 → 4.4 in roughly that
sequence (with overlaps).

### 4.1 Surface A — Research Workstation (`app.antiek.ai/`)

**Status**: Sprint 11 build. Detailed spec at `sprints/sprint11-web-app-mvp.md`.

**What it is**: The chat-first research surface. Operator types a
question, the substrate runs Loop 1, streams the 8-phase trajectory
in real time, renders the MASTER.md synthesis at completion. Operator
can highlight any claim in the synthesis and "chase" it — spawning
a child investigation that runs on the same substrate with the
parent as context.

**Why first**: It's the operator's primary use case (investment
research). The substrate already produces the right artifact (MASTER.md).
The bottleneck is UX: today the operator runs Python scripts and reads
markdown files. The web app turns that into something usable.

**MVP scope** (Sprint 11):
- Chat input → POST /investigations
- Live trajectory view (phase-by-phase streaming via WebSocket)
- MASTER.md viewer with hover-citation on every claim
- Highlight-to-chase (spawn child investigation from selected text)
- Past-investigations sidebar with parent-child tree

**Deferred to follow-on sprints**: golden insight tagging, continuous
mode, multimodal acquisition UI, creation surface, account model.

### 4.2 Surface B — Document Wrestle (`app.antiek.ai/wrestle/`)

**Status**: Already built. Sprint 11 moves it into a `/wrestle` route
without behavior change.

**What it is**: The existing single-document deep-read surface. Load
a PDF, highlight regions to ask questions, see claim cards with
confidence badges, challenge claims to trigger grounder verdicts,
read emergent notes from the note-taker, see cross-doc question
links in the sidebar.

**Why preserve it**: The deep-read use case is genuinely different
from the broad-research use case. Operator described it explicitly:
*"if I wanted to start without starting with a question but start
with a document, I think the natural flow would be to take notes on
that document in this insights and open questions formatting."*

**Cross-mode connection (Sprint 11)**: From the chat-first surface
(A), clicking a chunk citation that points to a PDF document opens
the document in Mode B at the right page. From Mode B, an emergent
note that opens a cross-doc question spawns a Mode A investigation.
Same substrate, two reading modes, fluid handoff.

**Sprint 18-19 upgrade — the notebook surface.** The current chat-feed
in `NotesPanel.tsx` is the right baseline; PostHog Notebooks pattern
(`integration_posthog.md` Wedge 2) is the right ceiling. A TipTap-based
literate document combining region selections + claim cards + emergent
notes + cross-doc links + markdown prose + LaTeX as embeddable blocks.
Available at `/wrestle/<id>/notebook` alongside the chat-feed —
operator picks per use case. The notebook is the canonical render
target that Wedges 3 (command palette), 4 (ubiquitous AI), and 5
(trajectory replay) all build on. See §15.5 for the adoption open
question.

### 4.3 Surface C — Creation Workstation (`app.antiek.ai/write/`)

**Status**: Multi-sprint vision (Sprints 13-15). Detailed in section
10.

**What it is**: The writing surface. Operator's accumulated knowledge
graph becomes draggable "insight blocks" they arrange into a
deliverable outline. Each section gets a name + ordered blocks. The
substrate's `creative_writer` role expands the outline into prose,
anchored to the specific blocks. Edits at section / paragraph /
sentence / word level. Provenance preserved through edits.

**The strategic shape**: Antiek's consumption side produces the raw
material (the graph). The creation side is what the operator
*sells* — the deliverable artifact (book, memo, biography).

### 4.4 Surface D — Interview / Voice (`app.antiek.ai/interview/`)

**Status**: Multi-sprint vision (Sprints 16+). Detailed in section 11.

**What it is**: The acquisition channel for content that doesn't exist
as a document yet. Two modes:

- **Single-operator voice notes** (Sprint 13 simplest version):
  operator hits record, talks through an idea, transcription flows
  into the substrate's note-taking pipeline as a new ingested
  source. Same insight/question structure.
- **Multi-party interviews** (Sprint 16): operator generates an
  interview link, sends to relevant subjects, AI interviewer
  conducts the conversation, transcripts feed back into the
  substrate. Originally the "biography as a service" product
  concept.

### 4.5 Surface E — Brainstorming Workstation (`app.antiek.ai/brainstorm/`) — operator's stated preferred product direction

**Status**: operator-decided as the **preferred product direction**
in voice notes 2026-05-17. Operator verbatim: *"My thinking now is
that I would prefer to create my own brainstorming workstation
product where you can talk to your notes and slot some into focus
like legos and challenge them."* Sprint 17-18 product surface;
substrate primitives already exist.

**Why this matters for prioritization**: Surface E is not "Surface E"
in build-order rank — it is the operator's most-favored direction
among the five surfaces. Surfaces A (research workstation) and B
(document wrestle) are already built; Surface E is what the operator
specifically said they would prefer to build next, ahead of further
investment in the others. Sprint 17-18 reflects this priority.

**What it is**: the surface where the user parks unsharpened
thoughts, talks to their notes, slots them like Legos, and on the
user's go-ahead launches a research chain on a parked question.
Operator vision verbatim: *"I would prefer to create my own
brainstorming workstation product where you can talk to your notes
and slot some into focus like legos and challenge them. This can be
a thought partner like workflow where voicenotes or even an AI
assistant can be used to discuss the open-questions that the thoughts
of a user can be distilled to, and that list can exist as a 'watch
for later' function where they can be information research
trajectories that given the go-ahead can be launched by the user or
can be parked in that folder."*

**Why this is a fifth surface, not a feature of A or D**: research is
gated by curiosity, not by tooling. Curiosity surfaces in fragments
throughout the day — reading another paper, in a conversation, in a
voice note. The other surfaces start from a question (A) or a
document (B) or an outline (C) or an interview (D). The brainstorming
workstation starts from the user's own raw, unsharpened thoughts and
provides the parking lot + thought-partner + launch-when-ready
affordances. Currently the operator's parking lot is a notes file, a
browser tab, or nothing. The platform that solves the parking problem
captures the moment curiosity becomes investigable.

**Components**:

- **Watch-for-later folder**: UI on top of `question.identified`
  events filtered by an `unsharpened` state. Each parked question
  carries the context fragment that surfaced it (the voice note text,
  the highlighted paragraph, the conversation snippet). Click any
  parked question to expand context, edit, refine, or launch.
- **Launch-investigation affordance**: a button per parked question
  that POSTs to `/investigations` with the parked question as the
  seed. The investigation runs the Loop 1 cold-research chain on the
  question; results flow back as a new MASTER.md surfaced in the
  research workstation (Surface A).
- **Thought-partner workflow**: a new role under `roles/`
  (`thought_partner`) that takes a set of user-selected notes plus a
  prompt and produces challenges, syntheses, or extensions. Same
  recursive note-taking pattern as the autonomous chase, just
  initiated by user selection rather than autonomous trigger.
- **Voice-note input**: leverages Sprint 13 voice-acquisition
  pipeline. User talks through a thought; the system transcribes,
  extracts insights + open questions, parks the questions in the
  watch-for-later folder by default, surfaces insights for slotting.
- **Lego-block slotting**: any insight in the user's private graph
  is a first-class draggable object. User selects a set of insights,
  drops them into the thought-partner pane, prompts the partner to
  challenge or extend, iterates.

**Strategic role**: this is the surface where **private graph usage
happens**. Surface A (research workstation) drives public-graph
contribution. Surface B (document wrestle) sits between (public for
shared documents, private for user-uploaded content). Surface C
(creation workstation) produces deliverables from accumulated
material. Surface D (interview) captures content from others.
**Surface E is where users park their actual thinking, which is what
they don't want to share.** This is the surface that justifies the
50% margin on private tokens (§13.5) because it is the surface where
users will pay to keep their thoughts private.

**Privacy posture**: brainstorming workstation interactions stay on
the user's private graph by default. Nothing from this surface
enters the public collective graph without explicit user action
("share this to public graph" is a separate affordance, not the
default).

---

## 5. Voice and style — non-negotiable quality bar

Full details: `strategy/voice-and-style-discipline.md`.

This is the section every implementer needs to internalize. **Antiek's
product proposition collapses if the output reads like LLM slop.** No
amount of feature work makes a bullet-pointed em-dash-laden synthesis
into something the operator wants to read.

### 5.1 The slop pattern to suppress

- Em-dashes everywhere
- Bullet-point staccato within paragraphs
- Generic AI English vocabulary independent of subject matter
- Padding sentences ("It is important to note that...")
- Hedging modifiers that undermine claims with evidence
- Identical structural flow regardless of subject

### 5.2 The discipline to enforce

- Prose flows. Top-level structure (insights vs. open questions)
  stays; within each section, paragraphs.
- Sector vocabulary absorbed from the corpus. Radar engineers don't
  say "competitive moat"; VC analysts don't say "sidelobe
  reduction." Use the field's own words.
- One em-dash per thesis max.
- Confidence conveyed by sentence rhythm + word choice, not by
  appending "(high confidence)" markers in the prose.
- Forbidden phrases registered in the synthesizer system prompt.
- Reading typography: serif body font. The font itself signals
  "this is for absorbing, not for scanning."

### 5.3 Implementation surface

Three changes ship as part of Sprint 11 substrate work:

1. **Synthesizer prompt addendum** (~50 LOC) — forbidden constructions
   list, permitted-and-encouraged guidance, "absorb the corpus's
   vocabulary" instruction.
2. **Evidence retriever prompt addendum** (~30 LOC) — parallel
   discipline for upstream claim text.
3. **New role: `style_extractor`** (~150 LOC). Reads top-K chunks
   before synthesis, produces a 150-300 word "house style guide"
   describing the sector's vocabulary + argumentation pattern +
   sentence rhythm. Injected into the synthesizer's context pack as
   a `style_guide` layer. Feature-flagged on for qualitative
   investigations, off for purely quantitative ones.

UI-side: serif typography, no forced bullets in prose blocks, claim
spans inline (`<span>`), appendix material collapsed by default.

### 5.4 Verification

- Grep for `—` (em-dash) in MASTER.md: ≤2 per thesis (currently 12-20).
- Grep for padding constructions ("It is important to note", "It
  should be observed", "It can be argued that"): target 0.
- Sector vocabulary check: synthesis uses ≥40% of identifiable
  sector terms from corpus chunks.
- A/B with style_extractor on vs off: read both, decide if the role
  earns its cost.

### 5.5 Discipline extends to UI choices

Per `integration_posthog.md` §13.1, the voice and style discipline
governs **visual** choices, not just prose. The researcher's-notebook
identity — serif typography, no forced bullets, claim spans inline,
appendix material collapsed — is load-bearing for the product
proposition AND for the visual surface.

**Implication for UI library adoption:** any third-party component
library (Lemon UI candidate per `integration_posthog.md` Wedge 1b)
gets the same gate as prose. Decision criteria: does it preserve the
serif/notebook aesthetic, or does it drag the surface toward
SaaS-dashboard. Operator's eye test is final.

**Implication for AI-driven UI actions:** when Wedge 4 ubiquitous AI
ships, every AI action that modifies operator-visible surfaces
(notebook edits, MASTER.md modifications, dashboard rearrangements)
emits a typed event so the trajectory captures the AI's UI-driving
behavior. Voice and style discipline applied to AI actions: an
AI-rearranged notebook should not feel AI-rearranged; it should feel
like the operator's own work in the operator's own register.

**Implication for marketing surfaces** (when they ship): the same
discipline extends to the pricing page (`integration_posthog.md`
Wedge 6) and the eventual public handbook (Wedge 7). PostHog's
conversational-irreverent register is theirs. Antiek's register is
researcher's-notebook serious. Pattern transfers; tone does not.

### 5.6 PostHog's design and UI philosophy IS Antiek's design philosophy (operator-decided 2026-05-19)

Beyond the integration-spec verdicts in §17, **PostHog's design and
UI philosophy is the canonical reference for every interface decision
Antiek ships.** This is operator-decided and load-bearing, not a
stylistic preference. When designing any interface surface — for
operator use, for end users, for developers, for IP holders — the
first reference is `integration_posthog.md`. The voice/style
discipline (§5.1-§5.5) is the second reference and supersedes
PostHog's tone whenever they conflict.

**What transfers from PostHog (load-bearing):**

- **Notebooks as the literate-analysis primitive** (PostHog Wedge 2).
  TipTap-based block-structured documents combining queries + prose
  + replays + insights + region selections + claim cards + emergent
  notes + cross-doc links + LaTeX. This is Antiek's Loop 2 surface
  (Sprints 18-19, the linchpin per §14.3) AND the rendering target
  for trajectory replay (Wedge 5) AND a candidate render target for
  brainstorming workstation thought-partner sessions (Surface E §4.5).
- **Universal command palette (Cmd+K)** as cross-surface navigation
  (PostHog Wedge 3). One palette indexes everything: investigations,
  documents, claims, notes, open questions, watch-for-later items
  (§2.6), routes, AI actions. The palette is substrate-event-aware
  and updates within seconds of new content landing in the graph.
- **Max-style ubiquitous AI assistant** (PostHog Wedge 4). Inline
  presence on every screen, context-aware (knows current
  investigation, current personal-graph partition, current
  selection), UI-action capable with undo affordance through the
  event log. Every AI-driven UI action emits a typed event so the
  trajectory captures the AI's UI-driving behavior.
- **rrweb-concept trajectory replay** (PostHog Wedge 5). Timeline
  scrubber + event-at-time renderer for re-reading investigations,
  watch-for-later trajectories, and any operator-graded outcome.
- **Pricing page with calculator and transparent voice** (PostHog
  Wedge 6 template). When Antiek's pricing page ships, it surfaces
  the three-tier token-budget model (§13.5) with a calculator the
  user can manipulate (estimate cost given expected token usage
  on private + public partitions), free-tier limits prominent, no
  card required for free, plain-language explanation of why the 50%
  managed-service margin exists.
- **Storybook for the design system** (PostHog Wedge 1a). Every
  Antiek component documented as a story; visual regression catches
  structural breakage during Surface E / notebook / palette work.
- **Lemon UI evaluation gate** (PostHog Wedge 1b). The evaluation
  decision (Sprint 17 spike) is whether Lemon UI preserves the
  researcher's-notebook aesthetic per §5.5. If it does, adopt; if it
  doesn't, custom components stay. Either outcome is defensible.

**What does NOT transfer from PostHog** (Antiek's voice/style §5 wins):

- PostHog's conversational-irreverent tone, hedgehog mascot,
  SaaS-startup register. Antiek's register is researcher's-notebook
  serious — serif body font, no forced bullets in prose, claim spans
  inline. Pattern transfers; tone does not.
- PostHog's multi-tenant org/team/billing surfaces. Antiek is a
  consumer product (§9.0.1) where each user pays Stripe directly
  through the pay-as-you-go token-budget model; multi-tenant
  org/team UI is irrelevant.
- PostHog's ClickHouse + Kafka substrate. Antiek's DuckDB
  single-writer invariant is non-negotiable (§13.6 substrate
  transition matrix).
- PostHog's plugin marketplace. Antiek has zero third-party
  developers; building a marketplace would be theater.

**The discipline**: when in doubt about a UI/design decision, consult
`integration_posthog.md` first. The PostHog spec's wedge mechanics
and explicit REJECTs (§16.1) are canonical within their domain.

---

## 6. Primary source connection

Operator vision: *"It would be great if you could pull the user towards
the actual document. And it would even be better if you could pull
the user to the actual page so they could kind of scroll through that
document."*

### 6.1 What the substrate already has

Every chunk row carries `section_path`. For PDFs ingested via
`acquisition/books/reader.py`, this is "Page N" (set by
`_join_pages_to_markdown`). For URLs, it's the section heading
detected by `acquisition/urls/extract.py`. For arXiv, it's blank for
the abstract or "Page N" if the full PDF was fetched.

Every claim cites a list of `chunk_id`s. The substrate can answer
"where did this claim come from" with chunk-level precision.

### 6.2 Sprint 11 implementation

1. **Chunk hover modal** (already in MVP scope): hover any claim
   span → tooltip shows chunk IDs + source tiers. Click chunk ID
   → modal opens via `GET /chunks/{id}` showing chunk text +
   document title + section path.
2. **"Open in document viewer" button** in the chunk modal:
   navigates to `/wrestle/<document_id>?page=<N>` where N is parsed
   from `section_path`.
3. **WrestleApp `?page=` query handling**: existing `PdfViewer.tsx`
   gets an `initialPage` prop. The WrestleApp wrapper reads the
   query param and jumps to that page on load.
4. **Source-uri linking** for non-PDF sources (URL articles, arXiv
   abstracts): chunk modal shows a "View original" link to the
   `source_uri` field of the document row.

### 6.3 Beyond Sprint 11: deep-link to source moment in audio/video

When YouTube + podcasts come in (section 8), the source-of-truth
becomes a timestamp in an audio/video stream, not a page. Chunk
metadata grows: `section_path` becomes a richer object with `kind`
discriminator (`page_number | timestamp_seconds | url_anchor`).
"Open in document viewer" becomes "Open at timestamp" with an
inline player. Sprint 12+ work.

### 6.4 IP posture

For now (Sprint 11): substrate ingests freely from anywhere the
operator can find content. Chunk modal includes a small footer
attribution: *"Source: <document_title>. Used for research purposes."*
No removal mechanism yet. No IP-holder opt-out.

This is acceptable because the substrate is operator-only on a
single VM and isn't serving content to third parties. When the IP
attribution + ad economics layer (section 9) becomes active, the
posture changes — see section 9.7.

---

## 7. Continuous research mode

Operator vision: *"The continuous note-taking process of identifying
insights connected to open questions and then just chasing the rabbit
hole of open questions and creating a big knowledge base of notes that
could be distilled into the deliverable that I see. This should be
something that could run 24 hours, continuously sharpening the
information."*

### 7.1 The two interpretations

**A. Single-investigation never-terminates.** The orchestrator
re-enters Phase 2 for any unresolved `evidentiary_gap`, spawns new
sub-questions, accumulates results into the same MASTER.md, never
fires `investigation.completed` until a terminate signal arrives.

**B. Daemon spawns new investigations.** Separate process watches the
event log for `evidentiary_gap` records across all prior runs,
POSTs new `/investigations` against the strongest open questions,
accumulates results into a shared rolling document.

The operator's vision is closer to B. A is a much simpler first
implementation that gets ~60% of the value.

### 7.2 Sprint 12 — first interpretation

**Substrate changes**:

- `POST /investigations` gains an optional field:
  `keep_chasing: {mode: "off" | "depth" | "duration", value?: int}`
  - `mode: "off"` (default, current behavior)
  - `mode: "depth", value: N` — chase up to N levels of child
    investigations
  - `mode: "duration", value: H` — chase for up to H hours of wall
    time
- Orchestrator's Phase 8 logic gets an early-exit check. If
  `keep_chasing.mode != "off"` AND stop condition not yet met AND
  current MASTER.md has unresolved evidentiary_gaps:
  - Pick the strongest 1-3 open questions from the gaps
  - Each becomes a new sub-investigation with parent context
  - Spawn them (POST /investigations with `parent_investigation_id`)
  - Loop back to Phase 1 of the parent (but with the new
    sub-questions appended to the decomposer's output)
- New event: `investigation.chase_iteration_started` (which iteration
  number, current chase depth, projected cost so far)
- Budget cap: per-investigation cost limit (defaults to $10 USD if
  not specified). Orchestrator emits `investigation.chase_halted`
  when cap hit with reason.

**UI changes**:

- Chat input area gets a "Mode" selector: One-shot / Chase to depth /
  Chase for time / Custom budget
- Trajectory view renders the chase tree: parent + spawned children
  + their children
- Live cost meter in the header: "Currently $X.XX, projected $Y/hr
  at current rate"
- "Halt chase" button always visible during continuous mode

**Verification**: an operator can set up "chase this question for 2
hours up to $5", walk away, come back to find a richer MASTER.md
than a one-shot investigation produced.

### 7.3 Sprint 14+ — second interpretation (daemon)

**The daemon process**: a separate Python service running on the
same VM. Subscribes to the same event log (read-only). Maintains
an in-memory queue of unresolved open questions across all
investigations. Logic:

- Every minute, scan recent events for new `evidentiary_gap`
  records
- For each gap, compute a "chase score" based on:
  - Recency (newer gaps weighted higher)
  - Co-occurrence count (a gap that shows up across multiple
    investigations is more valuable to chase)
  - Operator interaction signal (highlighted-but-not-resolved
    text has higher score than passively recorded gaps)
- Spawn investigations against the top-scoring queue items
  subject to a daemon-level budget cap (`ANTIEK_DAEMON_HOURLY_BUDGET_USD`)
- All daemon-spawned investigations get a distinctive `policy_id`
  for trajectory filtering

**Storage**: results accumulate per-question. The substrate adds
a new concept: a `research_topic` that aggregates investigations
sharing context. Multiple investigations on the same root question
get rolled into one topic's "running master doc."

**Operator surface**: the chase-tree view in the web app shows
both operator-spawned chases AND daemon-spawned chases (visually
distinguished — daemon ones get a small robot icon).

### 7.4 Cost-runaway risk

The default daemon budget cap MUST be conservative. $5/day is
already $150/month on top of the operator's manual investigation
spend. The runaway scenario: a gap with high co-occurrence
spawns a chase that itself generates more gaps with high
co-occurrence, leading to exponential branching. Mitigations:

- Hard cap per investigation ($2)
- Hard cap per day across daemon ($5 default)
- Per-topic depth cap (max 5 levels deep)
- Decay: if an investigation produces only gaps that have already
  been chased ≥3 times across the daemon's history, halt that
  branch

---

## 8. Multimodal acquisition

Operator vision: *"There's a lot of sources of information within
YouTube videos, X posts, just general Internet stuff that are outside
of just like books and writing... a podcast or an interview, or even
like a meme cycle on TikTok or Instagram or Twitter."*

### 8.1 The substrate's existing pattern

`acquisition/` has shipped adapters for arXiv + URLs + books (PDFs).
Each follows the same contract:

```python
def ingest_<source>(source_input, *, investigation_id, ...) -> IngestResult:
    """
    1. Emit document.loaded event
    2. Open DB via connect_write
    3. Insert documents row
    4. Chunk text via processing.chunking.chunk_markdown
    5. Insert chunks + per-chunk nodes
    6. Return IngestResult with document_id + chunk_ids + node_ids
    """
```

New adapters use the same shape. The substrate-side changes are
small per source.

### 8.2 Sprint 12 scope — YouTube + podcasts

**YouTube** (~300 LOC):
- `acquisition/youtube/client.py` — wraps `yt-dlp` (already in
  `[youtube]` optional dep) for metadata + `youtube-transcript-api`
  for transcripts.
- `acquisition/youtube/adapter.py` — converts transcript to
  markdown, splits by speaker turn or by timestamp chunks. Chunk
  `section_path` becomes `Timestamp: HH:MM:SS - HH:MM:SS`.
- Fallback: when no transcript exists, use whisper API to transcribe
  the audio. Cost ~$0.006/min.
- IngestResult adds `video_id` + `transcript_source: "youtube" | "whisper"`.

**Podcasts** (~350 LOC):
- `acquisition/podcasts/client.py` — RSS feed enumeration via
  `feedparser` (already in `[rss]` optional dep) + episode audio
  download.
- `acquisition/podcasts/adapter.py` — most podcasts publish
  transcripts on their websites; check that path first. Whisper
  fallback otherwise.
- Chunk `section_path` becomes `Episode: <title> @ Timestamp: HH:MM:SS`.

**UI surface** (Sprint 12 day 4-5):
- New "Sources" tab in the workstation: paste a URL (arXiv, YouTube,
  podcast, general web) → substrate dispatches to the right adapter
  → progress streams via WebSocket → chunks land in the graph.

### 8.3 Deferred — X (Twitter)

Hard for non-technical reasons:
- X API requires paid tier ($100+/month for write; read restricted)
- `snscrape` used to work for unauthenticated scraping; may be
  broken
- Single tweet is too short to ingest meaningfully; **threads**
  and **quote-tweet chains** are the unit of analysis
- Most "meme cycle" insights are sentimental/cultural rather than
  factual — different analysis shape

**Plausible Sprint 14 path**: a browser extension (Chrome / Arc)
that captures a thread when the operator hits a button, POSTs it
to the substrate. Side-steps the API problem. Captures only what
the operator actually wants ingested.

### 8.4 Deferred — TikTok / Instagram / Reels

No clean text content. Requires vision + audio model to transcribe
+ describe. Defer until the substrate has a vision-capable role
tier. Sprint 15+.

### 8.5 Deferred — Substack / paywalled journalism

Technical ingestion is easy (RSS or scraping). The blocker is the
IP posture (section 9). Substrate already has `acquisition/urls/`
which ingests any HTML page; the question is whether to ingest
paywalled content (legal exposure) or wait for the attribution
economics (section 9) to make it palatable for publishers to opt
in. Sprint 16+.

---

## 9. IP attribution + ad economics

Operator vision: *"I could create some type of banner ad economy.
Where the ad kind of exists as the border of the page... If I calculate
the drivers of information within that page that the banner is around,
and I could kind of calculate the attribution to that core insight or
question that the user is interacting with... attribute some revenue to
that ad in that instance to the biggest drivers of that information,
split across everyone who's on that page."*

**This is the most strategically consequential section in the spec.**
It's also the most fragile — get the attribution math wrong and the
incentives turn perverse. Get it right and Antiek becomes the first
piece of infrastructure that pays IP holders for the LLM-mediated
information economy.

### 9.0 The legal gate is binding NOW (added 2026-05-18)

Three precedents have landed between original master-spec drafting
and the data-repository sharpening that fundamentally change the IP
posture:

1. **Bartz v. Anthropic** (settled September 5, 2025): $1.5B class
   settlement covering ~500,000 books at ~$3,000 per work. Judge
   Alsup held that training on **legally acquired** books is fair use
   ("quintessentially transformative") but training on books pirated
   from LibGen / Books3 / Pirate Library Mirror is NOT fair use, and
   such procurement is independently infringing regardless of what
   the model does with the content. Settlement releases conduct
   through August 25, 2025 only — future training is not licensed.
   Authors Guild reports 91.3% of eligible works claimed as of
   March 30, 2026.

2. **Hachette v. Internet Archive** (Second Circuit, September 4,
   2024): killed the structural argument that scanning-plus-lending
   or scanning-plus-querying is fair use. Binding precedent in the
   Second Circuit; IA declined certiorari. AAP describes as "broadly
   impactful to other controversies, including artificial
   intelligence cases."

3. **Authors Guild MDL** (In re OpenAI Inc. Copyright Infringement
   Litigation, MDL No. 3143): consolidated April 3, 2025. Judge Stein
   denied OpenAI's motion to dismiss October 2025, finding ChatGPT
   outputs could be "substantially similar" to plaintiff works. Fact
   discovery closes February 27, 2026. Summary judgment on fair use
   expected summer 2026.

**The dispositive variable is now procurement, not use.** Sprint 16
shipped IP attribution telemetry with three algorithms — correctly,
because no money flows yet. Sprint 18 ships Stripe Connect with money
flowing on the same attribution algorithm. **The Sprint 16
operator-stated gate ("operator's lawyer involved before payouts")
is binding for Sprint 18, not deferred.** Pre-payout the worst case
is a publisher cease-and-desist forcing takedown (lose data, not
money). Post-payout the worst case is a publisher discovers
attribution-based money has been routed based on a corpus including
their books ingested without license — now they have a contemporary
monetary transaction to point to. Once money flows, every chunk in
the graph has been monetized regardless of whether the publisher saw
any of it.

**Required intervention: retrieval-time gating before Sprint 18
ships.** Three options for ingested-but-restricted content:

- **Option A — Purge restricted-class content from the graph.**
  Cleanest legally. Breaks the cross-corpus value because the most-
  cited works will be the missing ones. **REJECTED** on product-thesis
  grounds — destroys the moat.
- **Option B — Tag and gate at attribution time.** Content stays in
  the graph for retrieval but is zeroed out in the attribution
  algorithm. Publishers see your platform using their content but
  never receiving payment. **REJECTED** as documented unjust
  enrichment.
- **Option C — Tag and gate at retrieval time.** Restricted content
  cannot be retrieved into a synthesis that triggers attribution.
  Stays in graph for private/operator-only research where fair use
  is robust. **ACCEPTED.** Requires a graph schema change: every
  retrieval call carries a `policy_tag` parameter; restricted content
  returns only when `policy_tag in {"private_research",
  "operator_only"}`.

Sprint 18 ships ONLY after retrieval-time gating is in production AND
publisher onboarding is a prerequisite to payouts (no payout
activates until at least one publisher has opted in). This converts
the payout system from "we owe you for retrospective use" to "we
will pay you for prospective use once you opt in." The legal
characterization is fundamentally different.

### 9.0.1 Phase 1 monetization is the operator's pay-as-you-go token model, NOT IP-payouts

The IP payout system (§9.1-§9.10 below) is the novel mechanism design
and the most strategically consequential piece, but **it is not the
right initial monetization vehicle**. Three reasons.

**First, the unit economics of ad-supported consumption alone don't
work.** Banner ad RPM on text content runs $5-$20 effective CPM in
good niches. A reader spending 10 minutes on a page generates
$0.05-$0.20 in ad revenue. That same reader's agentic interaction
during those 10 minutes (synthesizer + verifier + note-taker +
evidence-retriever all running) consumes 100,000-500,000 tokens at
~$5/M input, which is $0.50-$2.50 in token cost. **Pure unlimited
ad-supported AI consumption pays users to consume content** — the
Scribd failure mode. The fix is in the operator's pricing model
itself (next).

**Second, the operator-decided Phase 1 monetization is the
pay-as-you-go token-budget model from voice notes 2026-05-17**
(codified in §13.5). It is NOT a flat subscription; it is OpenRouter-
style budget pricing with explicit margin tiers and a free cap that
bounds CAC exposure.

- **Free public tier (the network-effect driver)**: ad-supported
  public-graph consumption on DeepSeek-Flash inference up to a
  generous monthly cap (~5M tokens). 70% of ad revenue from a public
  note's attention routes to the note's creator (the user-as-IP-
  holder mechanism — §13.9). Above-cap users convert to paid public
  consumption.
- **Paid public consumption (above cap)**: pay-as-you-go on the
  public graph at **10% margin** on raw token cost. Ads still on;
  creators still earn 70% rev-share.
- **Paid private use (the brainstorming workstation surface,
  Surface E §4.5)**: pay-as-you-go on the user's private graph at
  **50% managed-service margin** on raw token cost. No ads. Content
  walled. This is the surface that justifies the 50% margin because
  it is the surface where users will pay to keep their thoughts
  private.
- **Developer surface (API + MCP + CLI as Antiek Memory)**: usage-
  based per query with IP-attribution routing on public-notes queries
  (§13.8).

This is the YouTube + OpenRouter + creator-economy hybrid the
operator articulated. Pricing is **a budget set by the user, billed
on actual usage** — not a fixed monthly seat fee. The OpenRouter
framing the operator named is exact: users set a budget, get billed
for tokens consumed against that budget. The platform's margin layers
on top of underlying inference cost.

**Third, the legal characterization is cleanest for individual users**
who upload documents they have legitimate access to (research papers
they purchased, books they own, notes they wrote, voice notes they
recorded). Fair use is most robust for individual research with
assistive software on a personal corpus — the Authors Guild v. Google
snippets analysis and decades of researcher-tools precedent. The
platform is hosting infrastructure; the user is the fetch agent. The
Bartz failure mode (§9.0) is the inverse: if the platform fetches
copyrighted content on behalf of users, the platform owns the
procurement liability. **Architectural commitment: never have the
platform fetch a copyrighted document on behalf of the user.** User
uploads documents they have legitimate access to; platform processes
them.

**Verdict**: the operator's pay-as-you-go token-budget model is
Phase 1 monetization from Sprint 19+. The IP-payout system
(§9.1-§9.10) stays on the roadmap with one operator-decided
restructuring: pre-onboarded IP holder accounts ship with the
architecture in Sprint 18 (escrow accruing per the Kalshi-pattern
framing — §9.10), but **escrow payouts gate strictly on publisher
opt-in**, not on session attribution. Sprint 18 ships payout
infrastructure with the activation gate "first publisher contract
executed."

**Unit-economic envelope per population**:

- **Free-tier user**: ~$0 net of ad revenue (CAC line item bounded
  by the 5M-token DeepSeek-Flash cap)
- **Above-cap public user**: platform earns 10% margin on token cost
  + 30% of ad revenue from that user's session (70% goes to the
  creator whose note generated attention)
- **Private user**: platform earns 50% managed-service margin on
  token cost
- **Creator earning ad rev-share**: net positive contributor to
  ecosystem; payouts via the same Stripe Connect architecture as
  publisher escrow (§13.9)
- **Developer API consumer**: per-query usage-based; per-query cost
  on public-notes queries flows through IP attribution to publishers
  and creators (§13.8)

**Audience framing**: anyone doing knowledge work. Researchers,
writers, students, journalists, analysts, founders, hobbyists,
curious individuals — the operator's vision in voice notes is
explicit that "the information economy could be really, really
transformed with a very cursor-like experience to research and
knowledge work." This is a consumer product for individuals. The
platform's job is to make information consumption + creation feel
fundamentally different. No specific job-title segment is the target.

**Growth motion**: visible-artifact peer distribution. The operator
uses Antiek themselves, publishes outputs (under their personal
account or any pen name they choose), and peers who see the outputs
ask what tool produced them. Individual-to-individual organic
discovery through artifact quality, not paid acquisition or
enterprise sales. Voice-and-style discipline (§5) is the load-bearing
quality requirement that makes this growth motion work — the outputs
have to be visibly different from LLM slop or peers won't ask.

### 9.1 The full mechanic

1. User reads a synthesis page (MASTER.md viewer) on
   `app.antiek.ai`
2. Page renders with a banner ad (programmatic, bid upon)
3. Substrate knows: for every claim on the page, which chunk_ids
   supported it. Each chunk has a `document_id`. Each document has
   an `ip_holder_id` (new field added in this phase).
4. When an ad impression accrues, substrate computes attribution
   weights: for THIS specific page, how much did each source
   document contribute?
5. Revenue distributed:
   - Platform cut: configurable, default 30%
   - IP holders: 70% split among contributing documents, weighted
     by attribution share

### 9.2 What's load-bearing

- **Attribution math** (genuinely novel design problem)
- **Ad inventory mechanism** (programmatic vs. flat sponsor vs.
  lead-gen)
- **Payout infrastructure** (Stripe Connect, KYC, ToS)
- **IP holder onboarding** (publisher dashboard)
- **Anti-gaming** (click fraud, view fraud, attribution gaming)

### 9.3 Attribution math — design space

Given a synthesis page with N claims, each citing M chunks from K
documents, what's each document's share of the page's attribution?

**Option A — equal split per chunk citation**. Document gets
share proportional to (its chunks cited on page) / (total chunks
cited on page). Simplest. Fails to weight by importance: a load-
bearing claim with one chunk citation gets less than a peripheral
claim with five citations from the same document.

**Option B — weighted by claim confidence × source tier**. Each
chunk's contribution = `claim_confidence * (6 - source_tier)`.
Higher-confidence claims grounded in higher-tier sources contribute
more. Aligns incentives toward quality.

**Option C — weighted by "load-bearing"-ness**. Run a secondary
LLM pass: for each claim, "if you removed this claim, would the
thesis change?" Yes-answers contribute disproportionately. Most
defensible attribution-wise. Most expensive computationally.

**Recommended phased approach**:
- Phase 1 (telemetry only, no money): all three options computed
  per page. No payouts; just data collection. Lets the operator
  validate the math by reading attribution reports and
  qualitatively assessing if they "feel right."
- Phase 2 (real payouts begin): Option B as default. Option C as
  premium tier for high-value pages.

### 9.4 Ad inventory mechanism — design space

**Option A — Programmatic display ads.** Header-bidding-style auction.
Highest CPMs, highest infrastructure complexity (multi-month build),
brand-safety concerns, mostly low-quality ads. Probably wrong for the
audience.

**Option B — Flat-rate sponsorships.** "Sponsor pays $X/month to be the
ad on every page during the month." Simple to build. Low ceiling. Good
fit for the early-stage audience (specialist research readers — VCs,
analysts, journalists, founders).

**Option C — Lead-gen / vertical ads.** Ad slot shows a relevant
service offering (consulting, recruiting, vertical SaaS) targeted by
the synthesis topic. Higher CPMs than display, more aligned with
audience intent. Builds on the existing substrate's topic
classification (decomposer already produces topic categories).

**Recommended phased approach**: Phase 1 = Option B (single
sponsorship slot, manually sold). Phase 2 = Option C with manual
ad-inventory curation. Phase 3 (someday) = Option A only if scale
justifies the infrastructure.

### 9.5 Payout infrastructure

- **Stripe Connect** for the payee (IP holder) side. ~1-2 weeks of
  integration work.
- **Stripe** for the advertiser side. Standard checkout, ~1 week.
- **KYC + 1099 reporting + ToS**: 1-2 months of compliance work
  alone, depending on jurisdiction. The operator is in Saudi
  Arabia; Antiek as a US-incorporated entity simplifies some of
  this but adds complexity to the operator's tax situation.
- **Payout cadence**: monthly minimum, $10 minimum payout
  threshold to avoid Stripe fees eating small payouts. IP holders
  below threshold roll over to next month.

### 9.6 IP holder onboarding

New product surface: the publisher dashboard at
`publisher.antiek.ai`. Capabilities:

- IP holder claims their content (e.g., "I'm the author of these
  books / this Substack / this podcast")
- Verification: domain ownership for websites, ISBN matching for
  books, manual review for ambiguous cases
- Connects Stripe account for payouts
- Sees a dashboard of: which Antiek synthesis pages cited their
  content, attribution shares, accrued revenue
- Can opt OUT of having their content used (and removed
  retroactively if they didn't consent)

The technical architecture: a new `ip_holders` table linked to
`documents` via `ip_holder_id` foreign key. A new event type:
`ip_holder_claim_verified`. A new role permission: publishers can
see attribution + revenue data for their own content, nothing else.

This is its own product surface and accounts for ~30% of the work
in the IP-attribution sprints.

### 9.7 Anti-gaming

The threat model: anyone who learns the attribution math has
incentive to inflate impressions on pages where THEIR content has
high attribution share.

Mitigations:

- **Per-document payout rate cap.** No document can earn more than
  $X/day regardless of citation volume.
- **Click + view fraud detection.** Standard ad-tech mitigations
  (bot detection, geo anomaly detection, click velocity caps).
- **Audit logs.** Every attribution computation is logged with
  inputs + outputs; humans can spot-check.
- **Operator-controlled IP holder verification.** Until a
  publisher is operator-verified, their attribution share is
  withheld (held in escrow). Discourages drive-by gaming.

### 9.8 Phased sequence

| Phase | Sprint | What ships | Money flows? |
|---|---|---|---|
| 1. Attribution telemetry | Sprint 16-17 | Substrate emits `page_attribution_computed` events per page render. Three attribution algorithms computed in parallel for A/B analysis. No UI changes. No payouts. | No |
| 2. Manual sponsor slot | Sprint 18-19 | Single sponsorship slot in MASTER.md viewer footer. Manual sponsor onboarding via direct sales. Sponsor pays flat monthly fee. Revenue routed manually to top-3 attributed publishers as proof-of-concept. | Yes (manual) |
| 3. Publisher dashboard | Sprint 20-22 | `publisher.antiek.ai`, Stripe Connect, automated payouts. ~3 sprints because compliance + KYC + UX is substantial. | Yes (automated) |
| 4. Lead-gen ad inventory | Sprint 23+ | Curated vertical ad slots replacing the manual sponsor model. Higher CPMs. | Yes (scaled) |
| 5. Programmatic auction | Sprint 30+ | Only if scale warrants. Probably never if Phase 4 economics are strong enough. | Yes (scaled) |

### 9.9 Strategic open questions

- **Is the IP holder opt-in viable?** If Antiek ingests freely and
  IP holders can opt out (with retroactive removal), what's the
  steady-state ingestion rate? If 80% of valuable corpus opts out
  the moment they hear about Antiek, the platform's information
  density collapses. Need to validate that the attribution
  economics offer enough upside to keep IP holders opted in.
- **What's the buyer for the ad inventory?** Programmatic ad
  networks treat research audiences as low-value. The right
  buyer is enterprise (sales tools, vertical SaaS, recruiting,
  consulting). That requires direct sales relationships, not a
  display ad network. Probably means a real BD function exists
  by Phase 4.
- **Is the model competitively durable?** Cloudflare, OpenAI,
  Anthropic each have stronger distribution to build "pay
  publishers for LLM citations" rails. What does Antiek have?
  Probably: chunk-level attribution is finer-grained than what
  model-provider attribution will ever be (providers see
  "tokens in, tokens out"; Antiek sees "for this specific page
  rendering, these specific chunks contributed"). The substrate
  IS the moat.
- **Does the legal posture survive scaling?** Currently the
  substrate ingests "everything online" with no IP clearance.
  When the first takedown notice arrives, what's the workflow?
  This needs an answer BEFORE the attribution layer goes live —
  publicly distributing scraped content + monetizing it through
  ads invites a different legal response than research-only
  ingestion.

### 9.10 Pre-onboarded IP holder accounts (Kalshi pattern — operator-decided 2026-05-17)

Operator vision verbatim from voice notes: *"I also had an interesting
idea of pretending all the IP I use from Anna's Archive and other
sources is legal and creating accounts for the IP holders so that the
revenue share accrues over time until we partner so that I can hand
them the account when we partner. I will also send each an email
saying that I am building this platform and have created accounts for
them and am excited to onboard them (and distribute revenue) whenever
they are ready. This timestamp will help me in the legal tension;
Kalshi executed perfectly in a legally tense environment by being
transparent and aggressive; I want to do the same."*

**Architecture ships Sprint 18 alongside the publisher dashboard
(§14.1). Payouts gate strictly on publisher opt-in.** The Sprint 18
legal gate (§9.0) and the operator's Kalshi-pattern framing are
compatible because the architecture creates the account + accrues
the escrow but does NOT route money until the publisher affirmatively
opts in. This converts the publisher's eventual framing from "this
platform stole from us" to "this platform was openly building an
opt-in payment system that we ignored."

**Why pre-onboarded accounts cut both ways legally** (and why
execution discipline matters):

- **Mechanism that helps**: documentary evidence of good-faith
  intent. Timestamped notification email + pre-created account +
  segregated escrow accruing per publisher = "we were not
  free-riding; we were building an opt-in payment system."
- **Mechanism that hurts**: the escrow itself documents the
  platform's use of unlicensed content. Bartz turned on procurement,
  not training. A plaintiff's lawyer could frame the escrow as
  "they admit they owe us money, they just didn't pay us."

**The framing that makes this work in Antiek's favor** is precision
about what the platform is and isn't doing. The platform is NOT
republishing books. It is NOT letting users read books cover-to-cover.
It IS using chunks of text for attribution-bearing synthesis and
discussion in a manner the platform believes is transformative use,
with revenue share routing back to IP holders in good faith from day
one. The notification email language matters: *"We are building a
platform that uses your published works for AI-mediated research
synthesis, in a manner we believe is transformative under fair use,
while routing revenue share to you in good faith from day one. We
invite you to claim your account and accept payments accrued to date."*
This frames Antiek as a fair-use operator voluntarily sharing
revenue, not as an infringer paying restitution.

**Implementation requirements (binding)**:

1. **Notification email to publisher's legal department**, not
   marketing team. Record of delivery required.
2. **Account claimable through documented process** (claim by
   verified domain ownership, ISBN matching for books, manual
   review for ambiguous cases).
3. **Escrow in segregated regulated accounts**, not commingled
   with operating funds — so "we have your money waiting" is a
   verifiable statement.
4. **Opt-out within 30 days** (7 days better): if publisher emails
   "remove our content from your platform," content must actually
   be removed within the defined window, or the good-faith framing
   collapses.
5. **Lawyer involved before the first notification email is sent**,
   not after. The Sprint 18 legal gate (§9.0) is binding for
   this exact reason.

**First-cohort strategy** (Sprint 19): send the first batch of
notification emails to academic publishers + university presses
whose institutional mission includes broad dissemination of
knowledge and whose litigation budgets are smaller. **MIT Press,
Cambridge University Press, Princeton University Press** are the
right first cohort. Their response (positive, negative, or none)
calibrates how the broader strategy will land before committing
with publishers who have more aggressive postures (e.g., the Big
Five publishers who joined the Hachette v. Internet Archive
plaintiff group are the WORST candidates for first notification
because they have institutional momentum toward litigation).

**Substrate hooks**: every document carries `ip_holder_id` (already
in spec). Pre-onboarded IP holders get an `ip_holder` record with
`status: pre_onboarded`, `claim_status: unclaimed`,
`escrow_balance_usd: 0`. Every attributable usage of their content
accrues to the escrow balance. Opt-in flips `claim_status: claimed`
and unlocks the Stripe Connect payout. Opt-out flips
`status: opted_out` and triggers content removal within 30 days.

### 9.11 What to do now

Sprint 18 substrate work + Sprint 19 first-cohort outreach. **Lawyer
involved before any notification email sends.** The Sprint 16
operator-stated gate is binding here per §9.0.

---

## 10. Creation surface — writing tool

Operator vision: *"In the consumption process where you're doing
research and you're chasing ideas, you're ultimately building the Lego
blocks of insights related to different ideas. You could fork these
insights out, draw an outline of a deliverable you want to write where
you could segment the insights like, oh, let's merge these three
blocks together. This could be a section. I want to call this section
this, and then I'll pull these blocks of insights, and then it'll be
called this, and then maybe I'll add this open question here because
I want to discuss it here."*

### 10.1 The shape

The substrate accumulates a graph of insights through consumption-side
investigations (Surfaces A + B). The creation surface inverts the
flow: operator drags insight blocks into a structured outline → LLM
expands the outline into prose → operator edits at every granularity.

**Lego-block metaphor** is operator's framing and is the right one.
Each insight in the graph is a first-class draggable object with:

- Stable `node_id` and/or `claim_id`
- Source provenance (which chunks supported it, which documents)
- Confidence + source tier
- Operator-added metadata (highlighted-as-golden, tagged categories,
  custom notes)

### 10.2 The data model

New tables on the substrate:

```sql
-- A deliverable is a draft document being assembled by the operator
CREATE TABLE deliverables (
    deliverable_id      TEXT PRIMARY KEY,
    title               TEXT NOT NULL,
    deliverable_kind    TEXT NOT NULL CHECK (deliverable_kind IN (
        'research_memo', 'book_chapter', 'biography_section',
        'investor_brief', 'general_essay'
    )),
    investigation_root_id TEXT,  -- optional link to root investigation
    created_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status              TEXT CHECK (status IN ('draft', 'in_review', 'final')),
    metadata            TEXT  -- JSON
);

-- A section is an ordered piece of a deliverable
CREATE TABLE deliverable_sections (
    section_id          TEXT PRIMARY KEY,
    deliverable_id      TEXT NOT NULL REFERENCES deliverables(deliverable_id),
    parent_section_id   TEXT REFERENCES deliverable_sections(section_id),
    section_index       INTEGER NOT NULL,
    title               TEXT,
    prose_text          TEXT,  -- the generated/edited prose
    prose_provenance    TEXT,  -- JSON: which blocks generated which paragraphs
    created_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- A block-to-section assignment is which insight blocks live in which section
CREATE TABLE section_blocks (
    section_id          TEXT NOT NULL REFERENCES deliverable_sections(section_id),
    block_kind          TEXT NOT NULL CHECK (block_kind IN (
        'insight', 'open_question', 'operator_note'
    )),
    block_id            TEXT NOT NULL,  -- node_id, claim_id, or note_id
    block_index         INTEGER NOT NULL,  -- order within section
    PRIMARY KEY (section_id, block_kind, block_id)
);
```

### 10.3 The expansion role: `creative_writer`

New role at `roles/creative_writer/`. Takes:

- The section's title + position in the deliverable
- The ordered list of attached blocks (insights, open questions,
  operator notes)
- The full deliverable's title + kind for global context
- The style_guide from `style_extractor` (run once per deliverable,
  caches across sections)

Produces:

- Prose for the section
- A `prose_provenance` map: for each paragraph, which blocks
  contributed
- Citations preserved (claim spans inline, chunk_ids referenced)

The prompt explicitly takes the **voice and style discipline** (section
5) since this is the final operator-facing artifact. Even more strict
than the synthesizer because the deliverable is publishable, not just
informational.

### 10.4 The edit-back-into-graph problem

When the operator edits the generated prose, what happens?

**Option A**: Edits are local to the deliverable. The graph isn't
modified. Simple but loses the high-value signal of operator judgment.

**Option B**: Significant edits become new "operator-asserted claims"
in the graph. A claim with `policy_id = "operator/<deliverable_id>"`
gets inserted with the operator's edited text. Future investigations
can cite these claims. Recursive value loop.

**Recommended**: Option B. New event type:
`CLAIM_ASSERTED_BY_OPERATOR` with payload carrying the original
generated text, the edited text, the deliverable/section context.
Substrate's grounder role can still verify these (they're claims
without primary-source citation, so flagged as `source_tier = 5`
unless operator manually attaches chunk citations).

### 10.5 UI surface

Mode C at `app.antiek.ai/write/`. Three-pane layout:

```
+----------------+----------------+--------------+
| Block palette  | Outline + prose| Editor       |
|                |                |              |
| Search / filter| Sections tree  | Current      |
| insight blocks | with attached  | section's    |
| from graph     | blocks         | generated    |
|                |                | prose,       |
| Drag → outline |                | editable     |
+----------------+----------------+--------------+
```

- Left: searchable index of all insights + questions + notes
  in the graph. Filter by investigation, topic, source, golden-
  tagged, recency.
- Center: the outline. Drag blocks from left panel into sections.
  Reorder sections. Add titles. Click "Generate prose" → triggers
  `creative_writer` for that section.
- Right: the generated prose in an editor. Operator edits inline.
  Save → commit edit, optionally promote to graph (Option B).

### 10.6 Multi-sprint sequence

- **Sprint 13**: data model migration + creative_writer role +
  basic UI (no drag-drop yet, blocks added via search-and-select).
  Generates prose for a single section at a time.
- **Sprint 14**: drag-drop outline UI + multi-section coherence
  (`creative_writer` aware of adjacent sections to avoid repetition).
- **Sprint 15**: edit-back-into-graph (Option B). Stripe Atlas
  decision and deliverable export formats (PDF, EPUB, Substack
  draft).

---

## 11. DeepBlu — interview-as-acquisition

Operator vision: *"From all those interviews, I could have the same
workflow of, that's the information asset, and the LLM could take
notes on every interview. Then those notes could have the insights and
the open questions, and the open questions could then inform maybe me
who's writing this project. I could have a dashboard where it says,
oh, these are the things you still need to find out based on all
these transcripts that I did and all these insights, I think XYZ
person would be useful. Then I could push some notifications for them
if I had already sent the link to them to be a user to kind of talk
to the interviewer or just do voice notes."*

### 11.1 The shape

DeepBlu is the acquisition channel for content that doesn't exist as
a document. Two modes:

**Mode 1 — Operator self-interview (Sprint 13, easiest)**. Operator
records voice notes. Whisper transcribes. Transcript flows into the
substrate's note-taking pipeline as a new ingested source. Same
insight/question structure.

**Mode 2 — Multi-party AI interview (Sprint 16+)**. Operator creates
an "interview project" specifying a topic + target informant list.
Each informant gets a unique link. They click → AI interviewer
conducts a conversation (voice or text). Transcripts feed back into
the substrate. Aggregated across informants, the substrate produces
synthesis as if it had interviewed the whole network.

### 11.2 Data model additions

```sql
-- An interview project bundles related interviews under a topic
CREATE TABLE interview_projects (
    project_id          TEXT PRIMARY KEY,
    title               TEXT NOT NULL,
    topic_description   TEXT,
    created_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deliverable_id      TEXT REFERENCES deliverables(deliverable_id),
    interview_guide     TEXT  -- JSON: AI interviewer's prompt + must-cover questions
);

-- One interview session within a project
CREATE TABLE interviews (
    interview_id        TEXT PRIMARY KEY,
    project_id          TEXT NOT NULL REFERENCES interview_projects(project_id),
    informant_handle    TEXT,  -- operator's label, not real name unless given
    informant_email     TEXT,  -- for invite + notifications
    invited_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    started_at          TIMESTAMP,
    completed_at        TIMESTAMP,
    transcript_document_id TEXT REFERENCES documents(document_id),
    consent_recorded    BOOLEAN NOT NULL DEFAULT FALSE,
    status              TEXT CHECK (status IN (
        'invited', 'in_progress', 'completed', 'declined', 'incomplete'
    ))
);
```

### 11.3 The AI interviewer

A new role at `roles/interviewer/`. Differs from other roles because:

- **Conversational** (multi-turn) rather than one-shot
- **State-machine driven** by interview_guide (must-cover questions
  + adaptive follow-ups)
- **Has memory across the conversation** (uses long context, not
  per-turn dispatch)
- **Produces transcripts** that flow into the substrate's note-taking

Implementation: substrate gains a new orchestration loop (Loop 4 —
Interview) parallel to Loops 1 (research) and 2 (wrestling). Loop 4
manages the conversation state, dispatches each turn through the
substrate's dispatch router (interviewer role → pro tier), persists
the transcript continuously, ends when must-cover questions are
answered or informant explicitly ends.

### 11.4 The informant surface

A new product domain: `interview.antiek.ai`. Per-interview unique
URL. Informant lands on a page with:

- Project title + interviewer's framing ("Operator X is researching
  Y. This is a Z-minute conversation. Your responses will be...")
- Consent checkbox (with link to terms covering use of transcript)
- Voice-or-text mode toggle
- Chat-style conversation interface
- "End interview" button always visible

For voice: WebRTC capture, whisper transcription streaming, AI
interviewer response via text-to-speech (ElevenLabs or OpenAI TTS).
Voice loop adds latency (~3-5s round-trip) but is the right form
factor for the operator's biography use case.

### 11.5 The operator's interview dashboard

In the creation workstation: a new section showing all interview
projects + per-project status (informants invited / completed),
emergent insights surfacing across interviews, open questions
across interviews that suggest "you should interview someone with
expertise in X."

The dashboard reads from the same substrate graph. Insights extracted
from interview transcripts are first-class graph citizens —
indistinguishable from insights extracted from any other source.

### 11.6 Synquery partnership (operator-flagged)

Operator: *"There's this GLG expert AI native company called
Synquery. I'd probably want to engage with a partnership with them
where I could offer my users access to their service and they could
interview anyone to create the building blocks they want for their
books."*

The integration shape (Sprint 18+):
- Operator's substrate identifies "you need to interview someone
  with expertise in X" via the open-question chase
- Operator clicks "find an expert" → Synquery API call
- Synquery returns matching experts + booking flow
- Interview happens through Synquery's platform
- Transcript returned to Antiek as a new ingested source

Sensible only after the creation surface exists and the operator
has accumulated enough graph to know where the expertise gaps are.
Pre-Sprint-11 the substrate doesn't have the demand shape to make
this partnership worthwhile to either party.

### 11.7 Multi-sprint sequence

- **Sprint 13**: operator self-interview / voice note. Whisper
  transcription. Transcript into note pipeline. No multi-party,
  no AI interviewer prompting.
- **Sprint 16**: multi-party AI interview state machine + informant
  UX + interviewer role + project dashboard.
- **Sprint 17**: voice mode (WebRTC + TTS) for the AI interviewer.
- **Sprint 18**: Synquery integration.

---

## 12. Voice note ingestion

The simplest creation-surface form factor. Sprint 13 ships this as
the easiest entry point into the creation workflow.

### 12.1 The flow

1. Operator opens creation workstation, clicks "New voice note"
2. Microphone permission granted, recording starts
3. Operator talks through an idea (could be 2 minutes or 20)
4. Click stop → audio uploaded to substrate
5. Substrate dispatches whisper API for transcription
6. Transcript becomes a new `document_kind: "voice_note"` row in
   the documents table
7. The note_taker role runs on the transcript: extracts insights +
   open questions in the standard format
8. Result: a new set of insight blocks added to the operator's
   graph, available for drag-and-drop into outlines

### 12.2 The prompted-back-by-substrate variant

Operator vision: *"There also should be a loose idea of like
something pushing and prompting the user on the actual content,
prompting on the insights, open questions."*

Variant of the flow: after the transcript is processed and notes
extracted, the substrate identifies gaps (e.g., "you mentioned
X but didn't connect it to Y, which you've discussed in 3 prior
notes"). The substrate generates follow-up prompts.

UI: after a voice note, the operator sees a "Follow-up?" card with
the substrate's prompts. Click → records another voice note in
response. Builds a conversational chain.

This is functionally similar to the AI interviewer but with the
operator as both interviewer and interviewee — the substrate is
just the prompt generator. Lower implementation cost than the
multi-party interview path (no informant UI, no consent flow, no
voice TTS, just whisper + the existing note pipeline + a new
"follow-up prompt" generator role).

### 12.3 Implementation

Sprint 13 ships:
- `acquisition/voice/` adapter (~150 LOC)
- Web UI: recording component (existing browser MediaRecorder API)
- Whisper dispatch (new tier in dispatch config: `transcription`)
- `voice_note_followup` role (~80 LOC) for the prompted-back variant
- Substrate cost: ~$0.006/minute of audio transcribed

---

## 13. Account model + network effects

Operator vision: *"This is an architectural decision that I still
don't know how to make the trade-off of public versus private. Because
I know that I want there to be network effects, but also I'd want
people to have a version where private documents could be sent. But I
guess for now, I don't care about private documents being sent. This
is very, very, very, very, very far down the line."*

### 13.1 Current model (Sprints 11-21 — extended through pay-as-you-go pricing model launch)

**Single-operator, single-graph.** The production VM hosts one
substrate, one DuckDB file, one event log. The operator is the only
user. No accounts, no auth, no isolation.

This is acceptable because:
- `app.antiek.ai` is publicly reachable but no one knows about it
- Only the operator's API keys get burned by abuse (rate limit at the
  Caddy level if it becomes a real problem)
- The operator's research is the only content; nothing private is
  at risk

**The pay-as-you-go pricing-model Phase 1 launch (Sprint 19+) does
NOT force the full multi-user substrate to ship simultaneously.** Per
§9.0.1, the first cohort of individual users can run on a shared
single-graph architecture with per-user `owner_user_id` row scoping
(per §13.10 substrate hygiene) and the shared substrate remaining
operator-curated. The full two-graph architecture (private + public +
shared substrate, §13.2) ships at Sprint 22+ for the architectural
reasons in §13.4 below (compounding hasn't demonstrated yet on the
solo operator graph; premature multi-user destroys the moat that
multi-user is supposed to monetize).

### 13.2 Future model — the personal-graph-as-memory architecture (Sprint 22+)

Per operator voice notes 2026-05-17, the architecture is NOT a single
shared graph with view filters, and it is NOT three separate graph
classes per user. **It is organized around the personal graph as the
user's memory, with public-facing and private-facing partitions inside
the personal graph.** Operator verbatim: *"the personal graph of a
user is different than a private one, as a user can have a public
one. And a user facing one that is public and private. This can be a
user's memory."*

**Three graphs total, with a clear ownership boundary:**

1. **Personal graph (one per user) — the user's memory.** Contains
   every note the user has produced, voice-noted, highlighted, or
   curated. The user partitions notes into **public-facing** (visible
   in the collective graph, earns 70% ad rev-share to the user when
   consumed) and **private-facing** (walled, never reaches the
   collective graph, paid by the user at 50% token margin). The user
   can move notes between private-facing and public-facing at any
   time, with immediate effect on what the collective graph sees.
   **The personal graph is what Antiek Memory (§13.8) exposes to
   external LLMs through API/MCP/CLI** — it IS the user's memory in
   the literal product-naming sense.
2. **Collective graph (one global aggregation).** Built from every
   user's public-facing notes, plus pre-onboarded IP holder content
   (§9.10), plus operator-curated source corpus. This is what the
   free public tier consumes; ad-supported; 70% creator rev-share
   routes to whichever public-facing note generated attention.
   Quality-gated on entry (verification + voice-style scoring +
   source-tier validation per §13.9) before eligibility for
   attribution.
3. **Shared substrate (one global, platform-owned).** Skill versions,
   source-tier rules, rubric registry, attribution algorithm versions,
   RLM env definitions, model routing config. Single-writer at platform
   level via the writer queue.

**The architectural commitment that makes the privacy claim
load-bearing**: the private-facing partition of every personal graph
is **physically separated** at the storage layer (per-user DuckDB
files with per-partition encryption keys), not merely tagged. A query
against a user's private-facing notes cannot, by schema design, write
into the collective graph. This is the database-separation +
audit-log + impossibility-by-design pattern from §13.3 that lets
Antiek say "we are architecturally incapable of leaking your data"
rather than "we promise not to."

**Cross-graph writes flow through the shared substrate, never directly.**
A skill patch derived in a user's private-facing notes (e.g., "Tier-1
sources in neutral atom physics include Lukin lab papers but not
Vuletic preprints") propagates to all users via the shared-substrate
writer queue — not as the patched private content, but as the
**discovered rule**. The user's specific quantum chunks stay walled;
the discovered fact about source tiers propagates as a shared skill
patch with differential-privacy guarantees per §13.3. This is how the
platform learns from private usage without ever exposing private
content — which is the operator's stated requirement: *"such
information I use to make my product better will be de-identified."*

**This is not a small change.** It requires splitting the DuckDB schema
between user-scoped tables (documents, chunks, nodes, edges) and
substrate-scoped tables (skill versions, source-tier rules, rubric
registry). Single-writer DuckDB invariant becomes
**single-writer-per-user-graph plus single-writer-on-substrate**. The
Quack swap point becomes more load-bearing because Postgres handles
this natively while DuckDB's single-file-per-database architecture
makes the boundary cleaner but the implementation more file-system-
coupled.

**Three substrate decisions to make now (Sprint 16-18) to avoid
retrofit cost:**

1. **Adopt the DuckLake pattern early.** Production-ready April 2026.
   Even if the catalog Postgres serves a single tenant for the first
   100 users, having the catalog separation in the data model from day
   one is what enables the Stage 1 → Stage 2 transition (§13.6)
   without rewriting the application layer.
2. **Design encryption keys per-partition inside the personal graph,
   not per-user account.** A user has ONE personal graph (their
   memory, §13.2), and within it multiple project-scoped partitions
   (research projects, biography contexts,
   professional vs personal). Unit of encryption is the graph, with
   per-graph keys wrapped by user master key. Also the natural unit at
   which to measure 50%-margin token pricing (§13.5).
3. **Pick the memory framework architecture now.** Substrate is DuckDB;
   workload is inherently temporal (every claim carries "when did I
   learn this"). Zep's Graphiti pattern (temporal knowledge graph with
   validity windows on facts; LongMemEval 63.8%) is the architectural
   template. Implement Graphiti's pattern in native DuckDB tables
   rather than adopting Zep as a runtime dependency, but the data
   model should match.

### 13.3 Engineering-grade privacy (the differentiator)

Chatbot privacy fear is the single largest unmet need in
knowledge-worker LLM products today. Every analyst, lawyer,
consultant has at least one story about pasting something into
ChatGPT and then panic-deleting the conversation. The product
category that solves this is currently empty. Notion AI doesn't
solve it because Notion is the storage. Claude and ChatGPT don't
because their privacy policies are written by lawyers, not engineers.
A product that ships with **engineering-grade privacy architecture**
has a real differentiator.

**The credibility mechanism is architectural separation, not policy
promise.** Users have been burned by "we don't train on your data"
promises that turned out to mean "we don't train unless you forget to
toggle this setting we changed the default on." Verifiable: database
separation (per-user DuckDB files for private graphs, shared substrate
DuckDB for the collective graph; schema makes accidental cross-graph
writes physically impossible), audit logs, impossibility-by-design.

**Differential privacy for preference telemetry — local-DP shuffler
pattern with per-surface ε budgets.** Per Apple's deployed parameters
(ε = 2 for HealthKit, ε = 4 for emoji, ε = 8 for QuickType) and the
expert consensus band (ε < 1 strong, 1-10 various degrees of better
than nothing, > 10 not meaningful):

- **Skill-invocation frequency**: low sensitivity, ε = 2/day defensible
- **Source-tier preference signals**: medium sensitivity, ε = 1/day,
  explicit opt-in
- **Query-content telemetry**: do NOT collect under DP at any ε that
  preserves utility. Either E2E encryption with no learning, or no
  collection.

The shuffler model (local randomization on-device + third-party
shuffler stripping identifiers before aggregation) is the
architecturally correct pattern. Local-DP alone requires materially
higher ε to achieve same utility because each user contributes only
one noisy sample. The US Census Bureau's ε = 19.61 is the cautionary
tale — too high to be meaningful per multiple peer-reviewed critiques;
not the target.

**Privacy dashboard as first-class product surface.** Real-time view of
every telemetry collected from the user's private graph, with toggles
per category and a "delete everything" button that actually deletes
everything within 30 days. The privacy dashboard is the mechanism by
which users develop trust. Engineering investment is modest (~2-4
engineer-weeks for the DP layer + a few sprints for the dashboard);
the differentiation value is "we are architecturally incapable of
leaking your data" rather than "we promise not to."

### 13.4 Why multi-user delays to Sprint 22+

The substrate compounding thesis (§2.5) — "investigation N+1 is
genuinely cheaper and better than N" — **has not been demonstrated
yet** as of Sprint 16. The operator-graph has 16 sprints of plumbing
and an unknown number of weeks of actual research use. Sprint 11 was
when the workstation became usable. **Six months of operator-graph
accumulation is the minimum demonstration period before multi-user is
the right risk to take.**

The mechanism that argues against early multi-user is **graph
contamination**. Current architecture has one graph, one operator, one
set of source-tier classifications. The compounding asset is that
every investigation deepens specific themes (quantum, defense,
semiconductors, batteries) and the next investigation in those themes
inherits a richer prior. The moment user B opens an account and runs
an investigation on a topic that overlaps operator's themes (and they
will, because those are the popular deep-tech themes), B's
investigation either contaminates the operator's graph or runs against
a stale snapshot. Both options destroy the compounding asset that is
supposed to be the moat.

**The two-graph architecture (§13.2) is the resolution, but it
requires Sprint 22+ engineering work, not a Sprint 19 turn-on.**
Sprint 19 should be operator-graph depth: more sources, more
investigations, accumulated skill patches that demonstrate the
compounding curve. That demonstration is what gets shown in the
peer-distribution motion (§9.0.1) — the operator's research outputs
under the Sanabil byline or personal account, with peers asking what
tool produced them.

### 13.5 Pricing model (operator-decided 2026-05-17)

Per operator voice notes verbatim: **"I will charge people like
OpenRouter by allowing people to set a budget for tokens used, and
for private documents I will charge for token usage on such documents
at a 50% margin. I guess I will charge users for public token
consumption at a 10% margin, but will allow rev share of 70% to them
on the ad placement; So this will incentivize people to consume to
create IP on my platform."**

**Three tiers + developer surface, all pay-as-you-go on tokens:**

1. **Free public tier (the network-effect driver)**: ad-supported
   public-graph consumption on DeepSeek-Flash inference up to a
   generous monthly cap (~5M tokens). No per-token charge under the
   cap. 70% of ad revenue from a public note's attention routes to
   the note's creator. Above-cap users automatically convert to
   paid public consumption (next tier).
2. **Paid public consumption (above cap)**: pay-as-you-go at **10%
   margin** on raw token cost across whichever model the user
   chooses. Ads still on; creators still earn 70% rev-share on the
   ad revenue from sessions that consumed their content.
3. **Paid private use (brainstorming workstation, document wrestle
   on user-uploaded private content, etc.)**: pay-as-you-go at
   **50% managed-service margin** on raw token cost. **No ads.**
   Content stays in the user's private graph, never reaches the
   collective public graph. This is the surface that justifies the
   50% margin because it is the surface where users will pay to
   keep their thoughts private.

**Framing to the user for the 50% private margin**: NOT "we charge
50% margin on tokens" but "we charge a managed-service fee equivalent
to 50% of underlying inference cost, in exchange for the substrate
value (graph infrastructure, attribution, voice/style discipline,
recursive note-taking, brainstorming workstation, two-graph privacy
architecture, etc.)." Same number, different psychology. The
OpenRouter analog the operator named is exact: users set a budget,
get billed for actual token consumption against that budget.

4. **Developer surface (API + MCP + CLI as "Antiek Memory")**:
   usage-based per query. Personal-notes endpoint free for the
   user's own account (it's their data). Public-notes endpoint
   priced per query with the per-query cost flowing through IP
   attribution to publishers (§9) and creators (§13.9). Book
   endpoint priced at publisher contract rate; ships only after
   publisher onboarding (§9.10).

**The mechanism for resolving the public-tier unit-economics
problem**: the free-tier cap. Without a cap, ad revenue per
session ($0.05-$0.20 for 10 minutes at $5-$20 CPM) doesn't cover
token cost ($0.50-$2.50 in tokens at $5/M input). The Scribd failure
mode. With the 5M-token DeepSeek-Flash cap, free-tier CAC is bounded;
above the cap, the user pays 10% margin which is positive contribution.
The 70% creator rev-share stays on both free and paid public tiers
because that's where network effects accrue.

### 13.6 The substrate transition matrix

| Stage | Substrate | Tenancy model | Trigger to migrate |
|---|---|---|---|
| **0** (current) | Single DuckDB file with single-writer agent | Per-user file path | Sustained write contention > 100 writes/sec across all users |
| **1** (Sprint 18-22) | DuckDB per user + shared substrate DuckLake | File-per-user routing in app layer; Postgres catalog | Per-user file count approaches OS handle limits; backup latency exceeds backup window |
| **2** (Sprint 22+) | DuckLake (DuckDB + Postgres catalog) for shared substrate; per-user DuckDB for private graphs | Hybrid: Postgres catalog routes to per-user files | Cross-user analytics queries become a primary workload |
| **3** (post-Series A) | Postgres sharded by user_id for both private and shared; DuckDB for analytical workloads only | Postgres-native multi-tenant (Notion pattern: logical shards across physical DBs) | Per-user query load exceeds single-machine DuckDB capacity |

Realistic forced-move thresholds (inferred from Notion's 2020 trigger
+ DuckDB's stated production limits):

- Stage 0 → Stage 1: ~100-500 concurrent active users with non-trivial
  write rates
- Stage 1 → Stage 2: ~1,000-5,000 users
- Stage 2 → Stage 3: depends on workload mix, not predictable from
  current information

**Encryption at rest is a Stage 1+ requirement for the
engineering-grade privacy claim** (§13.3) — the consumer differentiator
— AND for SOC 2 Type II if/when enterprise procurement becomes
relevant (§13.7 deferred). DuckDB does NOT natively support transparent
file-level encryption; use LUKS or filesystem-level encryption with
per-graph keys in KMS (AWS KMS, GCP Cloud KMS, or HashiCorp Vault).
Substrate-level requirement that must be designed in before user
files are created (retrofit = per-user migration with downtime).

### 13.7 Trust infrastructure: consumer privacy compliance + deferred SOC 2

**Consumer Phase 1 monetization (§9.0.1) does NOT require SOC 2 Type
II attestation.** SOC 2 is the enterprise-procurement compliance
framework; consumer Phase 1 is individual subscribers paying out of
pocket through Stripe, not enterprise procurement. The relevant
compliance frameworks for an individual-subscription consumer
product are:

- **GDPR Article 13/14 transparency** (EU users): privacy notice,
  lawful basis, data-subject rights (access, deletion, portability)
- **CCPA notice + opt-out** (California users)
- **Engineering-grade privacy architecture** (§13.3): differential
  privacy with per-surface ε budgets, two-graph database separation,
  privacy dashboard with real-time telemetry view

**Trust Center publication for consumer users**: build a public-
facing Trust Center by Sprint 22 alongside the multi-user pivot.
Contents: privacy architecture description, DP parameters (epsilon
registry per §13.3), data-retention policy, deletion SLA (30 days),
incident-response process, privacy-dashboard tutorial.

**The substrate hygiene work (encryption at rest, access logging,
change management, vulnerability scanning, backup testing) is
required regardless of SOC 2** — it's the foundation for the
engineering-grade privacy claim consumer users will check, not just
for an enterprise compliance certificate. Build the controls in
Sprint 16-18 hygiene window per §13.10.

**SOC 2 Type II becomes relevant later** ONLY if Antiek ever enters
enterprise procurement workflows (e.g., a corporate strategy team
wants to standardize on Antiek and their procurement asks for SOC 2).
That is not Phase 1, not Phase 2, and may not happen at all if the
consumer thesis holds. If/when it does become relevant, the realistic
13-15 month timeline from substrate controls is: Sprint 22-24
platform onboarding (Drata recommended, Secureframe as budget
alternative ~$5-$7K/year base) → Sprint 28-30 observation window
begins (6 months minimum for enterprise procurement; 3 minimum
technically) → Sprint 40-44 first Type II report. Cost: ~$30-$50K
first year for single-framework Type II all-in.

**The substrate-controls work is in the Sprint 16-18 hygiene window
either way.** The choice between "consumer privacy compliance" and
"SOC 2 Type II" is upstream of the actual engineering work; both
rest on the same controls. The decision to defer SOC 2 is a marketing
and procurement-positioning decision, not a substrate-engineering
decision.

### 13.8 Developer surface (MCP-first)

Per data repository workstream 2 (MCP ecosystem: ~97M monthly SDK
downloads, ~2,000 servers in official Registry, 92% adoption among
2025-2026 agent frameworks per BCG), MCP is the only defensible
**primary** developer surface as of mid-2026. Direct REST API and CLI
ship as secondary.

**Antiek Memory MCP server design (Sprint 19-20):**

1. **Three resources** as first-class URI-addressable entities:
   - `antiek://private/notes/{user_id}/{note_id}` — per-user OAuth
     scope, encrypted at rest, no public exposure
   - `antiek://public/notes/{note_id}` — read-only with
     attribution-routing metadata; all writes through public-notes
     pipeline with prompt-injection filtering
   - `antiek://books/{isbn}/{chunk_id}` — per-publisher licensing
     state; returns chunk OR licensing-required error per §9.0
     retrieval-time gating
2. **Four tools**: `search_personal`, `search_public`, `cite_source`,
   `record_attribution`. The `record_attribution` tool captures the
   attribution event at the agent step that consumed the content,
   not after the fact — this is what makes rev-share work end-to-end
   across the MCP boundary.
3. **Prompt-injection defense**: every public-notes return wraps
   content in `<antiek:content trusted="false">...</antiek:content>`;
   system prompt instructs agent to treat envelope content as data,
   not instructions. OWASP LLM01 mitigation adapted to MCP.
4. **Rug-pull defense**: tool description hashes published in
   `.well-known/mcp-tools.json` manifest; clients verify on every
   refresh. Drift treated as fatal session-termination event (per
   Invariant Labs April 2025 disclosures of MCP rug-pull attacks).

**Naming**: brand as "Antiek Memory" not "Antiek API." This is
load-bearing per §13.2 — the user's personal graph IS the user's
memory, and Antiek Memory is the developer-facing exposure of that
memory to external LLMs. The value proposition to developers is not
"another data API"; it is *"connect your LLM to your user's memory
of everything they've read, thought about, asked, and written,
respecting the public-vs-private partition the user has set up."*
Positions against OpenAI Memory and Anthropic MCP catalog rather
than against Postgres-as-a-service.

**Pricing tiers**:
- Personal-notes API: free for the user's own account (it's their
  data), rate-limited to prevent abuse
- Public-notes API: per-query priced, per-query cost flowing to IP
  attribution per §9.1
- Book API: priced at publisher contract rate; ships ONLY after
  publisher onboarding

### 13.9 User-as-IP-holder framing (Phase 1 architecture, Sprint 19)

**Users producing public notes are first-class IP holders from
day one.** This is operator-decided per voice notes 2026-05-17:
*"So this will incentivize people to consume to create IP on my
platform."* The mechanism the operator named — public notes get
70% ad rev-share to their creator — IS the lock-in mechanism. A
user who has accrued meaningful attribution revenue from their
public notes does not switch platforms easily.

**The architectural commitment**: the same Stripe Connect + account
structure + attribution dashboard that holds pre-onboarded publisher
escrow (§9.10) holds user creator revenue. The populations differ;
the architecture does not. **Four populations sharing one substrate
+ one Stripe Connect integration + one attribution dashboard:**

1. **Free-tier users** consuming public-graph content, generating
   ad views, no payment in or out
2. **Paying private + above-cap public users** paying token margin
   at the operator's three-tier model (§13.5)
3. **Creators** of public-graph contributions, earning 70% of ad
   revenue routed by attribution
4. **Pre-onboarded IP holders (publishers)** with escrow accruing
   until opt-in (§9.10)

**Quality gate on public-graph entry**: voice-and-style discipline
(§5) is enforced on synthesizer prompts but the platform doesn't
control input quality for user-contributed public notes. Users will
paste in low-quality notes and expect attribution revenue. The
mechanism that handles this: public-notes ingest pipeline runs
verification + voice-style scoring + source-tier validation before
eligibility for attribution. Low-quality submissions get rejected
or routed to private graph only. This is the mechanism that prevents
the public graph becoming a content farm.

**Cross-user network effects (Phase 3, Sprint 25+).** Once multi-user
ships (Sprint 22+) and the four populations are live, cross-graph
network effects unlock:

- User A interviews their colleague C; the transcript becomes a
  public document in A's graph
- User B is researching the same topic; B's investigations can cite
  C's transcript via cross-graph search
- The substrate's "ask an expert" flow surfaces user A as a potential
  interview subject for B (with A's opt-in)

This is the **Sprint 25+ network-effects layer**. Depends on:
- Multi-user accounts shipped (Sprint 22+)
- Two-graph architecture proven (§13.2)
- Creator population active and earning meaningful rev-share
- DeepBlu interview surface mature enough for cross-user interview
  requests

The Phase 1 commitment (Sprint 19) is the architecture, the
dashboard, and the rev-share flow for users-as-creators. The
Phase 3 commitment is the cross-graph teleportation that compounds
once enough creators are contributing. Four populations (operator,
paying private + above-cap public users, free-tier creators,
publishers), one
substrate, one set of incentives.

**Quality gate on public-graph entry.** Voice-and-style discipline (§5)
is enforced on synthesizer prompts but the platform doesn't control
input quality for user-contributed public notes. Users will paste in
low-quality notes and expect attribution revenue. Mechanism that
handles this: public-notes ingest pipeline runs verification +
voice-style scoring + source-tier validation before eligibility for
attribution. Low-quality submissions get rejected or routed to private
graph only. This is what prevents the public graph becoming a content
farm.

### 13.10 What to do now

**Substrate decisions only.** No multi-user surfaces ship before
Sprint 22. What CAN and MUST be done now:

1. **DuckLake catalog separation** designed into the data model from
   Sprint 18 (per §13.2 substrate decisions).
2. **Per-graph encryption keys** with KMS escrow (per §13.6).
3. **Owner identifier on every row** — every document, chunk, node,
   edge, investigation carries `owner_user_id` defaulting to a single
   hard-coded value. When multi-user lands, schema needs no
   migration; only application layer changes.
4. **Differential privacy shuffler infrastructure** (per §13.3) —
   ε-budget enforcement at the substrate level, with dashboard UI
   deferred to Sprint 22+ but substrate plumbing live by Sprint 19.
5. **Substrate trust controls** (per §13.7 — foundation for consumer
   engineering-grade privacy claim; also satisfies SOC 2 if/when
   enterprise procurement becomes relevant) — encryption-at-rest +
   access logging + change management + vulnerability scanning +
   backup testing all designed in.

This is **cheap to do now, expensive to do later**. Sprint 16-18
hygiene work.

---

## 14. Sprint sequence (11 → 22 mainline + parallel tracks)

This is the road from "MVP shipped" through Sprint 16 (current state)
through "Wedge 2 notebook + multi-user + payouts + Wedge 5 replay."

### 14.1 Mainline sprint table

| Sprint | Theme | Mainline work | Integration-spec work woven in |
|---|---|---|---|
| **11** ✅ | Research workstation MVP | 3 REST endpoints + voice/style v1 + multi-user schema prep + full Mode A | — |
| **12** ✅ | Multimodal + continuous mode | YouTube + podcast adapters; continuous-mode orchestrator; **Hermes-primary dispatch flip** | — |
| **13** ✅ | Voice notes + creation v0 | Voice acquisition; creative_writer role; deliverables data model; Mode C v0 | — |
| **14** ✅ | Creation drag-drop + X ingestion | Multi-section coherence; browser extension for X; drag-drop UI | — |
| **15** ✅ | Edit-back-into-graph + export | CLAIM_ASSERTED_BY_OPERATOR; deliverable export PDF/EPUB/Substack | — |
| **16** ✅ | IP attribution telemetry + interview machinery | `page_attribution_computed` events; 3 attribution algorithms; interview state machine; AI interviewer role; informant UI | Hermes verify-tier fallback chaos test (cd602c9) |
| **17** | Interview voice mode + **dispatch tier measurement** | WebRTC capture; TTS dispatch tier; streaming whisper; **synthesizer pinned to Opus primary** for 2-week measurement against Hermes/Grok on verifier pass rates (§14.4) | **Storybook scaffold** (PostHog Wedge 1a, half-day); **Lemon UI evaluation decision** (PostHog Wedge 1b spike); **`program.md` per role** (autoresearch INTEGRATE NOW, half-day); **Watch-for-later folder** (§2.6) as Sprint 17 or 18 product surface; **Prime F+D debt** items absorb if first real-LLM eval cycle ships |
| **18** | Publisher dashboard (SPLIT — NOT Synquery) + **Retrieval-time gating** + **Pre-onboarded escrow architecture** + **Notebook surface (linchpin)** | `ip_holders` table with `status: pre_onboarded` + `escrow_balance_usd`; Stripe Connect onboarding; **retrieval-time gating in production BEFORE Stripe Connect activates** (§9.0); **publisher opt-in prerequisite to any payouts** (§9.10) | **Notebook surface Wedge 2** (PostHog) main work ~10 days; **Pricing-page template** (PostHog Wedge 6) for the operator's three-tier pricing model; **DuckLake catalog separation** designed in (§13.10); **substrate trust controls** begin (§13.7) |
| **19** | **Operator's pay-as-you-go pricing model live** + **First-cohort publisher outreach** + **Brainstorming Workstation Surface E** + Developer surface MCP-first + UI upgrade chain | **Three-tier token-budget pricing via Stripe** (§9.0.1 / §13.5): free public tier (DeepSeek-Flash cap), paid public (10% margin), paid private (50% margin); **Antiek Memory MCP server** (§13.8) — 3 resources + 4 tools + signed tool descriptions; **MIT Press + Cambridge + Princeton notification emails** sent (§9.10 first cohort); **user-as-IP-holder dashboard** ships parallel to publisher dashboard (§13.9); **Surface E Brainstorming Workstation** (§4.5) ships with watch-for-later folder + thought-partner workflow + Lego-block slotting | **Command palette** (PostHog Wedge 3); **Ubiquitous AI** (PostHog Wedge 4) if undo affordance ready; **Prompt autoresearch local-only** (autoresearch Wedge 1) parallel side-track scaffolding; **DP shuffler substrate plumbing** (§13.3) |
| **20** | **Visible-artifact growth motion** + Trajectory replay + dispatch tier verdict | Operator uses Antiek and publishes outputs (any pen name, any account); peers who see the outputs ask what tool produced them — individual-to-individual organic discovery through artifact quality; **dispatch tier-measurement verdict** lands (§14.4) — if Grok-on-synthesis within 5pp of Opus, flip back to Hermes-primary; else keep Opus on synthesis | **Trajectory replay viewer** (PostHog Wedge 5); **Autoresearch Wedge 1 ratify-or-REJECT** verdict landing (the Lutke gap test, §15.6); **Phase 8 gate shadow-mode** (autoresearch Wedge 2 prep) |
| **21** | **Synquery integration** + Phase 8 enforcing | Synquery API client (deferred from Sprint 18); **only after creation surface PMF signal** that warrants paying for expert calls | Ubiquitous AI across all surfaces; **Phase 8 gate enforcing** (autoresearch Wedge 2 ratified) |
| **22** | **Multi-user pivot + two-graph architecture** (NOT Sprint 19) | Auth (Clerk/Supabase); **per-user private graphs** + **shared public graph** + **shared substrate** per §13.2; **consumer Trust Center** publication (§13.7) | Privacy dashboard as first-class product (§13.3); DP enforcement live; substrate stage 0→1 transition |
| **23-24** | Phase 4 ad inventory + creator rev-share infrastructure | Lead-gen ad inventory; vertical ad targeting; **70% creator rev-share** (§13.9 user-as-IP-holder) on public-graph contributions | — |
| **25+** | **Phase 3 ad inventory at scale** + **Cross-graph network effects (§13.9)** | Ad inventory live across public consumption surface; **70% rev-share to creators AND opted-in publishers** routes via the existing Phase 1 escrow architecture; cross-graph "ask an expert" flow with user opt-in | **Config sweeps** (autoresearch Wedge 3) IF ≥500 graded outcomes; **Public handbook** (PostHog Wedge 7) IF team >1; **SOC 2 Type II deferred** unless enterprise procurement path opens (§13.7) |
| **30+** | Cross-graph network effects + federation | Cross-user "ask an expert" flow; user-as-IP-holder revenue attribution (§13.9) | Programmatic auction (if scale warrants); vision-capable role |

Each sprint ~5-10 working days. The Sprint 11-16 arc shipped in
~10-12 weeks of focused work; Sprints 17-22 are projected at similar
cadence.

### 14.2 Parallel tracks (off the mainline critical path)

**RLM track** (sequenced inside `rlm_integration_spec.md` as RLM-1
through RLM-5 — independent of mainline sprint numbering to avoid
collision): sequences AFTER Sprint 20's outcomes table populates
enough graded trajectories. The six design decisions in
`rlm_integration_spec.md` §6 await ratification before RLM-1 starts.
Cost-cap discipline mirrors continuous-mode budget caps.

- RLM-1: long-doc wrestling RLM bridge (~600 LOC, load-bearing)
- RLM-2: long-corpus synthesizer RLM mode (~250 LOC)
- RLM-3: `investigation_kind="rlm"` orchestrator (~500 LOC, net-new)
- RLM-4: verifiers envs for the other four roles + `rlm_env.py`
  (~2000 LOC)
- RLM-5: trajectory harvest CLI for `prime-rl`

**Loop 3 unlock track:** strictly gated by the five criteria in
`loop_3_unlock_criteria.md`. No work happens until trajectory volume
+ SFT readiness + validated reward + open-weight justification + eval
headroom are all checked. When unlocked: `integration_prime_intellect.md`
governs whether to use `prime rl run` (DEFERRED until unlock) or the
local SFT loop pattern from `integration_autoresearch.md` Wedge 4
(comparison at unlock time, not before).

**Autoresearch local-only track:** prompt mutation experiments on
operator's local machine, gated to NEVER touch production VM until
ratified. Sprint 19 starts scaffolding; Sprint 20 ratification
verdict. If REJECTed, autoresearch Wedges 2-4 fall and Phase 8 keeps
its current unconditional patching.

### 14.3 Sequencing discipline

- **Wedge 2 notebook surface is the linchpin.** PostHog Wedges 3, 4, 5
  all depend on it. Sprints 18-19 must not slip the notebook.
- **Autoresearch Wedge 1 is the integration ratification gate.** If it
  fails the Lutke-gap test in Sprint 20, autoresearch Wedges 2-4 fall.
  Phase 8 gate work in Sprint 21+ depends on this verdict.
- **The Sprint 18 legal gate is binding.** Retrieval-time gating must
  ship to production AND first publisher must be opted in BEFORE
  Stripe Connect activates any payout. Pre-payout exposure is
  takedown; post-payout exposure is Bartz-level damages on a
  contemporary monetary transaction. The two are not equivalent and
  the gate is not negotiable (§9.0).
- **Synquery slips from Sprint 18 to Sprint 21.** The split is
  binding. Different workflows (publisher onboarding + Stripe + KYC
  + 1099 vs expert sourcing + transcript ingestion), independent
  failure modes, no reason to correlate risk. Synquery activates only
  after creation surface PMF signal that operators want to commission
  expert calls.
- **Multi-user pushes from Sprint 19 to Sprint 22+.** Compounding has
  not been demonstrated yet. Sprint 11 was when the workstation
  became usable; six months of operator-graph accumulation is the
  minimum demonstration period. Premature multi-user destroys the
  moat that multi-user is supposed to monetize (§13.4 graph
  contamination).
- **Hermes-primary dispatch posture is locked for flash/pro/verify
  tiers; synthesizer is under measurement (Sprint 17-20).** Sprint 12
  + cd602c9 chaos test establish the architectural invariant per
  `antiek-hermes-bridge`. Synthesizer is the operator-facing artifact
  and voice/style discipline is synthesizer-level; the dispatch tier
  measurement gate (§14.4) decides whether Grok-4.3 on synthesis
  matches Opus 4.7 within the 5-percentage-point verifier-pass-rate
  tolerance.
- **No work on Loop 3 unlock criteria until the criteria themselves
  pass.** Don't pre-build the SFT loop, the verifiers envs, or the
  hosted RL infrastructure.

### 14.4 Dispatch tier-differentiation measurement gate (Sprint 17-20)

Per data repository workstream 7 + `integration_autoresearch.md` cost
modeling, the Hermes-primary posture is correct for cold research
loop (volume of dispatches builds the graph; substrate quality
emerges from compounding) but **the cost-per-acceptable-synthesis
denominator matters more than cost-per-call** for the synthesizer
specifically.

**Synthesis is the artifact that gets read by humans, edited, and
exported.** Voice and style discipline (§5) is a synthesizer-level
requirement. Grok 4.3 has not been benchmarked on long-form English
research writing the way Claude Opus 4.7 has. Routing synthesis to
Grok primary is a bet on Hermes Bridge + Grok producing verifier-
passing synthesis at acceptable rates. Maybe true; not yet measured.

**Measurement protocol** (Sprint 17 begin, Sprint 20 verdict):

1. **Pin synthesizer tier to Opus 4.7 via OpenRouter primary with
   Hermes fallback** for the measurement window.
2. **Run 2 weeks** of normal investigation traffic.
3. **Measure verifier pass rates per provider** on synthesis outputs.
4. **Verdict criteria** at end of measurement:
   - If Grok-4.3-on-synthesis passes verifier within 5 percentage
     points of Opus-on-synthesis: flip back to Hermes primary on
     cost grounds.
   - If gap is larger: cost savings on synthesis are illusory because
     they convert to additional verifier and re-synthesizer dispatch.
     Keep Opus on synthesis as primary.

**The volume argument cuts the other way once synthesizer is the
binding artifact.** Cost per synthesis is not the right denominator;
cost per **operator-acceptable** synthesis is. If Grok produces three
rejections for every one Claude acceptance, the cost ratio is the
inverse of the per-call ratio.

**Verify tier stays as configured** (Hermes primary, OpenRouter
fallback, property-tested at `tests/test_dispatch_fallback_chain.py`).

---

## 15. Strategic open questions

Each of these needs a real answer at the inflection point flagged.
They're not blockers for the immediate sprints but they shape what
the substrate becomes.

### 15.1 The legal posture question (must answer by Sprint 16)

Currently substrate ingests "everything online." The IP attribution
phase (Sprint 16+) implicitly distributes this content to ad
viewers. That's distribution + monetization of scraped content.
Almost certainly not defensible under current US copyright law (fair
use covers research-only use; not monetized distribution).

**Possible postures**:
- A. Pre-opt-in only. IP holders must affirmatively join before
  their content gets surfaced in attribution. Slow path; depends
  on attribution economics being attractive enough.
- B. Fair-use-defended. Argue that synthesis is transformative use,
  source attribution is sufficient. Untested at scale.
- C. Hybrid. Some content classes (academic papers, government
  documents, public-domain books) ingested freely; others (books
  in copyright, Substack, paywalled journalism) require opt-in.

Recommended: **C, with the operator's lawyer involved before Sprint 16
ships**. Each content class gets a policy tag at ingestion time;
attribution layer respects the policy.

### 15.2 The browser-extension question (must answer by Sprint 14)

X ingestion via API is impractical. A browser extension that captures
threads + tweets on operator click is the workable path. But:

- Extension distribution requires Chrome Web Store review (~weeks)
  or sideloading (only operator + small group)
- Extension permissions are a separate consent surface
- Multi-browser support multiplies effort (Chrome / Arc / Firefox /
  Safari)

Recommended: **ship as a Chrome-only sideloaded extension first**,
operator-only distribution, validate that the workflow works,
formal Web Store distribution in a later sprint.

### 15.3 The voice interview latency question (must answer by Sprint 17)

WebRTC capture + streaming whisper + TTS round-trip is ~3-5 seconds
end-to-end. That's awkward for natural conversation. Options:

- Accept the latency; train operators to use the rhythm
- Use a smaller faster whisper model (loses accuracy)
- Pre-generate likely interviewer follow-up questions in parallel
  (cuts the "thinking" latency)
- Switch to a synchronous voice model (OpenAI Realtime API,
  Anthropic's voice mode when available) — cuts latency but
  introduces a dependency on a different cost/availability model

Recommended: **start with async (Sprint 17), evaluate moving to
synchronous in Sprint 23+**.

### 15.4 The competitive durability question (no sprint deadline)

Cloudflare, OpenAI, Anthropic, Perplexity, even Notion AI all have
stronger distribution / capital / brand than Antiek. What's
Antiek's durable competitive position?

The honest answer: **the substrate is the moat**. 12 sprints of
typed event log, dispatch routing, role environments, recursive
chase architecture. That's hard to replicate. The UI is replicable
in a quarter. The substrate is not.

This means: never let UI ambition push the substrate to compromise.
Specifically: never compromise the single-writer DuckDB invariant
to get a flashier UI. Never compromise the typed event log to
get faster prototyping. The substrate's discipline IS the product.

### 15.5 Wedge 2 (notebook) adoption — will the operator actually use it? (must answer by end of Sprint 19 + 4 weeks)

`integration_posthog.md` §16.2 names this explicitly. Wedge 2 ships
BOTH the notebook AND the chat-feed; operator picks per use case.
After 4 weeks of operator use:

- If chat-feed usage <20% of notebook usage: notebook is the ceiling;
  deprecate chat-feed in Sprint 21
- If chat-feed usage >50%: notebook isn't the right primitive for
  quick-question use cases; reframe as "deep-read mode only"
- In between: both surfaces stay; the operator's choice is the answer

**Recommended:** ship both, instrument both via the event log, decide
after 4 weeks of operator behavior data. No design call needed before
ship.

### 15.6 The Lutke gap — does autoresearch's mechanic survive LLM-judged metrics? (must answer by end of Sprint 20)

`integration_autoresearch.md` §10.6 names this as the load-bearing
question for the whole autoresearch integration. Lutke's Shopify
result was on a deterministic metric (render time). Antiek's metrics
are LLM-judged. **No published evidence yet that the
propose-execute-measure-gate mechanic survives the deterministic →
LLM-judged transition.**

Wedge 1 ratification IS the test. Verdict lands by end of Sprint 20.
If REJECTed: autoresearch Wedges 2-4 fall; the integration ends
honestly rather than getting salvaged by lowering the bar. If
RATIFIED: Wedges 2-4 sequence per their own unlock criteria.

### 15.7 RLM bridge design decisions — six awaiting ratification (must answer before RLM-1 starts)

`rlm_integration_spec.md` §6 has six design decisions blocking RLM-1:
RLM-as-bridge stance, cost attribution to root role, $5 session cap,
subllm_role_tiers flash split, per-iteration event granularity,
64K-token wrestling threshold.

**Recommended:** ratify the six decisions in a single review session
when RLM-1 sequences into priority (after Sprint 20). Pre-Sprint-20
they're premature to litigate.

### 15.8 The Prime Intellect F+D debt (must absorb into Sprint 17 or 19)

`integration_prime_intellect.md` INTEGRATE NOW called for items F
(trajectory→verifiers schema compat test) + D (`prime eval run`
against a 50-example `parameter_extractor_v0.jsonl`) at "Sprint 10."
Sprint 10 shipped without them. They are debt.

**Recommended:** absorb into Sprint 17 IF the first real-LLM
evaluation cycle ships in that window; otherwise defer to Sprint 19
(when prompt autoresearch needs the same compat-test infrastructure).
Either window is defensible; both keep the items inside the
near-term horizon.

### 15.9 The Sprint 18 legal gate — is retrieval-time gating in production before payouts ship? (binding NOW, Sprint 18)

§9.0 names this. The operator-stated gate "operator's lawyer involved
before Sprint 16 payouts" was technically preserved because Sprint 16
shipped telemetry without money flowing. Sprint 18 ships Stripe Connect
on the same attribution algorithm — that's the same decision deferred
by one sprint, not resolved.

Three options surfaced (§9.0): Option A (purge restricted content,
breaks moat — REJECTED), Option B (gate at attribution time, documented
unjust enrichment — REJECTED), Option C (gate at retrieval time —
ACCEPTED). The binding question is whether Option C is implementable
and in production by Sprint 18 ship date.

**Recommended:** Sprint 18 has TWO prerequisites that must be met
before Stripe Connect activates any payout: (a) retrieval-time gating
in production, (b) at least one publisher opted in. If either is
unmet at Sprint 18 ship, defer the Stripe Connect activation to
Sprint 19. Do NOT ship payouts on an ungated graph.

### 15.10 The operator's pay-as-you-go token-budget pricing IS the monetization model (operator-decided 2026-05-17)

The pricing model lives in §9.0.1 and §13.5 verbatim from the
operator's voice notes. The shape is **OpenRouter-style pay-as-you-go
token-budget pricing**: users set a budget for tokens used; the
platform bills against actual consumption at three margin tiers (free
public DeepSeek-Flash cap, paid public 10% margin, paid private 50%
margin) + 70% creator rev-share on ad revenue + developer surface
(API + MCP + CLI as Antiek Memory, §13.8) priced at usage. This is
hard-to-vary creative work the operator did across voice notes
2026-05-17. The structure is non-negotiable substrate-level
commitment, not a design space to explore.

If a sprint plan or integration spec ever proposes a different
monetization shape, escalate to the operator and treat the proposal
as a substrate-level question, not a sprint-level decision.

### 15.11 The dispatch tier-differentiation question (Sprint 17-20 measurement)

§14.4 names this. Synthesizer is the operator-facing artifact; voice
and style discipline is synthesizer-level; Grok 4.3 has not been
benchmarked against Opus 4.7 on long-form English research writing.
The Hermes-primary posture (cost-optimization through volume) may not
hold on the synthesis tier because the binding denominator is
cost-per-acceptable-synthesis, not cost-per-call.

**Recommended:** the measurement protocol in §14.4 is the answer.
Sprint 17 begins; Sprint 20 verdict lands. No design call before the
verdict.

### 15.12 The watch-for-later product surface — does it actually unlock private graph usage? (4-week post-ship measurement)

§2.6 introduces this as an operator product insight. The strategic
claim is that the brainstorming workstation is where users park
unsharpened questions and pay 50% margin on private token consumption.
The mechanism is real but the willingness-to-pay at that price point
is not yet validated.

**Recommended:** ship in Sprint 17 or 18, instrument every parked
question and every launched investigation, measure 4 weeks of operator
behavior data. If operator uses watch-for-later >3 times per week, the
product hypothesis holds. If <1 time per week, deprecate the surface
and absorb the voice-note path into the existing workstation.

---

## 16. What we explicitly do NOT do

Discipline list. Each of these is a real temptation that someone
will propose. The answers are settled. Re-litigate only if the
underlying assumption changes.

- **Horizontal scaling of the FastAPI process.** The
  `InvestigationCoordinator` holds per-investigation futures in-
  process. `--workers 4` corrupts the DuckDB single-writer
  invariant. Migration to Postgres (substrate-level decision)
  is the only correct path to scale.
- **Migrating off DuckDB without explicit substrate sprint.**
  DuckDB is the substrate's foundation. Moving to Postgres /
  Snowflake / etc is a 2-sprint architectural change, not a
  config flip.
- **Adding more tools "just in case."** No Daytona, no Modal, no
  Momentic, no Pulumi until a specific problem warrants it.
  Substrate stays tool-thin.
- **Pre-building features for hypothetical users.** Multi-user
  accounts, federation, RLHF training loops, payment processing
  — all are real long-term needs, all are deferred until the
  operator has used the current surface for weeks and demand
  signals are concrete.
- **Rendering MASTER.md as a bulleted list.** Voice and style
  discipline is non-negotiable. Anything that forces enumerated
  output where prose belongs gets rejected.
- **Auto-deploying on git push.** Manual `ansible-playbook
  deploy.yml` is the right friction level. CI/CD becomes correct
  when there's a second committer, not before.
- **Adding monitoring beyond systemd journals + Caddy access
  logs.** Prometheus, Grafana, Datadog, Sentry — all defer until
  there's a real on-call situation. Operator + journalctl is the
  right surveillance level at this scale.
- **Letting the daemon's chase budget exceed $5/day by default.**
  Cost runaway is the failure mode that turns Antiek into a
  $5000/month surprise charge. Hard caps in code, configurable
  upward by the operator, never default-uncapped.
- **Compromising voice/style discipline to ship faster.** A
  shipped slop-feeling product loses the operator. A delayed
  non-slop product keeps them. Always optimize for the latter.
- **Treating insights as anything other than provenance-grounded.**
  Every claim cites chunks. Every chunk cites documents. Every
  document has an `ip_holder_id` (even if null today). The
  provenance graph is the substrate's compounding asset; never
  break the chain.

### 16.1 Consolidated REJECTs from integration specs

The four integration specs (§17) each carry their own REJECT lists.
These are canonical at product-strategy level and re-stated here so
they cannot be quietly re-opened by a sprint-level decision.

**From `integration_posthog.md` §12:**

- **No ClickHouse + Kafka migration.** DuckDB single-writer is the
  substrate. Re-evaluate only via explicit substrate sprint.
- **No plugin marketplace.** Zero third-party developers; theater.
- **No copying PostHog's voice / mascot / tonal register wholesale.**
  Antiek has its own voice discipline (§5.5). Pattern transfers;
  tone does not.
- **No HogQL-style user-facing query language for the graph.** No
  power users; re-evaluate Sprint 25+ only.
- **No multi-tenant org/team/billing surfaces before the multi-user
  pivot.** Sprint 19 builds these as part of multi-user; not earlier.
- **No 25+ acquisition adapters by parity to PostHog destinations.**
  Different shape (research-pull vs CDP-push). Adapter count is
  driven by operator's actual source needs.
- **No multi-product nav before its time.** Sprint 19+ alongside
  multi-user.
- **No rrweb DOM-mutation capture.** Antiek records typed events,
  not DOM.

**From `integration_autoresearch.md` §9:**

- **No rewriting the investigation loop in autoresearch's shape.**
  Category error — knowledge research ≠ ML systems research.
- **No using autoresearch as a dispatch substrate.** Collides with
  Hermes-primary posture.
- **No publishing role prompts Hub-style.** Asymmetric IP reversal.
- **No targeting Karpathy's "100 experiments overnight" cadence.**
  Cost-bound, not throughput-bound.
- **No git-commit-per-change at substrate level.** Duplicates
  `ANTIEK_PARAM_VERSION` discipline.

**From `integration_prime_intellect.md` §5:**

- **No Prime as a dispatch provider.** Verify tier needs cross-family
  independence; synthesis tier needs Opus; flash/pro tiers are 3-10×
  more expensive on Prime. Reversible only when an Antiek-trained
  checkpoint wins on §D eval.
- **No Hub publishing of envs or methodology.** Methodology is the
  product; asymmetric reversal cost.

These rejections are not deferred decisions; they are settled
negative. Re-open only if the underlying assumption changes
meaningfully — e.g., an Antiek-trained checkpoint actually winning
the §D eval would reopen the Prime-as-dispatch-provider question.

### 16.2 Additional REJECTs from the data-repository sharpening (2026-05-18)

**On positioning and strategy:**

- **No "four products" framing.** The substrate is the moat (§2.5).
  Separating products would have meant separating graphs, which would
  kill the cross-corpus knowledge-graph value that IS the product
  thesis. The biography wedge, the research workstation, the
  brainstorming surface, the creation tool — all one substrate. Re-
  raised in the May 2026 reframing analysis and explicitly REJECTed.
- **No "Cursor for research" mental model wholesale.** Cursor has no
  substrate; Antiek does (§1, §2.5). The analog applies at inference
  routing (don't train, route to providers — already Antiek's
  Hermes-primary posture) but NOT at the substrate. Reframing Antiek
  as "Cursor for research" misses the moat.
- **No "Spotify-pattern" framework as Phase 1 strategy.** That
  framework is correct for Phase 3+ (Sprint 25+ ad-supported public
  surface with publisher rev-share). Pulling it into Phase 0/1 is the
  Bartz failure mode that just cost Anthropic $1.5B. Phase 1
  monetization is the operator's pay-as-you-go token-budget model
  (§9.0.1, §13.5), not IP-payouts.
- **No biography-first MVP pivot.** The May 2026 reframing analysis
  recommended biography-as-MVP as the cleanest IP-zero wedge. Operator
  ratified the substrate-is-moat unification (§2.5). Biography stays as
  Surface D (§4.4); it is not the MVP wedge replacement for the
  research workstation.

**On legal posture:**

- **No payouts on an ungated graph.** Sprint 18 ships ONLY after
  retrieval-time gating in production + first publisher opt-in
  (§9.0, §15.9). Pre-payout exposure is takedown; post-payout
  exposure is Bartz-level damages on a contemporary monetary
  transaction. The gate is not negotiable.
- **No pre-onboarded escrow active against unconsenting rights
  holders.** Google Books precedent (Judge Chin's 2011 rejection of
  the Amended Settlement Agreement) defeats opt-out-by-default. Escrow
  framework activates ONLY when publisher has affirmatively opted in
  (§9.10).
- **No commingled escrow funds.** Cash only, segregated regulated
  accounts at a real fiduciary institution. Mechanically distinct from
  operating funds. If "we have your money waiting" is going to be the
  framing, it must be a verifiable statement.

**On substrate and architecture:**

- **No multi-user before Sprint 22.** Compounding has not been
  demonstrated yet. Premature multi-user destroys the moat that
  multi-user is supposed to monetize via graph contamination (§13.4).
- **No single-graph-with-view-filters as the multi-user model.** Two-
  graph architecture (private + public + shared substrate) is the
  resolution (§13.2). View-filter shortcuts that share underlying
  storage between users are explicitly excluded.
- **No epsilon > 10 on any DP claim.** Per the expert consensus band
  (§13.3), ε > 10 is not a meaningful privacy guarantee. The Apple
  Tang-et-al. precedent is the cautionary tale on overstating DP
  claims; the Census ε=19.61 is the cautionary tale on under-engineered
  DP at scale. Per-surface budgets stay in the 1-8 range.
- **No DuckDB migration off without an explicit substrate sprint.**
  Reiterated from §16 above with sharpening: the DuckLake transition
  (Stage 1) is a planned migration with a designed catalog-Postgres
  separation; the Postgres-sharded transition (Stage 3) is the
  contingency. Neither happens as a config flip.

**On publisher relationships:**

- **No Pearson as textbook anchor.** Pearson+ direct-to-student
  strategy signals disintermediation appetite. Cengage is the textbook
  anchor; McGraw-Hill secondary. Pearson approached last in the
  publisher sequence, if at all (§9.6 sequenced onboarding).
- **No MFN on publisher equity.** Spotify precedent issued preferred
  shares with NO equity MFN — only standard licensing MFN on rate
  cards. Equity stake compresses naturally through subsequent rounds.
  Pulling an equity MFN into the term sheet creates a cap-table block
  on later capital formation.
- **No publisher equity above 15% combined.** Spotify's combined
  founding grant was ~17-18% across five rights-holders; compressed
  to ~7% combined by 2024. A book platform allocating 15%+ to anchors
  blocks future capital formation. Allocate aggressively to first 3
  signers (12% combined) and reserve only 3% for all subsequent
  signers in aggregate (§9.6).

**On the developer surface:**

- **No CLI as the primary developer surface.** CLI is the developer
  experience layer (third in the stack); MCP is the primary; REST API
  is secondary universal substrate (§13.8). Building the CLI as a
  parallel implementation rather than as a wrapper over the API is the
  rejection.
- **No book API before publisher contracts.** The Antiek Memory MCP
  server's three resources include `antiek://books/{isbn}/{chunk_id}`
  but the resource returns licensing-required errors until publisher
  contracts execute. Shipping the book resource before contracts is
  the rejection.

**On unit economics:**

- **No unlimited public-tier consumption.** Scribd failure mode. Free
  public tier caps at 5M tokens/month on DeepSeek-Flash, then converts
  to paid at private rate (§13.5). Any pricing model that doesn't cap
  consumption is rejected.
- **No fresh deep-research queries on the ad-supported tier.** Fresh
  queries cost $3-$10 in tokens; ad revenue per session is $0.05-$0.20.
  Pure ad-supported fresh queries lose money structurally. Fresh
  queries are paywall-gated or rate-limited (§13.5).

---

## 17. Integration spec hierarchy and precedence

Four peer integration specs sit alongside this master spec. Each
owns a ratified verdict matrix for one external system or framework.
Their wedge mechanics and REJECTs are canonical within their domains.

### 17.1 The four integration specs

**`integration_posthog.md`** — UI / design / product / website patterns
(MIT-licensed PostHog core). The Wedge 2 notebook surface is the
largest single product upgrade in Sprints 18-19; Wedges 3-5 chain off
it. Eight REJECTs guard against ClickHouse migration, plugin
marketplace, voice/mascot copying, HogQL-style query language,
multi-tenant surfaces before pivot, parity-adapter inflation,
multi-product nav before its time, and rrweb DOM capture. §16.1
consolidates these as canonical.

**`integration_autoresearch.md`** — Karpathy's
propose-execute-measure-gate loop (MIT, 630 LOC). Wedge 1 (prompt
autoresearch for the synthesizer role, local-only) is the
ratification gate for the whole integration. Sprint 19 starts;
Sprint 20 verdict. The Lutke-gap question is open — see §15.6. Five
REJECTs cover the category errors (rewriting investigation loop,
using as dispatch substrate, Hub-style prompt publishing, throughput
targeting, git-commit-per-change).

**`integration_prime_intellect.md`** — Verifiers env + GEPA + hosted
RL (Prime Intellect open-source stack). F+D debt items (compat test
+ eval runner) absorb into Sprint 17 or 19 per §15.8. Hosted
`prime rl run` strictly DEFERRED behind `loop_3_unlock_criteria.md`.
Prime-as-dispatch-provider + Hub publishing explicitly REJECTed.

**`rlm_integration_spec.md`** — Recursive Language Models for
long-doc wrestling, long-corpus synthesis, RLM-mode orchestration.
Six design decisions in spec §6 await ratification per §15.7. RLM
track sequences as parallel-to-mainline AFTER Sprint 20
outcomes-table populates (§14.2).

### 17.2 Precedence order

When this master spec conflicts with another:

1. `architecture_notes.md` — substrate-level commitments
   (load-bearing; never violate)
2. `loop_3_unlock_criteria.md` — gates ALL training-time work
3. This master spec — product vision + sprint sequencing
4. `strategy/voice-and-style-discipline.md` — quality bar for prose
   AND UI (extended in §5.5)
5. Integration specs — verdict matrices, wedge mechanics, REJECTs
6. Sprint-specific specs (`sprints/sprintN-*.md`) — execution
   detail for the active sprint

When precedence (1), (2), or (4) conflict with any integration spec
wedge, the substrate / unlock-gate / discipline wins. The integration
patterns are the means; the substrate is the moat (§2.5); the
researcher's-notebook product proposition is the end. **Never
substitute the end for the means.**

### 17.3 When a new integration spec gets authored

New integration specs follow the existing template (see any of the
four above). Required elements: header status + scope, mapping
section showing where the foreign system's primitives map to
Antiek's, verdict matrix with INTEGRATE NOW / WEDGE 1..N / DEFER /
REJECT categories, per-wedge unlock criteria, risks + mitigations,
sprint placement, open questions, "what to do now," final note
with precedence reference.

The discipline is rigorous-defensible-not-consensus-hedging
(per `feedback_architectural_rigor`).

---

## Final note for the implementing agent

This spec is the master reference. The four integration specs in
§17.1 are peer documents; their wedge mechanics and REJECTs are
canonical within their domains. The precedence order is in §17.2.

If §17.2's precedence (1) substrate commitments and any integration
spec wedge ever conflict, escalate to the operator. The substrate's
commitments are non-negotiable; integration patterns can be re-shaped.

Sprint 17 (`sprints/sprint17-*.md` once authored) is the immediate
work. The Sprint 17 integration-spec items — Storybook scaffold
(PostHog Wedge 1a), Lemon UI evaluation decision (PostHog Wedge 1b),
`program.md` per role (autoresearch INTEGRATE NOW) — are half-day-each
side-tracks that don't compete with the interview-voice mainline
work. Begin there.
