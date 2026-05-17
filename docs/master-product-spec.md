# Antiek — Master Product Spec

**Status**: execution-ready master spec consolidating the operator's product
  vision across four voice-memo dictations on 2026-05-17. Sprint-by-sprint
  sequence at the end. Each sprint is independently scoped; each builds on
  what the prior sprints made possible.
**Audience**: any agent (or human) picking up Antiek's product work cold.
  After reading this spec, you should know what Antiek is, why it exists,
  what's already built, what comes next, and which decisions are
  load-bearing vs. cosmetic.
**Predecessor docs**: `architecture_notes.md` (substrate-level commitments),
  `strategy/voice-and-style-discipline.md` (substrate prompt engineering),
  `sprints/sprint11-web-app-mvp.md` (first web-app sprint).
**Companion**: `infrastructure/SKILL.md` (production operations).

---

## Table of contents

1. [Product thesis](#1-product-thesis)
2. [Conceptual primitives](#2-conceptual-primitives)
3. [What's already built](#3-whats-already-built)
4. [The four surfaces](#4-the-four-surfaces)
5. [Voice and style — non-negotiable quality bar](#5-voice-and-style--non-negotiable-quality-bar)
6. [Primary source connection](#6-primary-source-connection)
7. [Continuous research mode](#7-continuous-research-mode)
8. [Multimodal acquisition](#8-multimodal-acquisition)
9. [IP attribution + ad economics](#9-ip-attribution--ad-economics)
10. [Creation surface — writing tool](#10-creation-surface--writing-tool)
11. [DeepBlu — interview-as-acquisition](#11-deepblu--interview-as-acquisition)
12. [Voice note ingestion](#12-voice-note-ingestion)
13. [Account model + network effects](#13-account-model--network-effects)
14. [Sprint sequence (11 → 18)](#14-sprint-sequence-11--18)
15. [Strategic open questions](#15-strategic-open-questions)
16. [What we explicitly do NOT do](#16-what-we-explicitly-do-not-do)

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

---

## 3. What's already built

This section is **status as of 2026-05-17** so any agent reading
this spec knows what doesn't need to be re-derived.

### 3.1 Substrate (1166 tests passing)

- **Event log**: typed Pydantic schema with 61 ActionTypes; canonical
  source `substrate/schemas/events.py`; append-only `.jsonl` storage.
- **Dispatch**: provider-agnostic routing via `substrate/dispatch/`.
  OpenRouter-backed in production (single key drives DeepSeek-Flash,
  DeepSeek-Pro, Claude Opus 4.7). Cost tracked per call, emitted as
  `dispatch.call` events. Fallback chain with `--workers 1` enforced.
- **Context pack**: layered prompt assembly with budget enforcement
  in `substrate/context_pack/assembler.py`. 3 truncation strategies.
- **Graph schema**: DuckDB with `documents`, `chunks`, `nodes`,
  `edges`, plus Sprint-10 additions for `syntheses`,
  `synthesis_substrate_manifest`, `outcomes`, `chunk_tier_overrides`.
- **9 roles**: decomposer, evidence_retriever, parameter_extractor,
  connector, synthesizer (the 5 orchestrate.py originals) +
  challenger, grounder, note_taker, user_agent.
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

- Web app for chat-first research (Sprint 11 — the immediate next
  build).
- Voice and style prompt discipline (Sprint 11 substrate-side work).
- Primary source PDF deep-link from a synthesis (Sprint 11).
- Multimodal acquisition (YouTube, podcasts, X, social).
- Continuous chase mode.
- IP attribution + ad economics.
- Creation surface (writing tool).
- DeepBlu interview surface.
- Multi-user accounts + cross-graph network effects.

These are the eight directions this spec covers.

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

### 9.10 What to do now

**Nothing.** Sprint 11 (MVP) ships first. Sprints 12-15 cover
multimodal acquisition + continuous mode + creation surface +
DeepBlu. The IP attribution layer is Sprint 16+ at earliest.

Documentation discipline: when Sprint 11 ships, the substrate
should ALREADY be emitting the chunk-level citation data that
Phase 1 attribution telemetry needs. Sprint 11 doesn't add anything
specifically for attribution; it just ensures the data exists and
is queryable when Phase 1 starts.

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

### 13.1 Current model (Sprints 11-15)

**Single-operator, single-graph.** The production VM hosts one
substrate, one DuckDB file, one event log. The operator is the only
user. No accounts, no auth, no isolation.

This is acceptable because:
- `app.antiek.ai` is publicly reachable but no one knows about it
- Only the operator's OpenRouter key gets burned by abuse (rate
  limit at the Caddy level if it becomes a real problem)
- The operator's research is the only content; nothing private
  is at risk

### 13.2 Future model (Sprint 19+)

The transition to multi-user introduces these requirements:

- Authentication (probably Clerk or Supabase Auth)
- Per-user knowledge graphs OR shared graph with per-user view
  filters
- Privacy model: documents marked public vs private; defaults to
  private
- IP attribution complications: if user A's private document
  contributes to user B's synthesis, what happens? (Probably: B
  can't cite A's document; B's synthesizer sees the chunks
  redacted)

### 13.3 Network-effects path

The operator's vision involves network effects across users'
knowledge graphs:

- User A interviews their colleague C; the transcript becomes a
  public document in A's graph
- User B is researching the same topic; B's investigations can
  cite C's transcript via cross-graph search
- The substrate's "ask an expert" flow surfaces user A as a
  potential interview subject for B (with A's opt-in)

This is the **Sprint 20+ vision**. It depends on:
- Multi-user accounts working
- Public/private model being well-defined
- IP attribution scaled enough that contributing publicly has
  economic upside
- DeepBlu interview surface mature enough to handle cross-user
  interview requests

### 13.4 What to do now

**Nothing structural.** Substrate stays single-user until Sprint 19+.

What CAN be done now: ensure the substrate's data model doesn't
make multi-user impossible later. Specifically:
- Every document, every chunk, every node, every investigation
  should already carry the data needed for per-user filtering
  even if no filter is applied (e.g., `documents.owner_user_id`
  defaulting to a single hard-coded value). When multi-user
  lands, the substrate schema doesn't need migration; only the
  application layer changes.

This is **cheap to do now**, expensive to do later. Add as a
one-day Sprint-11 substrate-side task.

---

## 14. Sprint sequence (11 → 18)

This is the road from "MVP shipped" through "creation surface live"
through "IP attribution telemetry running."

| Sprint | Theme | Substrate work | UI work | Strategic risk |
|---|---|---|---|---|
| **11** | Research workstation MVP | 3 new endpoints + voice/style discipline + multi-user schema prep | Full Mode A (chat → trajectory → MASTER.md viewer → highlight-to-chase) | Low — substrate is solid, UI is thin renderer |
| **12** | Multimodal + continuous mode | YouTube + podcast adapters; continuous-mode orchestrator parameter | Sources tab in workstation; chase-mode selector in chat input | Medium — cost runaway risk in continuous mode |
| **13** | Voice notes + creation v0 | Voice acquisition adapter; creative_writer role; deliverables data model | Mode C (creation) v0: section-based, no drag-drop yet | Low |
| **14** | Creation drag-drop + X ingestion | Multi-section coherence in creative_writer; browser extension for X | Mode C drag-drop UI + block palette; X extension popup | Medium — browser extension friction |
| **15** | Edit-back-into-graph + export | New event type for operator-asserted claims; deliverable export to PDF/EPUB/Substack draft | Mode C editor with provenance preservation; export dialog | Low |
| **16** | IP attribution telemetry + interviews | `page_attribution_computed` events; 3 attribution algorithms; interview state machine + AI interviewer role | Interview project dashboard; informant UI at `interview.antiek.ai` | High — attribution math is novel; interview voice loop is unfamiliar territory |
| **17** | Interview voice mode | WebRTC capture; TTS dispatch tier; streaming whisper transcription | Voice interface in interview surface | Medium — voice loop latency / quality calibration |
| **18** | Publisher dashboard + Synquery | `ip_holders` table + `publisher.antiek.ai`; Stripe Connect onboarding; Synquery API client | Publisher dashboard surface | High — KYC + compliance + Synquery partnership all simultaneously |

Each sprint ~5-10 working days. Total: ~10-12 weeks of focused work
for the Sprint 11-18 arc.

### Out beyond Sprint 18

- **Sprint 19-22**: payouts + multi-user accounts + Phase 4 ad inventory.
  Quarter-long initiative.
- **Sprint 23+**: scale. Programmatic ad auction, vision-capable role
  for video/image content, federation / network effects, RL training
  loops (the Loop 3 vision that's been deferred since Sprint 0).

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

---

## Final note for the implementing agent

This spec is the master reference. When you encounter ambiguity
during implementation, the precedence order is:

1. `architecture_notes.md` — substrate-level commitments
   (load-bearing; never violate)
2. This spec (`master-product-spec.md`) — product vision +
   sprint sequencing
3. The sprint-specific spec (`sprints/sprintN-*.md`) — execution
   detail for the active sprint
4. The voice and style discipline (`strategy/voice-and-style-discipline.md`) —
   quality bar for every operator-facing output

If precedence (1) and (2) conflict, escalate to the operator
before resolving. The substrate's commitments are non-negotiable;
product vision can be re-shaped.

Sprint 11 (`sprints/sprint11-web-app-mvp.md`) is the immediate
work. Begin there.
