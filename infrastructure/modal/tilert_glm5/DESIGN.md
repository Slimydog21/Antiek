# TileRT GLM-5 on Modal — Antiek-aligned inference plane

## Problem

Modal **Auto Endpoints** catalog (2026-06) does not offer **GLM-5.2**; weights are on Hugging Face (`zai-org/GLM-5.2-FP8`). Operator serves **GLM-5-class** checkpoints via **TileRT** (not SGLang/DFlash), with a path into **Antiek** `substrate/dispatch` as provider `tilert`.

## Non-negotiables (from TileRT v0.1.4)

| Constraint | Implication |
|------------|-------------|
| **8× NVIDIA B200** | Modal: `gpu="B200:8"` (supported) |
| **torch==2.11.0+cu130**, transformers **4.46.3** | Base image: `ghcr.io/tile-ai/tilert:cu132-latest` + `pip install tilert==0.1.4` |
| **Sharded weights** (`weight_converter`, 8× `*_dev_*`) | Modal **Volume** `antiek-tilert-glm5-weights`; one-time prep job |
| **One backend per process** (`load_backend("glm5")`) | Single `@app.cls` per deployment; no multi-model colocation |
| **Converter `glm-5`** | HF default `zai-org/GLM-5.2-FP8`; TileRT still uses `--model_type glm-5` until upstream documents a distinct 5.2 type. **Mandatory smoke** after convert. Antiek model id `glm5` (alias `glm-5.2` in `/v1/models` optional) |

## Architecture

```
Antiek api.antiek.ai (Hetzner)
  └─ dispatch(role) → tier "speed" → provider "tilert"
        └─ OpenAICompatProvider (Bearer ANTIEK_TILERT_API_KEY)
              └─ POST {ANTIEK_TILERT_BASE_URL}/v1/chat/completions
                    └─ Modal @web_endpoint (FastAPI)
                          └─ GLM5Generator (TileRT, MTP optional)
                                └─ 8× B200, weights on Volume
```

**Boundary:** TileRT lives **only** behind this HTTP surface. Antiek never imports `tilert`; it only speaks OpenAI Chat Completions (same contract as DeepSeek/MiMo/Hermes).

## Latency vs cost knobs

| Knob | Speed | Cost |
|------|-------|------|
| `min_containers=1` | Warm 8×B200 always | High idle burn |
| `min_containers=0` + `scaledown_window` | Cold start + weight load | Scale-to-zero |
| `TILERT_WITH_MTP=1` | Higher tok/s (TileRT MTP) | Same GPU; quality acceptance stats vary |
| `max_containers=1` | No queue behind second replica | One inference stream per node (correct for 8-GPU shard) |

**Recommendation for “build alongside TileRT” iteration:** `min_containers=0` while converting weights; flip to `min_containers=1` on `main` env when Antiek `speed` tier is production-critical.

## Security

- Bearer token in Modal secret `antiek-tilert-auth` → `ANTIEK_TILERT_MODAL_TOKEN`
- Antiek prod: `ANTIEK_TILERT_API_KEY` (same value) + `ANTIEK_TILERT_BASE_URL` (Modal web URL, **including** `/v1` in base if using `/chat/completions` path override — mirror Hermes/OpenRouter pattern)

## Files

| File | Role |
|------|------|
| `app.py` | Modal App `antiek-tilert-glm5` |
| `openai_shim.py` | Messages → prompt; Chat Completions JSON |
| `prep_weights.py` | HF download + `weight_converter` → Volume |
| `README.md` | Deploy / smoke / Antiek env |

## Future (unchanged Antiek code)

- Add `speed` role mappings in `config.yaml` (`coder`, `interactive` roles)
- Optional SSE streaming endpoint (Codex/mimo2codex); dispatch stays non-streaming first
- Prime-RL promoted weights: `--custom-volume-path` style path on Volume, same `glm5` backend