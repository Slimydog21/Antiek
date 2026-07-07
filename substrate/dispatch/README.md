# substrate/dispatch/

Multi-model LLM router with provider abstraction.

## Interface

```python
dispatch(prompt, role, max_tokens, verification_required, context_pack) -> response
```

Routes by role using the configuration in `config.yaml`. Routing
changes never require code changes.

## Configured backends

Claude-less (operator decision 2026-07-06): every tier's primary is
GLM-5.2 via Zhipu z.ai DIRECT API, with a three-deep cross-family
fallback GLM-5.2 → DeepSeek V4 Pro → MiMo V2.5 Pro, all direct
endpoints (no OpenRouter hop, no Anthropic).

- GLM-5.2 via z.ai, thinking OFF — flash + pro + verify tiers
- GLM-5.2 via z.ai, thinking ON — synthesis tier (reasoning opt-in)
- DeepSeek V4 Pro via api.deepseek.com — cross-family backup layer
- MiMo V2.5 Pro via api.mimo.xiaomi.com — second cross-family backup
- OpenAI whisper-1 / gpt-4o-mini-tts — transcription + TTS (voice I/O)
- Local inference (deferred; abstraction in place for later)

`hermes` (the operator's local subscription gateway) registers as an
opt-in provider when `HERMES_API_KEY` is set but is in no tier route —
a dormant gateway, not an active path. `config.yaml` is authoritative.

## Tracked metrics

Per-role token consumption, per-investigation cost, latency by phase.
These feed the hardware-decision criteria — see architecture_notes §6.

## The flash/pro split (thinking policy, not model variants)

All four tiers run the same GLM-5.2; the split is whether it reasons.
flash/pro/verify run thinking OFF for volume (crystallized answers at
throughput); synthesis runs thinking ON for the human-facing artifact.
Reasoning stays opt-in per role. See architecture_notes §2.5.
