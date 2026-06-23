# Decision: TileRT GLM-5 on Modal as Antiek `tilert` provider

**Date:** 2026-06-23  
**Status:** Accepted (scaffold + dispatch wiring; weights/deploy operator-gated)

## Context

- Modal Auto Endpoints do not offer GLM-5.2; weights on HF (`zai-org/GLM-5.2-FP8`). Operator wants **TileRT** latency for speed-sensitive work and long-term Antiek use. Placement: `tilert-antiek-placement.md`.
- Antiek dispatch already normalizes on **OpenAI Chat Completions** via `OpenAICompatProvider`.

## Decision

1. Host **TileRT `glm5`** on Modal `B200:8` in app `antiek-tilert-glm5` (`infrastructure/modal/tilert_glm5/`).
2. Expose **POST /v1/chat/completions** + Bearer auth (same secret name pattern as other Modal apps).
3. Register provider **`tilert`** in bootstrap when `ANTIEK_TILERT_API_KEY` is set.
4. Add config tier **`speed`** → `tilert` / `glm5`, fallback `xiaomi` / `mimo-v2.5-pro`.

## Consequences

- **Cost:** 8× B200 is expensive; `min_containers` defaults to 0; operator opts into warm pools.
- **Weights:** One-time Volume conversion job; GLM-5.2 HF release = re-run prep, not router rewrite.
- **Not in default role_tiers:** Roles keep Hermes/OpenRouter paths until operator maps hot roles to `speed`.
- **Codex:** Same HTTP surface; personal wiring via mimo2codex generic provider.

## Alternatives rejected

- **Auto Endpoints GLM-4.7 only:** Does not meet GLM-5 / TileRT goal.
- **vLLM on Modal:** Higher throughput batching; not TileRT co-design path operator chose.