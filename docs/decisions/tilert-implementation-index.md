# TileRT · Speed Brain — implementation index (ATSB)

**Status:** Substrate shipped on branch `caffen/duckdb-plane` (commits from `029be0a`).
**Live TileRT:** blocked on operator **OA-022** until `./scripts/tilert_modal_preflight.sh` exits 0.

## Routing (single entry)

| Concern | Location |
|---------|----------|
| `dispatch()` | `substrate/dispatch/router.py` |
| Brain `glm\|premium\|ceo` (reserved) | `substrate/dispatch/brain_choice.py` |
| `interactive` vs `autonomous` | `substrate/dispatch/engagement_mode.py` |
| Investigation kwargs | `substrate/dispatch/session_routing.py` → `dispatch_routing_kwargs()` |
| Tier `speed` → provider `tilert` | `substrate/dispatch/config.yaml` (`engagement_policy`, `speed` tier) |
| HTTP provider registration | `substrate/dispatch/providers/bootstrap.py` (`ANTIEK_TILERT_*`) |
| Research lane hints (not a router) | `substrate/dispatch/orchestration/notdiamond.py` |
| Event `tier` stamps | `substrate/schemas/events.py` |
| Mechanical routing audit | `tests/test_dispatch_routing_audit.py` |

## Product surfaces → code

| Surface | Wired in | TileRT role |
|---------|----------|-------------|
| Deep Research (API roles) | `interfaces/research/api/*` + `roles/*` + `orchestration/loop_one` | Driving roles: `dispatch_routing_kwargs` |
| Read (RLM) | `substrate/graph/rlm_tools.py` | Root serial reasoning |
| Write | `substrate/write/draft_generation.py` | Engaged synthesis path |
| Speak | `interfaces/research/api/read_voice.py` | LLM between turns (not ASR/TTS) |
| Research bridge (background) | `substrate/research_bridge/llm_dispatch.py` | Default `presence=background` |
| Start UX | `apps/reading/.../StartResearch.tsx`, `useStartInvestigation.ts` | Brain toggle + deliverable speed pref |

## Modal / ops (SPR-01)

| Step | Artifact |
|------|----------|
| Weights | `infrastructure/modal/tilert_glm5/prep_weights.py` |
| Serve | `infrastructure/modal/tilert_glm5/app.py`, `openai_shim.py` |
| Preflight | `scripts/tilert_modal_preflight.sh` |
| Smoke | `scripts/smoke_tilert_modal.sh`, `scripts/smoke_dispatch.py` |
| Codex (personal) | `infrastructure/modal/tilert_glm5/CODEX.md` |

## Measurement (SPR-07)

`scripts/tilert_speed_verdict_report.py` → ADR `tilert-glm5-verdict-2026-06-23.md` (fill after prod traffic).

## Philosophy (defensibility)

- **Two clocks:** engaged → TPOT (`speed`); off-product → throughput (`research_*`).
- **No** `import tilert` in Antiek product code; OpenAI-compat HTTP only.
- **Falsifier:** interactive GLM synthesizer verifier −5pp vs premium → drop synthesizer `interactive`→`speed` override only.

Strategic placement: `tilert-antiek-placement.md`. Future CEO + NotDiamond: `notdiamond-fable-ceo-stack.md`.