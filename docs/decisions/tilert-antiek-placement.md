# TileRT × Antiek product placement (GLM-5.2)

**Status:** Strategic architecture (2026-06-23, revised for dual-mode + GLM driver)  
**Weights:** `zai-org/GLM-5.2-FP8` on Hugging Face (753B; updated ~Jun 2026)  
**Engine:** TileRT v0.1.4, `load_backend("glm5")`, `--model_type glm-5` weight converter  
**Deploy:** `infrastructure/modal/tilert_glm5/` → Antiek provider `tilert`, tier `speed`  
**Routing:** `engagement_policy` in `config.yaml` + `dispatch(..., latency_mode=)`

**Operator thesis (2026-06-23):** Default **Brain = GLM** (`brain_choice=glm`) — TileRT when **in-product** (`interactive`). Users toggle **premium** for Opus/pro driving tiers (quality over cost). **Off-product** → autonomous throughput on DeepSeek / Xiaomi / Kimi (`research_*` tiers); per-investigation `deliverable_speed_preference` can still put driving roles on TileRT. Future: **Fable/Mythos** CEO + **NotDiamond** (see `notdiamond-fable-ceo-stack.md`). Additional brains join the closed set only after operator vibe-check.

This document states **where TileRT earns its place** in your stack—Deep Research, Read, Write, Speak, Engine, Harness, CLIs, Agents—and where it **must not** be forced, with evidence and falsifiers.

---

## 1. What TileRT actually optimizes (intellectual honesty)

TileRT is not “a faster vLLM.” It is a **latency-first execution paradigm**:

| Dimension | Throughput stack (vLLM, batch APIs, Modal Auto Endpoints) | TileRT |
|-----------|-----------------------------------------------------------|--------|
| Primary metric | Tokens/sec **aggregate** under concurrent requests | **Time per output token (TPOT)** on flagship MoE models |
| Hardware story | Flexible GPU counts; good batching | **8× B200** co-designed path; persistent engine, tile pipeline, MTP/DFlash acceptance |
| Economics | Pay per token via API or GPU-seconds at moderate utilization | **Dedicated 8-GPU node**—high fixed cost; wins when **serial agent latency** dominates value |
| API surface (today) | OpenAI-compat native | **Python generator + your HTTP shim** (Antiek: `OpenAICompatProvider`) |
| Model coupling | Loosely coupled to HF weights | **Converter + sharded layout**; backend **one model type per process** |

**Fair conclusion:** TileRT is defensible when **interactive closure time** (agent step, tool round-trip, REPL iteration, CLI turn) is the binding constraint—not when **total investigation spend** or **long-context synthesis quality** is.

TileRT’s own framing—“**speed as scaling law**”—matches agentic and test-time scaling: faster steps ⇒ deeper search *if* quality per step holds. That is a **hypothesis** for Antiek, not a theorem. You validate it with dispatch telemetry (`latency_ms`, verifier pass rate, cost-per-acceptable-synthesis), not slogans.

---

## 2. GLM-5.2 on Hugging Face vs TileRT converter

**Fact:** `zai-org/GLM-5.2` and `zai-org/GLM-5.2-FP8` are public on Hugging Face.

**Engineering fact:** TileRT documents conversion via:

```bash
python -m tilert.models.preprocess.weight_converter --model_type glm-5 ...
```

There is **no separate `glm-5.2` type** in public TileRT v0.1.4 docs. The defensible posture:

1. **Default prep repo:** `zai-org/GLM-5.2-FP8` (operator bandwidth / serving).
2. **Converter:** still `--model_type glm-5` until TileRT explicitly documents 5.2.
3. **Verification gate (mandatory before prod):** run `prep_weights` → smoke `tilert.generate` → one Antiek `dispatch` smoke on `speed` tier; if converter or generator fails, **stop**—do not silently fall back without logging a `tilert.weights_incompatible` decision event.
4. **Served model id:** Antiek config uses `glm5` (provider contract); expose alias `glm-5.2` in `/v1/models` for clients if needed—dispatch model string must match config.

Modal Auto Endpoints **not** listing GLM-5.2 does **not** contradict HF availability; it only means Modal’s managed catalog lags. **Self-hosted TileRT on Modal B200:8** is the correct lane for your goal.

---

## 3. Your product map → TileRT advantage (by surface)

### 3.1 Deep Research Workflow (Antiek core)

**Graph + typed event log** is the product (`architecture_notes` §1.1). Research generates **many** `dispatch.call` events across roles.

| Phase / role | Today (config posture) | TileRT advantage? | Recommendation |
|--------------|------------------------|-------------------|----------------|
| **note_taker, grounder, evidence_retriever, parameter_extractor** | `flash` → Hermes/Grok (zero marginal $ thesis) | **Weak** on cost alone—volume roles want **cheap bulk**, not 8×B200 serial premium | Keep **flash** on subscription/API path unless latency blocks UX |
| **decomposer, connector, challenger, user_agent** | `pro` base; **interactive → `speed`** | **Strong** when user is in-product | **Wired:** `engagement_policy.interactive` maps these to TileRT |
| **synthesizer** | `synthesis` base (Opus); **interactive → `speed`** | **Operator bet:** GLM-5.2 drives engaged synthesis; autonomous → `research_synthesis` (Kimi/DeepSeek) | **Falsifier:** verifier pass rate −5pp vs Opus → drop interactive synthesizer override only |
| **verifier** | `verify` with mandatory fallback | **Mixed**—latency helps redispatch loops; cross-family value is **model diversity**, not raw TPOT | TileRT as **optional verify path** only with A/B on false-pass rate |
| **RLM root** (meta-reasoning, code in REPL) | Spec: root **pro**, sub-LLMs **flash** (`rlm_integration_spec` §4.5) | **Strong** for **root** when iterations are latency-bound | TileRT **`speed`** for **root** only; sub-calls stay **flash** (MiMo/DeepSeek Flash)—preserves cost shape |
| **RLM sub-LLMs** (per-chunk extract) | Flash tier | **Poor**—high **count**, small prompts; TileRT wants **fat serial** decode | Never route bulk sub-calls to TileRT |

**Defensible Antiek thesis for TileRT:** **`interactive` = speed lane** (driving model); **`autonomous` = throughput APIs** on flash/pro/synthesis roles — not a single global model swap.

### 3.2 Read

Read path = ingestion, OCR, wrestling, embeddings (`acquisition/`, `processing/`). Dominant compute is **not** generative LLM decode at 1000 TPS.

| Component | TileRT? |
|-----------|---------|
| GLM-OCR, parsers, chunking | **No**—different models/modalities |
| Document **wrestling** (distill long PDF) | **Partial**—if wrestling becomes **RLM root** on huge docs, TileRT helps **root** latency; bulk chunk sub-calls stay flash |

### 3.3 Write

Write = graph selection + synthesis + deliverables. **Interactive** synthesis routes to TileRT; **autonomous** memos use Kimi/DeepSeek. Opus remains the **base** `synthesis` tier for paths without engagement overrides.

| Use | TileRT? |
|-----|---------|
| Final research memo while user is **in-product** | **Yes** (`interactive` + synthesizer override) |
| Background memo while user is **off-product** | **No** (`research_synthesis`) |
| **Draft scaffolding**, outline bullets, section headers in tight loop | **Yes** (experimental `speed`) |
| Miche / caffenagent **interview** copy generation | **Maybe** for **low-latency turn-taking** if interview provider points at `tilert`—measure round-trip SLA |

### 3.4 Speak

Speak = ASR + TTS + voice interview (`transcription`, `tts` tiers; caffenagent Modal ASR). **GLM-ASR / GLM-TTS** are separate Z.ai lines—not served by TileRT `glm5` backend.

| Component | TileRT? |
|-----------|---------|
| Transcription (MiMo ASR on Modal) | **No** |
| TTS | **No** |
| **LLM between turns** (interviewer brain) | **Yes**—candidate for `speed` if voice mode needs sub-second **thinking** between utterances |

### 3.5 AI Engine (substrate)

The engine is **dispatch + event log + graph**, not a model. TileRT integrates **only** as provider `tilert`:

- Same `dispatch()` contract, `DispatchCall` events, fallback chain.
- **No** `import tilert` in substrate—already enforced in `infrastructure/modal/tilert_glm5/DESIGN.md`.

**Philosophy alignment:** TileRT’s speed scaling **amplifies** dispatch **frequency** only if roles are wired to use it; the engine’s compounding graph thesis still depends on **event volume and attribution**, not TPOT alone.

### 3.6 AI Harness (Miche, PhonePanion, caffenagent surfaces)

Harnesses are **thin clients** to engine/API (`miche_harness.yaml`: Tailscale anchor, tabs, CLI profiles). TileRT belongs **server-side**:

- Miche tabs calling `api.antiek.ai` inherit tier routing from gateway config.
- **Do not** embed TileRT in device harnesses.

### 3.7 AI CLIs (Codex, Claude Code, Grok Build, conclave)

CLIs are **latency-native**—best product fit for TileRT in your portfolio:

| CLI | Fit | Wiring |
|-----|-----|--------|
| **Codex** | **Excellent**—per-turn TPOT dominates feel | mimo2codex generic provider → Modal OpenAI shim (Bearer), `wire_api=chat` |
| **Claude Code / Grok** | Good if routed through same compat proxy | Same HTTP surface |
| **Conclave** | **Poor default**—parallel multi-agent grading wants **many concurrent** calls; one TileRT node = **serial** | Keep conclave on API providers; optional **single** “speed juror” only as experiment |

### 3.8 AI Agents (caffenagent cycle, maintainer, RLM orchestrator)

| Agent pattern | TileRT fit |
|---------------|------------|
| Long-horizon **caffenagent** orchestrator (many tools, critic loops) | **High** for **primary coder model** if 8×B200 budget accepted |
| **Maintainer loop** (5-min triage) | **Low**—cheap flash sufficient |
| **RLM orchestrator** | **High** on **root**; sub-calls remain flash |

---

## 4. Where to implement (concrete, hard to vary)

### Layer A — Inference plane (done scaffold)

- Modal `antiek-tilert-glm5`, Volume weights from `zai-org/GLM-5.2-FP8`, MTP env flag.
- OpenAI `/v1/chat/completions` + Bearer.

### Layer B — Antiek dispatch (done scaffold)

- Provider `tilert`, tier `speed`, fallback `xiaomi` / `mimo-v2.5-pro`.
- Env: `ANTIEK_TILERT_API_KEY`, `ANTIEK_TILERT_BASE_URL`.

### Layer C — Routing policy (**implemented**)

`engagement_policy` in `config.yaml` + `latency_mode` on `dispatch()`. Gateway / session layer should pass `interactive` when the user is present, `autonomous` for background agents (or set `ANTIEK_LATENCY_MODE`).

```yaml
engagement_policy:
  default_mode: autonomous
  interactive:
    role_tier_overrides:
      synthesizer: speed   # GLM-5.2 driver (operator 2026-06-23)
      decomposer: speed
      # … connector, challenger, user_agent, knowledge_extractor
  autonomous:
    role_tier_overrides:
      synthesizer: research_synthesis
      decomposer: research_pro
      note_taker: research_flash
      # …
```

### Layer D — Research entry tier (closed set discipline)

`research_tier.py` is **only** `{fast, deep}`. Do **not** add `ultra` without ADR. Instead:

- **fast** stays MiMo.
- **deep** stays DeepSeek.
- TileRT enters via **`speed` tier + overrides** on specific investigations or roles—not a third research dropdown.

### Layer E — CLIs / personal coding

- Codex profile → TileRT Modal URL (parallel to OpenRouter GLM-5.2).
- Personal coding validates TileRT **before** Antiek prod routing.

### Layer F — Telemetry & falsifiers

Ship with any Stage 1 routing:

| Metric | Healthy signal | Falsifier (revert routing) |
|--------|----------------|----------------------------|
| p50 `latency_ms` on `speed` vs `pro` | Large drop on same prompt class | No improvement → TileRT not on critical path |
| Verifier pass rate | ≥ prior tier − 5pp | Worse → quality not defensible |
| Cost per investigation | Bounded cap per RLM session | Outliers per `rlm_integration_spec` §4.4 |
| GPU $/accepted synthesis | Not measured yet | If >> Opus path, speed thesis fails for Write |

---

## 5. Risks (fairness requires stating them)

1. **Fixed 8×B200 cost** vs Hermes zero-marginal flash—economic regression if overused for bulk roles.
2. **Converter / 5.2 compatibility**—assumption until smoke proves otherwise.
3. **Single-stream serving**—conclave, parallel sub-agents, and high fan-out flash roles **contend** on one node.
4. **Cold start** on Modal when `min_containers=0`—agent “first token” may lose to warm API unless `min_containers=1`.
5. **Vendor concentration**—TileRT + Z.ai weights + Modal; mitigated by **fallback chain** (already in `speed` tier).
6. **Synthesis voice on GLM**—interactive override is live; revert override (not the whole stack) if verifier data fails.

---

## 6. Philosophy in one paragraph (defensible)

Build **alongside TileRT** means: **two clocks**—**engagement latency** (user in Antiek → TileRT GLM-5.2 as driver) and **autonomous throughput** (user away → DeepSeek/Xiaomi/Kimi on `research_*` tiers). The graph remains the product; TileRT is the **interactive motor cortex**; API researchers are the **batch metabolism**. Future **Fable/Mythos + NotDiamond** sits above dispatch as orchestration, not a second router. **GLM-5.2-FP8** + TileRT wins **iff** faster engaged loops improve accepted outcomes; autonomous work must not steal 8×B200 serial capacity.

---

## 7. Immediate operator checklist

1. `modal run .../prep_weights.py --hf-repo zai-org/GLM-5.2-FP8`
2. Smoke generator + HTTP completions
3. Set gateway env keys; confirm `/health` lists `tilert` when key present
4. Codex/mimo2codex personal path for one week
5. Only then Stage 1 `role_tiers` for `challenger` / `user_agent`
6. Document result in `docs/decisions/` with verifier + latency numbers