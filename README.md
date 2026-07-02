# Antiek

**The workstation where reading compounds.**

Reading-for-understanding has a different cognitive shape than
reading-for-pleasure. LLMs make it possible to compress hundreds of
sources at speed — but almost every tool that does so throws away the
one thing that makes research trustworthy: per-source provenance.
Antiek is the workstation that refuses that trade. Cursor for knowledge
work, built on a substrate where every claim can show its receipts.

This is not a demo repo. The platform is built, tested (6,000+ test
functions), and running in production at [antiek.ai](https://antiek.ai)
with its API at `api.antiek.ai`. What remains open is deliberate — see
[What we deliberately have NOT built](#what-we-deliberately-have-not-built).

---

## The thesis

Most "AI research tools" are a chat box with a search API stapled on.
They produce em-dash–laden bulletized slop that you skim rather than
absorb, they cite nothing you can verify, and they forget everything
between sessions. We think that's three separate failures, and Antiek
is an existence proof that all three are choices, not laws of nature.

**1. Recursive note-taking is the engine, not a feature.** Every
document the substrate touches — paper, textbook chapter, YouTube
transcript, podcast, interview, voice note — is distilled into exactly
two buckets: **insights** (verified takeaways with chunk-level
citations, confidence, and a source tier) and **open questions** (gaps
the document raised but didn't answer). Open questions don't sit there
looking decorative. They become triggers for new research chains. The
graph grows compoundingly across investigations. Read one thing, and
the system knows ten things it should read next.

**2. Voice and style discipline is a quality gate, not a vibe.**
Antiek's prose has to feel like a researcher's notebook entry —
absorbing the source corpus's vocabulary and argumentation, claims
cited inline, no forced bullets, no slop. This is enforced in code
(master spec §5), it applies to the UI as much as the prose, and the
product fails without it. We treat a slop regression the way other
teams treat a failing build.

**3. The substrate is the moat, not the UI.** The typed event log, the
knowledge graph, the multi-model dispatch with cross-family
verification, the skill-patching loop — that's what compounds. The
analogy to Cursor holds at the inference layer (route to external
providers, charge for workflow value, don't train foundation models)
and breaks, on purpose, at the substrate layer: an IDE plugin is
replaceable in a quarter; an accumulated, provenance-complete personal
knowledge graph is not.

---

## What's actually built

We keep the status honest because a README that oversells is a bug.
Every row below is verifiable on `main`, not aspirational.

**The substrate.** Typed event capture (Pydantic v2 schemas,
`substrate/schemas/events.py` is canonical), a DuckDB-backed knowledge
graph with a strictly serialized single writer (`runtime/db_lock.py`),
multi-model LLM dispatch with cross-family verification, source
attribution down to the chunk, context packs, and a Skills layer that
captures domain expertise as versioned, first-class artifacts. Every
claim cites chunks; every chunk cites documents; every document carries
an `ip_holder_id` (even when null). The provenance chain is unbroken by
construction.

**The roles.** Decomposer, evidence retriever, parameter extractor,
connector, synthesizer — verifier-shaped, orchestrated by a phase
state-machine in code rather than a prose protocol, with append-only
phase logs and audit trails.

**The reading platform** (`apps/reading/`, React + strict TypeScript).
The full Research / Read / Write / Speak roadmap is on `main` — not
scaffolding, shipped modules: the reading geometry pass and layout map,
the notebook block-canvas with auto-notebook, the float menu, the
research home with plan mode, the library feed and in-book reader,
talk-to-book with shared ASR-in/TTS-out voice infrastructure, the Write
X-ray, biography templates, a personal doc space with
auto-categorization, and one penguin mascot we're rather fond of.

**The paranoia, as code.** This is where the craft lives:

- **Resilience:** a fault-injection harness, circuit breakers,
  timeout/bulkhead lint rules, chaos and steady-state suites, and a CI
  floor that keeps them honest.
- **An agent-failure regression library:** every observed production
  agent failure gets a YAML fixture in
  `tests/regression/agent_failures/` *before* the fix lands, and the
  fixture must fail until the mitigation ships. We don't fix bugs; we
  make bugs impossible to reintroduce quietly.
- **A locked craft signature:** the inline synthesis-rubric scorer's
  p95 latency is baselined (194.85 μs) and CI fails on a >10%
  regression (`python -m benchmarks.rubric_latency --check-regression`).
  Every *other* perf dimension is explicitly declared "good enough" in
  `docs/craft_signature.md` — one number defended ruthlessly beats
  twenty numbers watched vaguely.
- **Scoped strictness:** `mypy --strict` on the modules that must be
  bulletproof (event log, lock primitives) without letting strict-mode
  adoption theater block the rest of the tree.

**Production.** FastAPI substrate behind a Cloudflare Tunnel on
Hetzner, frontend on Cloudflare Pages auto-building from `main`,
magic-link auth, and a continuous-research daemon that chases
evidentiary gaps while nobody's watching. Ops runbooks live in
`infrastructure/`.

---

## Layout

```
substrate/      Typed events, graph, dispatch, schemas, attribution, context packs
skills/         Domain / process / verification / interview skills (versioned, first-class)
acquisition/    Source-specific ingestion (arxiv, books, urls, youtube, rss, interview, …)
processing/     Chunking, embedding, extraction, note-taking, distillation
roles/          Decomposer, evidence retriever, parameter extractor, connector, synthesizer
middleware/     Constraint checks, source tiering, temporal, archive, backtest
orchestration/  Phase runner as a state machine, phase log, heartbeat, audit
interfaces/     Research / interview / reading / creation surfaces
compounding/    Skill growth + verification — the property that makes the system compound
apps/reading/   The reading platform (React, strict TS, Storybook, Playwright, Lost Pixel)
runtime/        db_lock, remote_exec, monitoring, deployment
benchmarks/     Locked performance baselines (see docs/craft_signature.md)
tests/          6,000+ test functions: unit, integration, e2e, chaos, regression fixtures
docs/           The contract (master spec) + the status reports (companion docs)
```

---

## The invariants we refuse to break

A short list, defended hard. Each exists because the failure it
prevents is expensive and quiet.

1. **DuckDB single-writer.** One serialized writer through
   `runtime/db_lock.py`, `--workers 1` on uvicorn, period. Concurrent
   writers corrupt the one asset that compounds.
2. **The provenance chain.** Claim → chunk → document → IP holder.
   Anything that breaks this chain breaks both the trust story and the
   future economics layer in one move.
3. **Voice/style discipline** (spec §5). Applies to generated prose
   and to UI choices. Non-negotiable.
4. **The legal gate on monetization** (spec §9.0). No payout mechanics
   go live before retrieval-time IP gating is proven in production and
   publishers have opted in. The Bartz precedent prices getting this
   wrong at $3,000 per ingested work; we choose not to find out.
5. **Single-operator until compounding is demonstrated.** Premature
   multi-user destroys the moat before it exists. The pivot is gated,
   not vibes-based.
6. **The §16 REJECT list.** The spec maintains an explicit list of
   things we will *not* build or adopt, with reasons. Saying no in
   writing is cheaper than un-building.

---

## What we deliberately have NOT built

Engineering scope on the spec is essentially complete. The open items
are **operator-bound gates** (legal review, publisher opt-in, real ads
and Stripe activation, the multi-user pivot) and **explicit
deferrals** — each documented with what unlocks it:

- `docs/operator_gate_actions.md` — the binding gates, each with
  Status / Owner / Blocks-what / Action-needed.
- `docs/engineering_deferrals.md` — the "don't re-implement this;
  here's when it unlocks" list.
- `docs/decisions/` — one markdown file per closed gate or binding
  decision, so nothing gets relitigated by accident.

The ads/attribution layer (§9) — per-frame attention attribution that
pays the drivers of content value — exists as ratified design and
substrate hooks, gated behind §9.0. It is the strategically
consequential layer and precisely why the provenance invariant is
non-negotiable today.

---

## Running it

```bash
# Substrate tests
./.venv/bin/python -m pytest tests/ -q

# Frontend typecheck (strict)
cd apps/reading && npx tsc -b

# Strict-mode floor on core modules
mypy --strict substrate/event_log runtime/db_lock.py

# Craft-signature regression check
python -m benchmarks.rubric_latency --check-regression
```

Python 3.11+, DuckDB, Pydantic v2, FastAPI. LLM calls go through the
dispatch router — never directly.

---

## Where to read next

| If you want… | Read |
|---|---|
| The contract — what Antiek is and why | `docs/master-product-spec.md` |
| Current execution truth | `docs/operator_gate_actions.md`, then `docs/engineering_deferrals.md` |
| Agent onboarding + hard invariants | `CLAUDE.md` |
| Why the substrate looks like this | `docs/architecture_notes.md` |
| The one perf number we defend | `docs/craft_signature.md` |
| Everything we said no to | Master spec §16 |

The split between spec and status docs is deliberate: the master spec
is the contract, the companion docs are the status report. Updating
the spec on every shipped PR would couple implementation to
spec-editing — friction we chose not to pay.

---

Built by one operator and a fleet of agents held to a five-values bar:
intellectual honesty, fairness, rigor, diligence, defensibility. If a
claim in this README ever drifts from what `main` can prove, that's a
bug — file it like one.
