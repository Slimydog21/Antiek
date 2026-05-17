# Antiek

A research substrate that consolidates two prior projects — **Researchmaxx**
(research-agent infrastructure under Hermes) and **DeepBlu** (AI interview
infrastructure for biography-as-a-service) — onto a shared core.

The substrate handles typed event capture, knowledge-graph operations,
multi-model LLM dispatch with cross-family verification, source attribution,
and a Skills layer that captures domain expertise as first-class compounding
artifacts. Two surface applications sit on top of it: a research workflow
and an interview workflow. A third surface (consumption-side reading and
creation) is scaffolded but deferred.

## Status

This is the scaffolding pass. The folder structure exists, each module has
a README describing its purpose and scope, and the design rationale lives
in `docs/architecture_notes.md`. No business logic ships yet — see that
document and the per-module READMEs for what each piece will hold.

## Layout

```
substrate/      Typed events, graph, dispatch, schemas, attribution, context packs
skills/         Domain / process / verification / interview skills (versioned, first-class)
acquisition/    Source-specific ingestion (arxiv, books, urls, x, gmail, youtube, rss, interview)
processing/     Shared chunking, embedding, extraction, note-taking, distillation
roles/          Decomposer, evidence retriever, parameter extractor, connector, synthesizer, user agent
middleware/     Constraint checks, source tier, temporal, archive, backtest
orchestration/  Phase runner, phase log, kanban bridge, heartbeat, audit
interfaces/     Research / interview / reading / creation surfaces
compounding/    Skill growth + verification (the property that makes the system compound)
runtime/        Docker, monitoring, logging, deployment
docs/           Architecture notes, design rationale, audit findings
tests/          Unit, integration, fixtures
```

## Stack

Python 3.11+, DuckDB, Pydantic v2 for schemas, FastAPI for HTTP surfaces.
LLM calls go through the dispatch router; no model training in this build.

## Build order (from the spec)

1. Substrate consolidation (event log, dispatch, schemas, context pack, constants).
2. Researchmaxx migration (move prior scripts, consolidate duplicate role implementations).
3. Phase orchestration as code (replace prose-driven 9-phase protocol with a state machine).
4. Skills layer (process and verification categories alongside domain).
5. DuckDB write coordination (lock or queue).
6. Interview workflow integration (DeepBlu lineage).
7. Compounding-skill verification (diff and quality metrics).

Total estimated effort: 16–21 weeks. See `docs/architecture_notes.md` for
the reasoning behind each non-negotiable.
