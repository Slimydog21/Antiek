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
- Claude via API (high-stakes synthesis)
- Grok 4.3 via Hermes (cross-family verification)
- Prime Inference (additional capacity)
- Local inference (deferred; abstraction in place for later)

## Tracked metrics

Per-role token consumption, per-investigation cost, latency by phase.
These feed the hardware-decision criteria — see architecture_notes §6.

## The Pro/Flash split

Not interchangeable cost tiers. Flash variants for bulk processing
where volume is the binding constraint; Pro variants for synthesis
where reasoning depth and multi-hop coherence dominate. See
architecture_notes §2.5.
