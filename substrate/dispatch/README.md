# substrate/dispatch/

Multi-model LLM router with provider abstraction.

## Interface

```python
dispatch(prompt, role, max_tokens, verification_required, context_pack) -> response
```

Routes by role using the configuration in `config.yaml`. Routing
changes never require code changes.

## Configured backends

- DeepSeek V4 Pro / Xiaomi MiMo V2.5 Pro (primary work, reasoning-heavy)
- DeepSeek V4 Flash / Xiaomi MiMo V2.5 Flash (bulk, cost-optimized)
- **Engagement:** `latency_mode=interactive|autonomous` + `engagement_policy` in
  `config.yaml` — interactive driving roles → TileRT tier `speed`; autonomous →
  `research_*` tiers. See `engagement_mode.py` and `docs/decisions/tilert-antiek-placement.md`.
- **Brain toggle:** `brain_choice=glm|premium` on investigation start (default
  **glm** = GLM-5.2/TileRT when engaged; **premium** = Opus/pro). Use
  `dispatch_routing_kwargs(investigation_id)` at call sites. See `brain_choice.py`.
  **Precedence:** explicit `brain=` on `dispatch()` → investigation start event →
  `ANTIEK_BRAIN_CHOICE` env → default `glm`. Chase children inherit start fields
  (`orchestration/loop_one/orchestrator.py`).
- Claude via API (high-stakes synthesis)
- Grok 4.3 via Hermes (cross-family verification)
- Prime Inference (additional capacity)
- **TileRT GLM-5** on Modal (`tilert` provider, `speed` tier) — latency-first; see `infrastructure/modal/tilert_glm5/` and `docs/decisions/tilert-modal-glm5.md`
- Local inference (deferred; abstraction in place for later)

## Presence (engaged vs background)

API role handlers assume **engaged** (`latency_mode=interactive`) via
``dispatch_routing_kwargs(investigation_id)``.

**Background** (`presence="background"` → autonomous / ``research_*`` tiers):

| Entry | Path | Notes |
|-------|------|-------|
| Corpus bridge extract | ``substrate/research_bridge/llm_dispatch.py`` | Default ``presence="background"`` |
| Maintainer / cron | (inventory) | Wire ``presence="background"`` when adding dispatch |

Gateway-wide escape hatch: ``ANTIEK_LATENCY_MODE=interactive|autonomous``.

Per-investigation **deliverable_speed_preference** (start payload) can put
driving roles on ``speed`` while otherwise autonomous.

## Tracked metrics

Per-role token consumption, per-investigation cost, latency by phase.
These feed the hardware-decision criteria — see architecture_notes §6.

## The Pro/Flash split

Not interchangeable cost tiers. Flash variants for bulk processing
where volume is the binding constraint; Pro variants for synthesis
where reasoning depth and multi-hop coherence dominate. See
architecture_notes §2.5.
