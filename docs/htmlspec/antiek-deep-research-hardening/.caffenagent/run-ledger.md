# Run ledger — Antiek Deep Research Hardening (ADRH)

Spec: `~/specs/antiek-deep-research-hardening/` (master + sprint-01..08 HTML)
Repo: `~/Desktop/Antiek` · branch `adrh/spr01-provider-contract` (forked from `main` @ `1c4d5df9`)
Orchestrator: main conversation (co-CEO, holds five-values bar)
Builder: single Claude subagent inline (spec hint: one owning package, serial milestones, fan-out unit = None for build)
Critic: `grok` headless (Composer 2.5-fast) — independent verifier lenses, read-only

## Ground truth (verified 2026-06-26)

- `canonical_verify.sh deep-research` → **CANONICAL_VERIFY_OK** (P-11..P-17, 22 tests). In-scope DRL loop shipped.
- `canonical_verify.sh html-transport` → **CANONICAL_VERIFY_OK** (P-18, 18 tests). HTML transport shipped.
- `tests/research/` does NOT exist. 0/13 named ADRH test files present. No `ResearchProvider`/Exa/Parallel adapters in live tree. → **ADRH genuinely unexecuted.**
- `substrate/contracts/reading_surface.py` is PROVISIONAL ("DRW SPR-10 not yet implemented"). → reading-side goal #2 gap.
- Baseline runner tests: **28 passed** (`tests/test_research_runner.py` + drw lock + parent terminal).

## Operator constraints honored

- Operator deferred Exa/Parallel live calls (recorded in DRL ledger, 2026-06-12). ADRH adapters land as conformance-tested stubs/fixtures; no live API keys, no `live`-marked tests run. Provider code is interface + fixture shape only.
- Harness guardrail: `grok` with `--permission-mode bypassPermissions --always-approve` is DENIED by the auto-classifier. Workhorse used read-only (critic) — construction is a Claude subagent inline.

## Sprint progress

### SPR-01 — ResearchProvider interface & normalized contract (Wave 1)

| Milestone | Deliverable | Proof | Status |
|---|---|---|---|
| M1 | Locate runner + Exa client; document seam | below | done |
| M2 | Normalized result type | research/providers/types.py | done |
| M3 | ResearchProvider interface | research/providers/base.py | done |
| M4 | Conformance harness (+ negative) | tests/research/test_conformance.py | done |
| M5 | One-owner CI lint | tests/research/test_one_owner_lint.py | done |
| M6 | Stub + runner-seam test | tests/research/test_runner_seam.py | done |
| Critic | 4-lens adversarial pass (leak/rubber-stamp/smuggled-precision/grok-ceo) | below | in_progress |
| Gates | 4 verify gates + handoff packet | this file + commit | pending |

Critic rounds: floor=1 cap=4. Lenses: leak / rubber-stamp / smuggled-precision / grok-co-CEO.

## SPR-02 M1 — trajectory/measurement schema seam (verified 2026-06-26 19:08)

**Schema version anchor:** `EVENT_SCHEMA_VERSION = 27` at `substrate/schemas/events.py:711` (spec guessed v13; reality v27 — bumped many times). SPR-02 bumps to **v28** (additive).
**Event record:** `substrate/event_log/events.py` — `{event_id, investigation_id, synthesis_id, phase, role, action_type, payload, parent_event_id, policy_id, param_version, schema_version, emitted_at, document_id}`. `ActionType` = `str, Enum` (~60 members: `phase.enter`, `role.call.start/end/failed`, `decompose.*`, `evidence.retrieve.*`, `graph.node.inserted`, etc.). `payload` = opaque JSON (action-type-specific) → new measurement payload is additive/backward-compat.
**Storage:** append-only JSONL per investigation at `{ANTIEK_RESEARCH_EVENTS_DIR}/{investigation_id}.jsonl` → sealed to Parquet. `~/.antiek/research_events/`. `ANTIEK_EVENTS_DISABLED` toggle.
**SPR-02 scope (5 milestones):** M2 measurement record `{schema_version, investigation_id, sub_question_id, task_class, provider, tier, cost_usd(observed), latency_ms(observed), confidence, outcome, correlation_id}` in `research/measurement/schema.py`; M3 task-class enum (`structured_extract`/`broad_gather`/`needle_in_haystack`/`multi_hop`/`unclassified`) DRAFT; M4 validated writer + fwd/back-compat reader `research/measurement/log.py`; M5 reconstruction query. `research/measurement/` does not exist yet (clean target).

## SPR-02 build progress (workflow wf_b9c3bfa1-8ec, branch adrh/spr02-measurement-schema)

Builder round 1 (still finalizing at 19:52): all 5 files on disk — `research/measurement/{schema,task_class,log,reconstruct,__init__}.py`. `EVENT_SCHEMA_VERSION` bumped v27→v28 (additive, comment at `substrate/schemas/events.py:726`); new ActionType `RESEARCH_PROVIDER_MEASURED = "research.provider.measured"` (`:495`). Builder reports 67 research + 28 regression green. Orchestrator-verified: 95 passed in scope (48 measurement + 19 SPR-01 + 28 regression). 2 pre-existing collection errors (`test_substrate_cli_unified.py` → missing `substrate.harness.fork`; `test_substrate_end_to_end.py` → missing `substrate.conversation.compaction`) are STALE tests from unrelated prior work (pi-execution/unified-main), NOT a v28 regression — modules don't exist in tree, SPR-02 didn't touch them.
Awaiting builder BUILD_SCHEMA return → 4-lens verify panel (schema-leak-compat / writer-rejects / reconstruction / determinism-atomicity) → sharpen if blocking.

## Critic verdicts (workflow wf_37eaa7e8-662, 2026-06-26)

- **leak:** CLEAN on the leak test (ResearchResult embeds NO provider-specific structure: fields=dict[str,str|None], field_citations=dict[str,list[Source]], confidence=float, cost=float, latency=int, provider=str (label), tier=str, raw_ref=opaque RawRef). 1 MINOR doc defect — types.py didn't restate INV-1/INV-4 verbatim. **FIXED by orchestrator** (added verbatim Invariants block to types.py, mirroring base.py). Re-verify: 19 research tests green.
- **smuggled-precision:** CLEAN. Confidence mapping written in types.py docstring + flagged "UNVERIFIED ASSUMPTION" (anchors called "engineering guesses, not measured equivalents") + conformance harness range-checks [0,1].
- **rubber-stamp:** CLEAN. Positive (good stub) passes; negative (broken stub) genuinely fails-and-names-invariant (no xfail/skip hiding it). Agent adversarially attempted to neuter the negative to prove it fires — confirmed repo stayed clean.
- **grok-co-CEO (Composer 2.5):** BLOCKED on infra — harness Bash classifier "temporarily unavailable" repeatedly, blocking the `grok --single` shell-out (both the subagent and orchestrator). To retry when classifier recovers. Not a code defect.

## Gates (verified on disk by orchestrator, 2026-06-26 18:26)

- `.venv/bin/python -m pytest tests/research/` → **19 passed** (conformance positive+negative, one-owner lint, runner seam).
- `.venv/bin/python -m pytest tests/test_research_runner.py tests/test_contracts_drw_lock.py tests/test_drw_parent_terminal.py` → **28 passed** (regression holds; baseline preserved).
- Total: **47 passed**. Builder also fixed 2 real bugs in a prior partial attempt (cost("inv-seam") passing str not Handle; SDK-import test tripping on allowlisted pre-existing exa import) + removed a fictional "proven to fire" lint comment.

## Outstanding before SPR-01 close
- ~~Retry grok co-CEO review~~ → **SPR-01 COMMITTED** on branch `adrh/spr01-provider-contract` (commit: feat(ADRH SPR-01): ResearchProvider interface + normalized contract, 9 files +778). Handoff at `SPR-01-handoff.md`. 47 tests green. 3/4 lenses CLEAN; grok-co-CEO pending classifier recovery (source-free sketch approach ready).
- **Latent defect found & fixed during commit:** `/research/` top-level dir is gitignored (operator's local-artifacts scratch). Prior half-committed attempt had tests + runner seam tracked but `research/providers/` SOURCE gitignored — untracked. Fixed via `.gitignore` negation (`/research/*` + `!/research/providers/` + `!/research/__init__.py`). Source now tracked for the first time.
- grok co-CEO review remains queued for when the harness Bash classifier recovers (persistent "glm-5.2 temporarily unavailable" outage on substantial commands). Use the SOURCE-FREE prose sketch (no file contents cross the trust boundary) per the data-exfiltration guardrail.

## M1 seam findings (verified path:line, 2026-06-26)

**Runner (SOLE OWNER, host-local):** `runtime/research_runner/host_local.py`
- Calls Exa directly via lazy import at `:564`: `from acquisition.search.exa import discover, promote_discovery` inside `make_exa_gather_loop` (`:525`). This is the **INV-1/INV-4 violation hardening fixes** — the runner reaches into a concrete provider and branches on `gather_mode="exa"`.
- Protocol at `runtime/research_runner/protocol.py` (205 lines); re-exported at `substrate/contracts/research_runner.py`. Unit of work = `investigation_id`; runner owns start/stream/steer/status/cost/cancel; step logic injected as `BrowseLoop`.
- Demo stub loop `:447`; contract-gather stub `:480`; exa gather loop `:521` (env-gated `ANTIEK_DRW_GATHER=exa`).

**Existing Exa client (reuse, don't duplicate):** `acquisition/search/exa/`
- `client.py` — typed `ExaClient` (httpx, `MockTransport` for tests, retry 429/5xx ×3, `EXA_API_KEY`, `EXA_BASE_URL`). Returns typed records only; emits no events, touches no graph.
- `adapter.py:73` `DiscoveryProposed` (frozen dataclass), `:108` `DiscoveryPromotionResult`, `:123` `DiscoveryBudgetExceeded`. `discover(...)` at `:187` returns `list[DiscoveryProposed]`.
- `budget.py` — daily spend cap `check_and_reserve`. `cache.py`, `lookup.py`.
- **Current pre-hardening return shape = DISPOSAL, not ANSWER:** `discover` yields `DiscoveryProposed` (URL + decision accept/reject/redirect) for promotion into the graph. It does NOT return structured fields + per-field citations + confidence answering a sub-question. The normalized `ResearchResult` type is the deliberate improvement: provider contract shifts from "here are sources" → "here is a grounded answer."

**Existing provider abstraction?** None for research. `substrate/dispatch/base.py` is LLM dispatch (different concern). → New `research/providers/` package is justified (reuse-before-invent passes).
