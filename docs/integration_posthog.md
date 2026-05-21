# Antiek × PostHog — UI, Design, Product & Website Integration Spec

> **SUPERSEDED 2026-05-21** — §5.3's "load-bearing serif notebook" verdict was
> reversed by the operator. The new direction is a layered Antarctic workspace
> with the **Werner the penguin** mascot and sun-yellow outlining (`#F5DF24`)
> as the constant brand mark, day + night both first-class. See the full
> programme spec at `docs/ui_redesign_posthog/index.html` and the brand bible
> at `docs/ui_redesign_posthog/brand_werner.html`. The reasoning below is
> preserved for context — most of it still holds (Storybook, Notebook surface,
> Lemon-style discipline). The §5.3 "adopt yellow accent anyway would hurt
> the product" verdict is the specific finding that no longer applies; we now
> adopt a different, sharper yellow (`#F5DF24`, not PostHog's `#FFD329`) and
> a different mascot (Werner the penguin, not PostHog's Max hedgehog).

**Status**: Draft v1, 2026-05-18.
**Scope**: Decide which UI primitives, design patterns, product patterns, and
website/marketing patterns from PostHog (MIT-licensed core, separate `ee`
license) integrate into Antiek, which are deferred behind unlock criteria,
and which are explicitly rejected as misfits. Produce defensible verdicts,
not consensus hedging.
**Predecessor docs**: `architecture_notes.md` (substrate-level commitments),
`master-product-spec.md` (product vision + four surfaces + sprint sequence),
`strategy/voice-and-style-discipline.md` (the existing voice discipline this
spec must NOT conflict with), `sprints/sprint11-web-app-mvp.md` (the current
web app shape), peer integration specs at `integration_prime_intellect.md`,
`integration_autoresearch.md`, `daytona_integration_spec.md`,
`rlm_integration_spec.md`.
**Operator quality bar**: intellectual honesty, rigor, defensibility. Explicit
REJECT verdicts where warranted. No "PostHog does it so we should too"
framings. The right question is always "what specific Antiek problem does
this pattern solve, and is it a better solve than what we'd build native."

---

## Table of contents

1. [What PostHog actually is (and what's reusable)](#1-what-posthog-actually-is-and-whats-reusable)
2. [What does NOT transfer — the misreadings to avoid](#2-what-does-not-transfer--the-misreadings-to-avoid)
3. [Mapping PostHog's primitives to Antiek's surfaces](#3-mapping-posthogs-primitives-to-antieks-surfaces)
4. [Verdict matrix](#4-verdict-matrix)
5. [Wedge 1 — Lemon UI evaluation + Storybook scaffold](#5-wedge-1--lemon-ui-evaluation--storybook-scaffold)
6. [Wedge 2 — Notebook surface for Loop 2](#6-wedge-2--notebook-surface-for-loop-2)
7. [Wedge 3 — Universal command palette](#7-wedge-3--universal-command-palette)
8. [Wedge 4 — Max-style ubiquitous AI assistant (the "everywhere chat")](#8-wedge-4--max-style-ubiquitous-ai-assistant-the-everywhere-chat)
9. [Wedge 5 — rrweb-style trajectory replay](#9-wedge-5--rrweb-style-trajectory-replay)
10. [Wedge 6 — Transparent pricing page pattern](#10-wedge-6--transparent-pricing-page-pattern)
11. [Wedge 7 — Public handbook discipline](#11-wedge-7--public-handbook-discipline)
12. [Explicit rejections (don't re-litigate)](#12-explicit-rejections-dont-re-litigate)
13. [Risks and mitigations](#13-risks-and-mitigations)
14. [Unlock criteria for promoting wedges](#14-unlock-criteria-for-promoting-wedges)
15. [Sprint placement](#15-sprint-placement)
16. [Open questions (genuinely unresolved)](#16-open-questions-genuinely-unresolved)
17. [What to do now](#17-what-to-do-now)

---

## 1. What PostHog actually is (and what's reusable)

PostHog is a self-hostable, mostly-MIT-licensed product analytics platform —
analytics, session replay, error tracking, feature flags, experiments,
surveys, data warehouse, CDP, and an in-app AI assistant ("Max") — built as
a multi-product platform behind one UI. Repo is 51% Python (Django), 40%
TypeScript (React), 7% Rust. ClickHouse for event storage. Kafka for
ingestion. Dagster for batch. **None of those backend choices apply to
Antiek**; the value to read here is the UI/design/product/website layer.

The pieces worth examining as candidates for Antiek integration:

### 1.1 Lemon UI

**MIT-licensed**, npm-installable as `@posthog/lemon-ui`. PostHog's
in-house component library replacing Ant Design. Components include
`LemonButton`, `LemonTag`, `LemonInput`, `LemonModal`, `LemonTable`,
`LemonSelect`, `LemonCard`, etc. Documented in PostHog's Storybook.

### 1.2 Notebooks

Unified literate-analysis surface. One page combines: queries (trends,
funnels, retention, paths, lifecycle, SQL), event/person/cohort
references, session replays + playlists, feature flags, surveys, images,
external links, markdown prose, LaTeX. Single-author at a time
(conflict detection, not multiplayer). External sharing not yet
shipped. The editor appears to be TipTap-based (block-structured
ProseMirror).

### 1.3 Max — the in-app AI assistant

In-app chat that is **ubiquitous, not just a sidebar**. Surfaces "when
editing filters, writing SQL, or watching session replays." Deeply
connected to product data + event schema. Can navigate the UI itself
(modify filters, create insights, construct dashboards). Implementation
not publicly documented in detail.

### 1.4 The pricing page

A calculator. Pay-as-you-go with generous free tier. "More than 90% of
companies use PostHog for free." Founder voice on the page itself: "We
make a profit with every product." Free-tier limits prominently
displayed (1M events, 5K replays, 1M flag requests). No card required
for free. A mascot ("Hogzilla") used playfully.

### 1.5 The handbook

15 numbered chapters of internal operations, public. Covers origin,
product philosophy, business model, organization, values & direction.
Voice is conversational and direct — "This handbook simply explains
how we work." Treated by PostHog as one of their most important
assets — a marketing artifact AND an operating artifact.

### 1.6 Multi-product UI architecture

The repo's `/products/` directory holds each product module (analytics,
replay, flags, experiments, surveys, etc.). Frontend has a left-nav
organized by product. Cross-product nav patterns: a universal command
bar, persistent project/team/organization switcher, in-app billing.

### 1.7 Storybook discipline

Component documentation is first-class. Stories for each component;
visual regression catches; serves as the design-system source of
truth in lieu of a separate Figma library.

---

## 2. What does NOT transfer — the misreadings to avoid

These are the patterns PostHog uses well but that are wrong for Antiek's
current state. Each becomes a REJECT in §12 unless explicitly upgraded.

### 2.1 PostHog is multi-tenant SaaS. Antiek is single-operator pre-launch

PostHog's UI assumes orgs, teams, projects, billing, member roles, API
keys per user. Antiek today has one operator, one VM, one graph (per
master-product-spec §13.1). Adopting org/team/billing surfaces before
the multi-user pivot (Sprint 19+) is pre-building for hypothetical
users — explicitly forbidden by master-product-spec §16.

### 2.2 PostHog has 25+ integration destinations. Antiek has acquisition adapters, which are not the same shape

PostHog destinations push events outward (BigQuery, Snowflake, S3,
Webhooks). Antiek's `acquisition/{arxiv,books,urls,youtube,podcasts,
voice,twitter}` adapters pull sources inward. The "I want X destinations"
goal applies to PostHog because they're a CDP. Antiek is not a CDP.
Skip the analogy.

### 2.3 PostHog's plugin marketplace works because there are third-party developers

A plugin marketplace requires (a) a published extension SDK, (b) a
community submitting plugins, (c) ops to review and approve. Antiek
has zero third-party developers. A plugin marketplace before there's
a single external contributor is theater. Different rejection from
§12.6 below.

### 2.4 ClickHouse + Kafka are correct for event analytics. They're wrong for Antiek's research substrate

PostHog ingests millions of events per second per tenant. Antiek's
volume is hundreds to thousands of trajectory events per investigation.
DuckDB single-writer (architecture_notes §2.3) is correct at Antiek's
scale and fights with Antiek's substrate constraints. Migrating to
ClickHouse is a multi-sprint architectural change with no current
demand signal — same logic as the master-product-spec §16 "no
migration off DuckDB without explicit substrate sprint."

### 2.5 PostHog's voice/tone is theirs. Antiek already has its own voice discipline

PostHog's tone is conversational, irreverent, hedgehog-mascotted. It
**earned** that voice by being good at the product first. Copying the
tone (em-dashes notwithstanding) would conflict with Antiek's existing
voice-and-style discipline at `strategy/voice-and-style-discipline.md`,
which is about absorbing the source corpus's vocabulary, NOT injecting
SaaS-startup levity. The valuable lesson from PostHog is "have a
documented voice and enforce it," not "use this specific voice."

### 2.6 PostHog's marketing-as-handbook works because they're a 50+ person company

The handbook's 15 chapters cover team structure, recruitment, ops
decisions, compensation. Antiek has one operator. Most chapters would
be empty or N=1. The pattern transfers when Antiek has team and ops to
document — not before.

### 2.7 Lemon UI is one option; Antiek already has Tailwind + custom components

`apps/reading/` is Vite + React 18 + TypeScript strict + Tailwind +
pdf.js. Replacing custom components with Lemon UI is a real evaluation
question — but it's not free. Migration cost vs. ongoing component
maintenance cost has to be modeled. Default is NOT "switch because
PostHog uses it"; default is "evaluate and pick."

---

## 3. Mapping PostHog's primitives to Antiek's surfaces

| PostHog primitive | Closest Antiek analog | Mapping cleanliness |
|---|---|---|
| Lemon UI components | `apps/reading/src/components/{ClaimCard, NotesPanel, ChatInput, MasterMdViewer, ...}` | Medium — overlap on buttons/tables/inputs/modals; Antiek's domain components (ClaimCard, MasterMdViewer) have no Lemon equivalent |
| Notebooks (literate analysis) | Loop 2 wrestling surface; current chat-feed in `NotesPanel.tsx` | **Strong analog — and a real product upgrade.** Notebooks encompass "all of PostHog"; Antiek's Loop 2 currently encompasses one document. A notebook surface could unify Loops 1+2 |
| Max in-app AI assistant | `ChatInput` + wrestling bridge in `interfaces/research/api/wrestling.py`; the Research Workstation's chat input | Strong analog — same chat-first pattern but Antiek's chat is per-document or per-investigation, not ubiquitous |
| Pricing page calculator | None — Antiek hasn't monetized | Direct adoption template when monetization happens (Sprint 18+) |
| Handbook (15 chapters, public ops) | None — Antiek is solo pre-launch | Direct adoption template when team + multi-user (Sprint 19+) |
| Multi-product left-nav with module switcher | `App.tsx` route-based 3-pane layout | Medium — Antiek has 4 surfaces (Research / Wrestle / Write / Interview); the multi-product nav pattern fits, but the surfaces are smaller than PostHog's product count |
| Storybook design-system discipline | None — Antiek has no component documentation surface | Direct adoption — pure-upside hygiene |
| rrweb-style session replay | The append-only typed event log at `~/.antiek/research_events/*.jsonl` | **Strong analog.** Antiek already has the recorded trajectory; what's missing is the replay viewer. rrweb itself is MIT — directly vendorable for DOM-level replay if needed |
| ClickHouse + Kafka | DuckDB + in-process | Anti-mapping — see §2.4 |
| Plugin marketplace | None — and shouldn't have one yet | Anti-mapping — see §2.3 |
| HogQL (SQL dialect compiling to ClickHouse) | `substrate/graph/search.py` + `traverse.py` recursive-CTE algorithms | Weak — Antiek's graph ops are already in Python; no immediate need for a query language layer |

The strongest analogs are **notebooks**, **Max-style ubiquitous chat**, and
**rrweb-style trajectory replay**. The cleanest pure-upside hygiene wins are
**Storybook scaffold** and (potentially) **Lemon UI evaluation**. The
website patterns (pricing, handbook) are templates for when their
preconditions land.

---

## 4. Verdict matrix

| Wedge | What it is | Verdict | Why |
|---|---|---|---|
| **Wedge 1: Lemon UI evaluation + Storybook scaffold** | Evaluate `@posthog/lemon-ui` against current custom Tailwind components; ship Storybook as design-system documentation regardless | **INTEGRATE NOW — Sprint 17 substrate-side hygiene (Storybook); evaluation decision in Sprint 17 itself** | Pure-upside on Storybook. Lemon UI is a real evaluation question, not a default-yes |
| **Wedge 2: Notebook surface for Loop 2** | TipTap-based literate document that can embed: a PDF region selection, a Claim card, a Note, a question, a cross-doc link, prose, an image. Replaces or augments current NotesPanel chat feed | **INTEGRATE — Sprint 18-19 main work (deferred during Sprint 17 interview voice work)** | Strong product upgrade. The chat-feed UI in NotesPanel.tsx is the right baseline; the notebook is the right ceiling. Real defect this fixes: chat feeds are hard to re-read; notebooks invite re-reading. Same insight applies to MASTER.md viewer too |
| **Wedge 3: Universal command palette** | Cmd+K palette that searches: investigations, documents, claims, notes, open questions. Cross-surface navigation | **INTEGRATE PHASE 2 — Sprint 19** | Real UX upgrade. Antiek has 4 surfaces and a graph with thousands of nodes; navigation is the bottleneck. Cmd+K is the right primitive |
| **Wedge 4: Max-style ubiquitous AI assistant** | Make the chat surface available from every screen, not just the wrestle/workstation; context-aware (knows current selection, current investigation) | **INTEGRATE PHASE 2 — Sprint 19-20** | Antiek already HAS chat in two surfaces (research workstation + wrestle); the Max pattern is about ubiquity + UI-action capability. The "AI can modify filters and navigate" part is the upgrade |
| **Wedge 5: rrweb-style trajectory replay** | Visual scrubber for an investigation's event log. Play back the 8-phase trajectory as it happened, frame by frame | **INTEGRATE PHASE 2 — Sprint 19-20** | Operator-graded trajectories require re-reading; the event-log JSONL is hard to re-read raw. A replay viewer makes graded outcomes (Wedge 2 of integration_autoresearch.md) much more accurate |
| **Wedge 6: Transparent pricing page pattern** | Calculator-driven pricing page; free-tier prominent; "we make a profit on every product" voice; no card on free | **DEFER — gated on monetization. Sprint 18-19 publisher dashboard or whenever the first paid surface ships** | Template ready when the trigger lands. Don't build the page before monetization exists |
| **Wedge 7: Public handbook discipline** | 15-numbered-chapters-style public ops doc | **DEFER — gated on team + multi-user. Sprint 19+ at earliest** | Most chapters would be N=1 today; pattern transfers when preconditions land |
| **Adopt ClickHouse for event storage** | Migrate Antiek's event log from JSONL+DuckDB to ClickHouse | **REJECT** | No current need; multi-sprint substrate fight; violates the no-migration-off-DuckDB discipline |
| **Build a plugin marketplace** | SDK + submission flow + review pipeline | **REJECT** | No external developers exist; theater |
| **Copy PostHog's tone/mascot wholesale** | Replace Antiek's voice-and-style discipline with PostHog-style irreverence | **REJECT** | Conflicts with `strategy/voice-and-style-discipline.md`; PostHog's tone is theirs |
| **HogQL-style SQL surface over the graph** | A user-facing query language compiling to substrate graph ops | **REJECT FOR NOW (re-evaluate Sprint 25+)** | Antiek's graph ops are programmatic; no user demand for a query language; substrate is single-operator |

---

## 5. Wedge 1 — Lemon UI evaluation + Storybook scaffold

### 5.1 What it does

Two distinct pieces under one wedge. Sequence them in the order below.

#### 5.1a Storybook scaffold (DO NOW)

`apps/reading/` adds Storybook for every existing custom component
(`ClaimCard`, `NotesPanel`, `ChatInput`, `MasterMdViewer`, `NotesFeed`,
`CrossDocSidebar`, `PdfViewer`). Each gets `*.stories.tsx`. No
component changes; just documentation.

Cost: ~half a day. Value: design-system source of truth lives next to
the code, visual regression catches structural breakage during Wedge 2
notebook work, future contributors (including Claude Code) can read
the component contract without inferring it from usage.

#### 5.1b Lemon UI evaluation (DECIDE NOW, EXECUTE LATER IF YES)

Spike: `npm i @posthog/lemon-ui` in a branch, replace one component
(`ChatInput` is the lowest-risk candidate — straightforward textarea
+ button), measure:

- Bundle size delta (current `apps/reading/` production build is 532 KB
  main + 2.2 MB pdf.worker; Lemon UI adds X)
- TypeScript strict compatibility (Antiek's tsconfig is strict; Lemon
  UI must compile clean)
- Tailwind interoperability (Antiek uses Tailwind; Lemon UI ships its
  own styling layer)
- Visual fit (does it match Antiek's voice-and-style aesthetic, which
  is serif/researcher's-notebook, not SaaS-dashboard)

**Decision criteria** (yes if all three):
- Bundle size delta < 80 KB gzipped
- Visual fit passes operator's eye test (the serif/notebook aesthetic
  isn't broken)
- At least 60% of `apps/reading/`'s component surface can plausibly
  migrate

**Decision criteria for NO**:
- If any of the three fails
- If migration cost exceeds 3 days of work

If NO: keep Antiek's custom components + Tailwind. Storybook still
ships independently (5.1a). The evaluation is the deliverable.

### 5.2 Why this wedge ships first

- Storybook half is **zero risk, half-day cost, pure-upside hygiene**.
  No reason to defer.
- Lemon UI evaluation must happen before Wedge 2 (notebook surface)
  starts, because the notebook UI will need many new components
  (block menus, drag handles, embed cards) — and the build-vs-adopt
  decision is cheaper to make once, upfront.

### 5.3 The honest concern

Antiek's existing aesthetic — serif typography, researcher's notebook
feel, no forced bullets in prose (master-product-spec §5.3, §6.1) — is
**load-bearing for the product proposition**. Lemon UI's aesthetic is
SaaS-dashboard. The visual-fit criterion in §5.1b is not cosmetic; it's
preserving the thing that makes Antiek's output something the operator
wants to read.

If Lemon UI fails the visual-fit criterion, the evaluation is the
defensible answer — adopting it anyway "because PostHog uses it" would
hurt the product.

---

## 6. Wedge 2 — Notebook surface for Loop 2

The highest-leverage product integration. Detailed because it's the
wedge that ships real product value.

### 6.1 What it does

A new view at `app.antiek.ai/wrestle/<document_id>/notebook` (and
later `app.antiek.ai/investigations/<id>/notebook`) that renders a
literate-analysis document. Block types:

- **Markdown prose** — operator's own writing
- **Region embed** — a PDF region selection with citation
- **Claim card** — same data as current `ClaimCard.tsx`, embeddable
  inline
- **Note** — emergent note from `roles/note_taker/`
- **Question card** — open question, possibly with linked answer
  documents
- **Cross-doc link** — bridging note + source/target documents
- **Chat exchange** — operator question + claims returned (replaces
  the current chat-feed as one block type, not the whole surface)
- **MASTER.md section** — a synthesis fragment, possibly the whole
  MASTER.md
- **Image** — for diagrams (Layer-4 artifact at
  `~/.antiek/artifacts/<hash>.html` could render inline)
- **LaTeX** — for quantitative claims with equations

### 6.2 Technology choice

**TipTap** (ProseMirror-based, MIT-licensed). PostHog's Notebooks use
this; the React adapter is mature; block-structured docs serialize
cleanly to JSON.

Storage: notebook documents are a new `notebooks` table in DuckDB
(`document_id`, `investigation_id`, `title`, `content_json`, version
fields). Each block carries either prose, a substrate reference
(claim_id, note_id, question_id, region_id, chunk_id, document_id),
or both. **Substrate references are NOT denormalized into the notebook
JSON** — the notebook stores the reference; the renderer pulls the
current substrate state at render time. This preserves the substrate-as-
source-of-truth invariant (architecture_notes §13).

### 6.3 Why this is the right product upgrade

Operator quote from master-product-spec §4.2: *"if I wanted to start
without starting with a question but start with a document, I think
the natural flow would be to take notes on that document in this
insights and open questions formatting."*

The current Loop 2 surface is chat + claim cards + sidebar. It's
linear, append-only, hard to re-read. Operator's vision for the
deeper-read use case (research memo accumulation across multiple
sessions on one document) is **fundamentally notebook-shaped**, not
chat-shaped. PostHog's Notebooks pattern is the right primitive.

It also feeds Wedge 5 (rrweb-style trajectory replay): a notebook
is a static document; a replay is the dynamic generation of one. Same
object viewed two ways.

### 6.4 Single-author vs multiplayer

PostHog's Notebooks are single-author with conflict detection, NOT
multiplayer. **Match this.** Antiek is single-operator anyway;
multiplayer is a Sprint-19+ multi-user concern. Conflict detection
in a single-author setting is just "someone has the notebook open in
two tabs" — handle with the same pattern PostHog does (warn on save,
let user choose).

### 6.5 The relationship to MASTER.md viewer

MASTER.md is the Loop 1 deliverable; notebook is the Loop 2 working
surface. They are NOT the same thing:

- **MASTER.md** is generated, signed by the synthesizer role,
  represents the substrate's view of the answer to a question
- **Notebook** is operator-curated, represents the operator's view of
  what mattered from a corpus of investigations

Both render the same underlying claim/chunk/document references but
through different lenses. **The notebook can embed a MASTER.md
fragment** (a section, a thesis component, a falsification condition).
A MASTER.md cannot embed a notebook — flow is one direction.

### 6.6 Acceptance criteria

- Operator can open a PDF, highlight regions, ask questions, get
  claims, all current Loop 2 functionality — but inside the
  notebook surface instead of the chat-feed
- Operator can interleave prose blocks between claim cards (the
  literate-analysis affordance)
- Operator can export a notebook as Markdown (and later PDF via
  Sprint 15's deliverable export path)
- Substrate references remain live — if a claim's grounding verdict
  changes after the notebook was authored, re-opening the notebook
  shows the updated verdict
- The chat-feed remains available at `app.antiek.ai/wrestle/` for
  operators who prefer it; the notebook is at
  `/wrestle/<id>/notebook`. **Both ship; operator picks.**

### 6.7 Estimated effort

Sprint 18-19 main work. Approximately:
- TipTap integration + block schema + JSON serialization: ~3 days
- Block-type renderers for each substrate reference: ~3 days
- New REST endpoints (`POST /notebooks`, `GET /notebooks/{id}`,
  `PUT /notebooks/{id}`) + new DuckDB table + migrations: ~1 day
- Export to Markdown: ~half a day
- TS codegen for notebook block types: ~half a day
- Tests (notebook schema, block rendering, substrate-reference
  freshness, export): ~2 days

Total: ~10 days of focused work. Fits inside Sprint 18 or split
across 18-19.

---

## 7. Wedge 3 — Universal command palette

### 7.1 What it does

Cmd+K (Ctrl+K on Windows/Linux) opens a global search palette. Indexed:
- Investigations (by title, by topic, by recency)
- Documents (by title, by source, by recency)
- Claims (by text, by chunk, by source tier)
- Notes (by text, by source event)
- Open questions (by text, by document)
- Skills (by domain, by version)
- Surface routes ("go to /wrestle/<doc>", "go to /write/<deliverable>")
- AI actions ("ask a question", "start an investigation", "open the
  most recent notebook")

The palette uses fuzzy matching client-side over a substrate-pushed
index. Index updates flow through the existing WebSocket event feed.

### 7.2 Why this is PHASE 2 not NOW

The substrate already has the data; the new surface is one component.
But it depends on **what's worth indexing** being known — and the
notebook surface (Wedge 2) adds new indexable content. Order is:
notebooks first, then palette indexes notebooks alongside the rest.

### 7.3 Why this is high-leverage

PostHog's UI has the same palette; the value compounds with corpus
size. Antiek's corpus is intentionally growing (the graph as
compounding asset, master-product-spec §2.3). At investigation #50,
flat navigation is fine. At investigation #500, the operator can't
remember which investigation contained the claim they're trying to
re-find. The palette is the antidote.

### 7.4 Implementation note

The palette must be **substrate-event-aware**: when a new
investigation completes, the index updates within seconds.
WebSocket fan-out already exists for the wrestling bridge; reuse.

---

## 8. Wedge 4 — Max-style ubiquitous AI assistant (the "everywhere chat")

### 8.1 What's distinctive about Max vs Antiek's current chat

Antiek currently has chat in two places: the Research Workstation
(Sprint 11 — for starting investigations) and the Wrestle surface
(Sprint 2 — for region-scoped questions). Both are **modal-feeling**;
operator goes TO the chat to use it.

Max is ubiquitous: it surfaces "when editing filters, writing SQL,
or watching session replays." The chat is **inline**, present where
the operator already is. Max can also navigate the UI itself —
modify filters, create insights, build dashboards.

### 8.2 What this would mean for Antiek

Two affordances:

1. **Inline chat presence on every surface.** Persistent slide-out
   chat panel (right edge, collapsible) available from every route.
   Context-aware: knows current investigation, current document,
   current selection.
2. **UI-action capability.** Chat can take actions: "highlight the
   load-bearing claims in this synthesis," "filter notes to
   high-confidence only," "open the source PDF at the page that
   supports this claim," "spawn a chase investigation on this open
   question." Each action emits a typed event so the trajectory log
   captures the AI's UI-driving behavior.

### 8.3 Why this is PHASE 2 not NOW

- The substrate-side event types for AI-driven UI actions need
  definition first. Each "AI clicked X" should be a typed event so
  the trajectory remains complete.
- Context-awareness across all four surfaces requires the route-
  context being threaded everywhere. Not hard, but a real refactor.
- Sprint 17 is interview voice mode; Sprint 18 is publisher
  dashboard + Synquery. Both full. Wedge 4 fits Sprint 19-20.

### 8.4 The dangerous shape — the AI taking actions

PostHog's Max can modify dashboards. Antiek's equivalent would be
an AI that modifies the operator's notebook, the operator's
MASTER.md, the operator's chase configuration. **This requires
explicit undo affordances.** Substrate already supports versioning
(`ANTIEK_PARAM_VERSION`); the UI just needs to surface "undo last
AI action" + "show me what changed."

Without robust undo, ubiquitous AI assistance becomes ubiquitous
risk. Wedge 4 ships only when undo is wired through the typed event
log.

---

## 9. Wedge 5 — rrweb-style trajectory replay

### 9.1 The exact analog

PostHog uses **rrweb** (MIT-licensed) to record and replay DOM
sessions. Antiek already has the equivalent recording — the typed
event log at `~/.antiek/research_events/*.jsonl`. What's missing
is the replay viewer.

### 9.2 What it would do

Open `/investigations/<id>/replay` (or `/notebooks/<id>/replay`,
or any trajectory). The view: a scrubber across the trajectory
timeline, frame by frame showing what was rendered. Click any event
to see its full payload. "Play" auto-advances through the events
at configurable speed.

For Loop 1 (research): see the 8-phase decomposition, evidence
retrieval, parameter extraction, connector, synthesizer steps
as they happened.

For Loop 2 (wrestling): see the region selections, distillation
requests, claims returned, challenges raised, grounder verdicts,
notes emerged — as they happened.

### 9.3 Why this matters

The operator-graded outcomes table (`middleware/outcomes/`) requires
the operator to *re-read* trajectories. Currently re-reading means
parsing JSONL. A replay viewer is the right interface for grading.
It also makes Wedge 4 of integration_autoresearch.md (config sweeps)
viable, because grading 500 trajectories without a replay viewer is
infeasible.

### 9.4 Technology choice

Antiek does NOT need to vendor rrweb itself — rrweb captures DOM
mutations, which Antiek doesn't record. What Antiek needs is the
**concept**: timeline scrubber + event-at-time renderer + playback
controls. Implementation is React + the existing WebSocket event
feed in reverse (replay events from JSONL into the same components
that render them live).

Estimated effort: ~5 days. New module
`apps/reading/src/components/TrajectoryReplay/`.

### 9.5 Why this is PHASE 2

Depends on Wedge 2 (notebook surface) being the canonical render
target. A replay is dynamic-rendering-of-notebook-state-over-time;
the notebook surface defines the rendering vocabulary. Sequence:
notebook ships → replay viewer reuses notebook block renderers.

---

## 10. Wedge 6 — Transparent pricing page pattern

### 10.1 The pattern, decomposed

PostHog's pricing page has four distinctive properties:
1. **A real calculator.** Pick products, slide usage volumes, see
   dollar amounts.
2. **Free-tier limits prominently displayed.** 1M events, 5K replays,
   etc. — not hidden in fine print.
3. **No card on free.** Friction removed for the dominant case (90%+
   of users).
4. **Founder voice on the page itself.** "We make a profit with every
   product." The pricing page is a marketing artifact, not a
   conversion funnel.

### 10.2 Why DEFER

Antiek has not monetized. Master-product-spec §16 explicitly defers
"pre-building features for hypothetical users." The pricing-page
pattern is the right pattern WHEN the trigger lands — but it has no
fit until Sprint 18+ publisher dashboard or another paid surface
ships.

### 10.3 When it lands

Sprint 18 publisher dashboard introduces Stripe Connect for IP-holder
payouts. That's not a pricing-for-Antiek-users surface — it's a
payout surface. The first time Antiek charges its users is later,
likely:
- Sprint 19+ multi-user pivot (per-user-graph SaaS pricing)
- Or Sprint 23+ scale (ad-inventory + creator monetization)

When that trigger lands, the four properties in §10.1 are the
template. Build the calculator, lead with free-tier limits, no card
on free, founder voice on the page. Don't pre-build.

### 10.4 The explicit thing NOT to copy

PostHog's mascot (Hogzilla) on the pricing page. The mascot belongs
to PostHog's identity. Antiek's identity (per the voice-and-style
discipline) is researcher's-notebook serious, not SaaS-mascotted.
**Pattern transfers; mascot does not.** This is the discipline
generally for every wedge below: extract the structural pattern,
discard the surface aesthetic.

---

## 11. Wedge 7 — Public handbook discipline

### 11.1 The pattern, decomposed

PostHog's handbook is:
- 15 numbered chapters
- Conversational, direct voice ("This handbook simply explains how
  we work")
- Public at `posthog.com/handbook`
- Covers origin, product philosophy, business model, organization,
  values, direction
- Acts as both internal ops doc AND marketing artifact

### 11.2 Why DEFER

Most of those chapter topics are N=1 today. "Team structure" is
"one operator." "Compensation" is "operator self-funds." "How we
hire" is "we don't, yet." Writing a public handbook with most
chapters empty is performative.

Master-product-spec §13 says the multi-user pivot is Sprint 19+.
The handbook pattern unlocks at multi-user-with-team — Sprint 22+
at the earliest, possibly Sprint 25+.

### 11.3 What CAN happen now

Two pieces of the pattern transfer immediately:
1. **The conversational, direct voice for any operator-facing
   prose.** Antiek's `strategy/voice-and-style-discipline.md` already
   constrains synthesis prose. The same discipline extended to any
   future docs/blog/marketing surface is consistent.
2. **Operating decisions documented as they're made.** Antiek's
   `docs/` directory already has `architecture_notes.md`,
   `master-product-spec.md`, `integration_*.md` specs. These ARE
   the proto-handbook. Naming them consistently and treating them
   as artifacts (not throwaways) is the pattern.

### 11.4 What does NOT transfer now

Public exposure. Until Antiek has a public-facing audience worth
documenting for, the handbook lives in `docs/`, not on a marketing
site.

---

## 12. Explicit rejections (don't re-litigate)

Stated once. The verdicts are settled. Re-open only if the underlying
substrate or product state changes meaningfully.

### 12.1 REJECT: Migrating to ClickHouse + Kafka

No current need. Antiek's event volume is hundreds to thousands per
investigation, not millions per second per tenant. DuckDB single-writer
discipline (architecture_notes §2.3) is correct at this scale and is
the substrate's foundation. The migration cost is multi-sprint, and
the trigger (analytics-platform scale) doesn't exist. **Same logic as
master-product-spec §16 "no migration off DuckDB without explicit
substrate sprint."**

### 12.2 REJECT: Building a plugin marketplace

PostHog's marketplace requires an SDK + a community + a review process.
Antiek has zero external developers. Theater. Re-evaluate only if
Antiek's public surface eventually attracts contributors AND there's
demand for third-party extensions. Not before.

### 12.3 REJECT: Copying PostHog's voice, tone, or mascot wholesale

Antiek has its own voice discipline. PostHog's voice is conversational,
irreverent, hedgehog-mascotted SaaS-startup. Antiek's voice is
researcher's-notebook serious. Adopting PostHog's tone would conflict
with `strategy/voice-and-style-discipline.md` and damage the product
proposition. **The valuable lesson is "have documented voice discipline
and enforce it"; the specific voice is theirs.**

### 12.4 REJECT: HogQL-style user-facing query language for the graph

Antiek's graph operations are programmatic (Python in `substrate/graph/`).
Exposing a SQL-like surface for power users is real future work but
has no current demand signal — there are no power users yet, just one
operator. Master-product-spec §16 discipline applies: no pre-building
for hypothetical users. Re-evaluate Sprint 25+ if and when external
analysts use Antiek directly.

### 12.5 REJECT: Multi-tenant org/team/billing surfaces before multi-user pivot

PostHog's UI assumes orgs, teams, projects, billing, member roles.
Antiek's multi-user pivot is Sprint 19+ (master-product-spec §13).
Building the multi-tenant UI scaffolding before then is the exact
pre-building forbidden by master-product-spec §16. The wedges in this
spec that touch multi-user (handbook, pricing-page) are explicitly
DEFER, not REJECT — they unlock when the precondition lands. The
multi-tenant UI itself is a Sprint-19+ build, scope of that sprint, not
this spec.

### 12.6 REJECT: 25+ acquisition adapters modeled on PostHog's destination matrix

Different shape. PostHog destinations push events out (CDP). Antiek
acquisition adapters pull sources in (research). Adapter count is
driven by operator's actual source needs, not by parity to PostHog's
destination list. Sprint 12 added YouTube + podcasts because the
operator wanted them; future adapters land the same way.

### 12.7 REJECT: Building the multi-product navigation pattern in Sprint 17

Even though Antiek has 4 surfaces (Research / Wrestle / Write / Interview),
the multi-product nav is a Sprint 19+ shape question. Sprint 17 is
interview voice mode (full slate). Sprint 18 is publisher dashboard
(full slate). The multi-product nav fits naturally with the multi-user
work — both are about surfacing complexity to users. Don't sequence it
earlier.

### 12.8 REJECT: rrweb DOM-mutation recording itself

Antiek doesn't need DOM recording — the typed event log IS the
recording. Vendoring rrweb's capture code is unnecessary mass. Wedge 5
adopts the **concept** (timeline scrubber + replay) but builds it
against the existing event log.

---

## 13. Risks and mitigations

### 13.1 Aesthetic divergence

**Risk:** Lemon UI, the notebook surface, the command palette, and the
trajectory replay viewer all introduce more UI surface. If those
surfaces drift toward SaaS-dashboard aesthetic (which is Lemon UI's
native style), Antiek's researcher's-notebook identity erodes.

**Mitigation:**
- Wedge 1's visual-fit criterion (§5.1b) is a hard gate
- The voice-and-style discipline is extended to UI choices, not just
  prose. Add a §X to `strategy/voice-and-style-discipline.md`
  governing visual decisions when Wedge 1 lands.
- Operator's eye test on every new surface before it merges

### 13.2 Pattern adoption without preconditions

**Risk:** the handbook and pricing-page wedges are templates for when
their preconditions land. Premature adoption (e.g., publishing an N=1
handbook because PostHog has one) is performative and hurts.

**Mitigation:** explicit unlock criteria (§14 below). No wedge ships
without its preconditions checked.

### 13.3 Lemon UI vendor risk

**Risk:** PostHog could change Lemon UI's API, deprecate it, or
restrict it to MIT-with-conditions. Antiek would inherit any churn.

**Mitigation:**
- Wedge 1 evaluation explicitly tests bundle size + TS strict compat
- If Lemon UI is adopted, version-pin in `package.json`
- The components Antiek uses most (ChatInput, ClaimCard) have native
  fallbacks — they originated as custom components and could revert
- The decision criteria in §5.1b are designed to keep Antiek's native
  components viable as the fallback

### 13.4 Notebook abandonment

**Risk:** the operator builds a notebook surface (Wedge 2) but
continues to use the chat-feed (because muscle memory). The notebook
becomes a feature that exists but doesn't change behavior.

**Mitigation:**
- Wedge 2 ships BOTH surfaces (notebook AND chat-feed). Operator
  picks based on use case (deep re-readable analysis vs. quick
  question)
- Acceptance criteria (§6.6) include "operator interleaves prose
  blocks between claim cards" — if operator never does this, the
  notebook is failing its differentiation
- Track usage in the event log (every notebook open + edit emits
  events). Operator can self-audit after 4 weeks

### 13.5 The Max-pattern AI-action surface

**Risk:** Wedge 4 ships an AI that takes UI actions. Bad actions
(deleting a notebook, modifying MASTER.md) damage operator's work
silently.

**Mitigation:**
- Every AI action emits a typed event (architecture_notes §13.1 —
  events are how Antiek's trajectory stays intact)
- Undo affordance MANDATORY before Wedge 4 ships (§8.4)
- AI actions are gated to operator-confirmation for destructive
  operations (delete, overwrite). Read-only navigation actions can
  fire freely

### 13.6 Wedge sequencing drift

**Risk:** the spec sequences notebook → palette → AI ubiquity →
replay viewer. Each depends on the prior. If Wedge 2 (notebook)
slips, the whole chain slips.

**Mitigation:**
- Sequencing is documented in §15 sprint placement
- Wedges 6 and 7 (pricing, handbook) are not in the chain — they
  unlock on separate triggers and can ship out of order
- Storybook (5.1a) ships first and standalone; it's value
  regardless of the chain

---

## 14. Unlock criteria for promoting wedges

Each wedge has explicit gates. Crossing them is the ratification event.

### 14.1 Wedge 1 (Lemon UI + Storybook) unlock criteria

For Storybook (5.1a, INTEGRATE NOW):
- [ ] No precondition. Ship.

For Lemon UI adoption (5.1b):
- [ ] Bundle size delta < 80 KB gzipped
- [ ] TS strict compile clean
- [ ] Tailwind interop verified
- [ ] Operator's visual-fit eye test passes
- [ ] At least 60% migration coverage projection

If all closed → adopt. If any fails → keep custom components; Storybook
still ships.

### 14.2 Wedge 2 (notebook surface) unlock criteria

- [ ] Wedge 1 evaluation decided (adopt-or-don't on Lemon UI before
      block-renderer work starts)
- [ ] New `notebooks` table designed and migration written
- [ ] TipTap block-schema typed in Pydantic + TS codegen
- [ ] Substrate-reference freshness mechanism designed (renderer pulls
      live state, not denormalized JSON)
- [ ] Sprint 18 or 19 has dedicated capacity (~10 working days)

### 14.3 Wedge 3 (command palette) unlock criteria

- [ ] Wedge 2 shipped (palette indexes notebooks alongside other content)
- [ ] Substrate-event-aware index update path designed (WebSocket fan-out)
- [ ] At least 50 investigations + 200 documents in the production
      VM's graph (the palette's value depends on corpus density)

### 14.4 Wedge 4 (ubiquitous AI assistant) unlock criteria

- [ ] Wedge 2 shipped (notebook is the canonical context-aware surface)
- [ ] Undo affordance through the event log designed and
      operator-reviewed
- [ ] Typed event vocabulary for AI-driven UI actions added to
      `substrate/schemas/events.py`
- [ ] At least one AI action class implemented as a vertical slice and
      validated (e.g., "highlight load-bearing claims") before the
      ubiquity-pattern fans out

### 14.5 Wedge 5 (trajectory replay) unlock criteria

- [ ] Wedge 2 shipped (notebook block renderers are the replay's render
      target)
- [ ] Outcomes table populated with ≥50 graded investigations (the
      replay's primary use case is grading; without graded outcomes,
      it's a feature looking for a use case)

### 14.6 Wedge 6 (pricing page pattern) unlock criteria

- [ ] First paid surface shipped (Sprint 18 publisher dashboard OR
      first paid-user offering)
- [ ] Pricing decision made (free tier limits, per-product cost)

### 14.7 Wedge 7 (handbook discipline) unlock criteria

- [ ] Multi-user pivot shipped (Sprint 19+)
- [ ] Team grown beyond N=1 (or operator decides public-ops-as-marketing
      is worth N=1's empty chapters)

---

## 15. Sprint placement

| Sprint | Theme | PostHog-pattern work |
|---|---|---|
| **17** | Interview voice mode | **Storybook scaffold (Wedge 1a)** — half a day, side-track during voice work. **Lemon UI evaluation (Wedge 1b) decision** by end of sprint |
| **18** | Publisher dashboard + Synquery | **If pricing surface ships here, apply Wedge 6 template.** Main sprint slate is full; notebook deferred to Sprint 19 |
| **19** | Multi-user accounts (start) + **Wedge 2 (notebook surface)** | The big build. Notebook surface as main work alongside the multi-user pivot. Wedge 3 (palette) and Wedge 4 (ubiquitous AI) sequence in late-sprint if capacity |
| **20** | Multi-user / payouts | **Wedge 3 (command palette)** if not done in 19. **Wedge 5 (trajectory replay)** if outcomes table populated. **Wedge 4 (ubiquitous AI)** main work if undo affordance ready |
| **21-22** | Phase 4 ad inventory | Wedge 4 fan-out across surfaces. Wedge 6 (pricing) lands as ad inventory monetizes |
| **22+** | Scale | **Wedge 7 (handbook)** if team grows + operator chooses to go public |

**Critical sequencing constraint:** Wedge 2 (notebook) is the linchpin.
Wedges 3, 4, 5 all depend on it. Don't sequence those before Wedge 2
ships.

**What's not on the critical path:** Wedges 1a (Storybook), 6 (pricing),
7 (handbook). These can land independently of the notebook chain.

---

## 16. Open questions (genuinely unresolved)

These are the questions this spec does NOT settle.

### 16.1 Does Lemon UI's aesthetic fit Antiek's researcher's-notebook identity?

The Wedge 1b visual-fit criterion IS this question's answer. No way to
decide in advance — spike, evaluate, decide. The spec commits to running
the evaluation; the outcome is whichever the evaluation finds.

### 16.2 Should the notebook replace or augment the chat-feed?

§6.6 says BOTH ship; operator picks. The honest concern: maintaining
two surfaces doubles future UI work. If after 4 weeks the chat-feed
is used <20% of notebook usage, deprecate the chat-feed in Sprint 21.
If it's used >50%, the notebook isn't the right primitive for
quick-question use cases and should be reframed as "deep-read mode
only."

### 16.3 Is the substrate-reference freshness mechanism (live pulls, not denormalized JSON) the right call?

Argument FOR live pulls: substrate stays source of truth; grounding
verdicts can update; deletions propagate.

Argument AGAINST: makes notebooks fragile if substrate state drifts;
a deleted claim becomes a notebook with a broken reference.

**Operator decision needed before Wedge 2 ships.** Recommended posture:
live pulls, with a `tombstone` block type that renders gracefully when
a reference's target is gone. ("This claim was deleted on 2026-MM-DD;
prior text was…")

### 16.4 Should rrweb itself be vendored if Wedge 5 eventually wants DOM-level capture?

§9.4 says no — Antiek records typed events, not DOM. But if the
trajectory replay reveals demand for "show me what the operator was
hovering when they made this decision," DOM-level capture becomes a
real question. Defer until Wedge 5 ships and operator self-reports the
need.

### 16.5 Is TipTap the right block editor, or is something newer (Plate.js, Lexical) better in 2026?

TipTap is mature, ProseMirror-based, well-typed, the PostHog choice.
Plate.js is Slate-based, also mature. Lexical (Meta's) is newer with
better React performance.

**Recommended:** TipTap as default because PostHog's adoption is a
real-world data point (and Antiek's notebook block schema can borrow
their block-type definitions). Re-evaluate only if TipTap's bundle
size + TS strict compatibility fail Wedge 1-style criteria.

### 16.6 Does the public handbook become a public artifact eventually, or stay in `docs/`?

§11.4 says: stays in `docs/` until Antiek has a public audience. The
unresolved question is when "public audience" qualifies. Master-product-spec
multi-user pivot (Sprint 19+) is one threshold; first paid users is
another; some operators' personal blogs counterfactually serve as
handbook surrogates already. **Operator decides at the threshold;
no spec commitment here.**

---

## 17. What to do now

**One INTEGRATE NOW item.** Sprint 17 substrate-side hygiene:
**Storybook scaffold (Wedge 1a)**. Half a day. Pure-upside design-system
documentation. No risk. No precondition.

**Lemon UI evaluation (Wedge 1b)** as a parallel decision during Sprint 17:
spike, decide, document outcome. The decision either adopts or rejects;
either is a defensible answer.

**Everything else defers** with explicit unlock criteria (§14). The
notebook surface (Wedge 2) is the largest single value upgrade and
sequences naturally for Sprint 18 or 19 alongside the multi-user work.
The command palette + ubiquitous AI + trajectory replay (Wedges 3-5)
chain off the notebook. The pricing page + handbook patterns (Wedges 6-7)
unlock on separate triggers.

**Five explicit REJECTs** (§12.1-12.8) close the bait that the headline
"adopt PostHog patterns" implies. ClickHouse, plugin marketplace, voice/mascot
copying, HogQL-style query language, multi-tenant org surfaces, 25+
adapters by parity, multi-product nav before its time, rrweb DOM
capture. These are not deferred decisions; they are settled negative.

The wedges in §5-§11 are the integration. The rejections in §12 are the
guardrails. The unlock criteria in §14 are the ratchet. The verdict
on Wedge 2 (the linchpin) lands in Sprint 18-19.

---

## Final note for the implementing agent

Precedence order when this spec conflicts with another:

1. `architecture_notes.md` — substrate-level commitments (load-bearing;
   never violate)
2. `master-product-spec.md` — product vision + sprint sequencing
3. `strategy/voice-and-style-discipline.md` — quality bar for every
   operator-facing output (and now, per §13.1, for UI choices)
4. This spec — PostHog integration verdicts and wedge mechanics
5. Peer integration specs (`integration_prime_intellect.md`,
   `integration_autoresearch.md`, `daytona_integration_spec.md`,
   `rlm_integration_spec.md`) — conflicts resolved by operator review

If precedence (3) and any wedge ever conflict — i.e., adopting a PostHog
pattern hurts Antiek's voice or aesthetic — the discipline wins. The
PostHog patterns are the means; the researcher's-notebook product
proposition is the end. **Never substitute the end for the means.**

The substrate is the moat (master-product-spec §15.4); the UI is the
operator's interface to the moat. PostHog's patterns are the
best-in-class reference for that interface layer specifically. Borrow
ruthlessly where the patterns fit. Reject loudly where they don't.
Find out which is which through the wedge evaluations — don't presume.
