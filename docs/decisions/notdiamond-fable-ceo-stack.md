# NotDiamond orchestration + Fable/Mythos CEO (future)

**Status:** Architecture stub (2026-06-23)  
**Implemented today:** `engagement_mode.py`, `brain_choice.py` (user toggle **glm** / **premium**), `session_routing.py`, `engagement_policy` in `config.yaml`, `orchestration/notdiamond.py` heuristic plan
**Not implemented:** Live NotDiamond API, Fable/Mythos provider, tier `ceo` backend

## Stack (operator intent)

| Layer | Model / engine | When |
|-------|----------------|------|
| CEO / brain | Fable or Mythos | Future — tier `ceo` (null provider until ship) |
| Driving (in-product) | GLM-5.2 via TileRT (`speed` / `tilert`) | `latency_mode=interactive` |
| Deep researchers (off-product) | DeepSeek, Xiaomi MiMo, Kimi | `latency_mode=autonomous` + `research_*` tiers |
| Orchestrator | NotDiamond | Picks lane per task; must not fork `dispatch()` |

## Contract discipline

- One router: `substrate/dispatch/router.py::dispatch`.
- Orchestrator outputs **hints** (`OrchestrationPlan`: `latency_mode`, lane notes) → caller passes `latency_mode` and optional `provider_override`.
- TileRT stays HTTP-only; no `import tilert` in substrate.

## Kill switch (today)

Set ``ANTIEK_NOTDIAMOND_DISABLED=1`` to skip heuristic / future NotDiamond
routing hints. Loop 1 still routes via ``dispatch_routing_kwargs`` and
``engagement_policy`` only.

## Wiring checklist (when NotDiamond ships)

1. Replace `plan_research_lane()` body with NotDiamond route call + caching policy.
2. Register Fable/Mythos adapter; set `ceo.provider` / `ceo.model` in config.
3. Emit decision events on orchestrator choice (investigation_id scoped).
4. A/B: CEO delegates to researchers vs monolithic GLM — measure cost per accepted deliverable.

## Falsifiers

- NotDiamond latency adds more than interactive TPOT savings → keep static `engagement_policy` only.
- CEO tier does not improve delegation quality vs GLM-5.2 driver → defer Fable/Mythos.