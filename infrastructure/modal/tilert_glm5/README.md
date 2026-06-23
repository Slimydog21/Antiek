# TileRT GLM-5 on Modal (`antiek-tilert-glm5`)

Ultra-low-latency **GLM-5** via [TileRT](https://github.com/tile-ai/TileRT) on **8× B200**, exposed as **OpenAI Chat Completions** for Antiek `substrate/dispatch`.

See [DESIGN.md](./DESIGN.md) for Antiek boundaries and latency/cost tradeoffs.

## Prerequisites

- Modal workspace with **B200:8** quota (Team plan)
- Hugging Face access to GLM-5.2 weights (`zai-org/GLM-5.2-FP8`; full weights `zai-org/GLM-5.2`)
- `modal` CLI ≥ 1.5

## 1. Secrets

```bash
modal secret create antiek-tilert-auth \
  ANTIEK_TILERT_MODAL_TOKEN="$(openssl rand -hex 32)"

# Gated HF repos (prep_weights accepts `antiek-hf-hub` or `hf-token`):
modal secret create antiek-hf-hub HF_TOKEN="hf_..."
# or: modal secret create hf-token HF_TOKEN="hf_..."
```

## 2. Convert weights (one-time, ~hours)

From `prcrouch-feel` repo root:

```bash
modal run infrastructure/modal/tilert_glm5/prep_weights.py --hf-repo zai-org/GLM-5.2-FP8
```

Shards land in Volume `antiek-tilert-glm5-weights` at `/glm5-tilert`.

## 3. Deploy inference

```bash
# Optional: keep one warm node (faster, costs GPU while idle)
export TILERT_MIN_CONTAINERS=0
export TILERT_WITH_MTP=1   # TileRT multi-token prediction

# From repo root (app.py lazy-imports FastAPI inside the container — no local fastapi needed)
modal deploy infrastructure/modal/tilert_glm5/app.py
```

Deploy requires Modal secret **`antiek-tilert-auth`** (`ANTIEK_TILERT_MODAL_TOKEN`) and
converted weights on volume **`antiek-tilert-glm5-weights`** (step 2).

Note the **web URL** printed for `TileRTGLM5Service.web`.

## 4. Smoke

```bash
export BASE="https://<your-modal-web-url>"
export TOKEN="<ANTIEK_TILERT_MODAL_TOKEN>"

curl -sS "$BASE/health"
curl -sS "$BASE/v1/models" -H "Authorization: Bearer $TOKEN"
curl -sS "$BASE/v1/chat/completions" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"model":"glm5","max_tokens":64,"messages":[{"role":"user","content":"Say hi in five words."}]}'
```

## 5. Antiek production env

On the Hetzner VM (or local dispatch smoke):

```bash
ANTIEK_TILERT_API_KEY=<same as ANTIEK_TILERT_MODAL_TOKEN>
ANTIEK_TILERT_BASE_URL=https://<modal-web-host>   # no trailing slash
```

Dispatch registers provider `tilert` when `ANTIEK_TILERT_API_KEY` is set. Tier **`speed`** uses model id **`glm5`** (config.yaml).

## GLM-5.2

Default HF repo is **`zai-org/GLM-5.2-FP8`**. TileRT backend remains **`glm5`** / converter **`glm-5`**. Strategic placement: `docs/decisions/tilert-antiek-placement.md`.

## Codex (personal)

See [CODEX.md](./CODEX.md) for mimo2codex / Codex CLI wiring (SPR-06).