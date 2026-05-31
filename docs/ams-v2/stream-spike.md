# AMS-v2 M2 — Generative-Stream Feasibility Spike

**Branch:** `spike/ams-v2-stream` (throwaway off `caffen/AMS2-integration`; never merged to main — only this doc is a merge candidate).
**Question:** can the v2 mountain shell present a *near-real-time generative stream* — a Krea-driven sky that visibly re-renders as the reader moves through a session — and is it worth building as SPR-05?
**Method:** read the verified `origin/main` Krea wiring, steelman the three mechanisms that could produce a stream, and PROVE the measurable half of the envelope in a real browser (Playwright against the live `<Scene/>` compositor). Numbers that genuinely cannot be measured without a key are recorded as the literal string `not measured (no key)` — never invented.

The verdict is at the bottom. It is earned, not asserted.

---

## 1. What Krea actually offers

The proxy the browser talks to is `interfaces/research/api/krea_routes.py`, mounted by `register_krea_routes(app)` (L549). Three routes exist and no more:

- `POST /krea/generate` (L592) — submit a generation, returns `{job_id, status}`.
- `GET /krea/jobs/{job_id}` (L620) — poll one job.
- `GET /krea/scene` (L639) — the high-level endpoint SPR-04 consumes: prompt-build → cache → gate → submit → **poll-to-completion** → typed art or typed fallback.

This is an **async job → poll image generator. There is no streaming endpoint.** No SSE, no WebSocket, no frame channel — nothing that pushes successive frames at a frame rate. Any "stream" the shell shows would have to be *manufactured* on top of submit/poll/cache.

The module is explicit that its wire shape is not load-bearing fact. Its honesty banner (L37–65) states:

> HONESTY — the Krea wire shape below is DOC-DERIVED, NOT LIVE-VERIFIED.
> No live call was made (no key in sandbox). … Submit a generation (async job pattern): `POST {BASE}/generate/image` → `200 {"job_id": "job_abc123", "status": "queued"}`. Poll a job: `GET {BASE}/jobs/{job_id}` → `200 {"job_id": …, "status": "completed", "output": {"image_url": "https://…"}}`.

So every Krea *number* in this document inherits that caveat: doc-derived, not live-verified. The pricing the module codes against is `Flux ~$0.04/image, ~4s/image` (L14, L88–94) and `Krea video ~$0.20/sec` (L15) — also doc-derived, not live.

The poll loop in `/krea/scene` runs against `_POLL_BUDGET_S = 12.0` (L102) on `_POLL_INTERVAL_S = 0.75` (L103): up to ~12 seconds of polling per scene-state before it gives up and falls back. Spend is bounded by `_DEFAULT_DAILY_UNIT_CAP = 50` (L119; env `KREA_DAILY_UNIT_CAP`) and `_DEFAULT_RATE_LIMIT_MAX = 6` per 60 s (L129–130; env `KREA_RATE_LIMIT_MAX`). `KREA_KILL_SWITCH` (L379–385) is a key-independent operator panic lever — any of `{1,true,yes,on}` forces the fallback regardless of key.

Critically for what follows, *every* failure mode lands on one typed response, `DisabledResponse` (L211): HTTP **503**, `enabled:false`, `isFallback:true`, a stable `reason` string, and the `scene_key`. The gate order in `_gate()` (L576–590) is kill-switch → no-key → over-budget → rate-limited; the first trip short-circuits and **no upstream call is made past a tripped gate**. It is always a 503, never a 500, never a hang. That single contract is what makes the v2 floor robust, and it is the contract SPR-05 inherits unchanged.

The one place the upstream shape can change is flagged in the source: the comment header at L411, *"Upstream adapters (doc-derived; the ONLY part that changes if the live Krea schema differs)"*, over `_submit_generation` (L436) and `_poll_job` (L495). The module docstring (L59–61) says the same. **This adapter seam at ~L411 is the only attachment point for any server-side frame-pump path** discussed below; nothing in the budget/cache/disabled contract above it would change.

---

## 2. The three mechanism paths (steelmanned)

A real generative stream needs frames arriving fast enough and cheaply enough to read as motion or near-real-time refresh. There are exactly three mechanisms that could deliver one. Each is steelmanned with a named real candidate, where it attaches, its best case, and the *numeric* threshold its best case still misses.

### Path A — faster sub-second model, polled fast (poll-driven pseudo-stream)

**Candidate:** a sub-second turbo image model (the "Flux-schnell / turbo" class Krea exposes) submitted and polled tightly through the existing `/krea/scene` submit→poll loop, tightening `_POLL_INTERVAL_S` from 0.75 s toward the model's true latency.

**Where it attaches:** no new module — it reuses `_submit_generation`/`_poll_job` at L411 with a faster model id and a tighter interval. This is the *minimal* path.

**Best case (doc-derived envelope, labelled):** Flux at `~4s/image` (L88–94) is a ceiling of `1 / 4s = ~0.25 generated frames per second`. Even a generously **hypothetical** sub-second turbo at ~1 s/image (a made-up best case, *not* doc-derived — more optimistic than Flux's only sourced rate, assumed purely to steelman Path A) would be only ~1 generated fps. Run as a pseudo-stream at the documented Flux rate, 4 s/image = **15 images/minute = ~$0.60/minute** (`15 × $0.04`), which **exhausts the 50-unit daily cap in ~3.3 minutes** (`50 / 15`).

**Threshold it misses:** "near-real-time generative stream" means motion-grade refresh — call it **≥ 10 generated fps**, an order of magnitude below cinematic but the floor at which successive frames read as continuous change. ~0.25 gen fps (Flux, sourced) and even ~1 gen fps (the *hypothetical* optimistic turbo — not a documented rate) miss ≥ 10 fps by **1–2 orders of magnitude**. The per-frame cost also misses any session-grade economics: at ~$0.60/min a single reader exhausts the whole day's spend before finishing one chapter. Both the **fps threshold** and the **$/min-at-cap threshold** fail, on doc-derived numbers carrying the not-live caveat.

### Path B — server-side frame-pump over SSE/WS at the L411 seam

**Candidate:** a new server-side push channel — FastAPI `StreamingResponse`/SSE or a WebSocket — that pumps frames to the browser as they complete, so the client does not poll. This is the only path that could *architecturally* be called "streaming."

**Where it attaches:** the L411 adapter seam. The module docstring already names this as the place a different upstream wire shape plugs in. An SSE/WS pump would be a sibling to `_submit_generation`/`_poll_job`.

**Best case:** SSE/WS removes *polling* latency and the 12 s poll budget — frames would surface the instant the generator finishes one. The transport could comfortably carry 60 messages/second.

**Threshold it misses — and why it is the decisive one:** the transport is not the bottleneck; the **generator** is. SSE/WS at 60 msg/s pumping a 4 s/image (or even a 1 s/image) generator still delivers ~0.25–1 frame/s of *new content* — the same ≥ 10 gen fps miss as Path A, now with an empty fast pipe. And the channel itself is **entirely NEW**: there is no SSE/WS endpoint on `origin/main` (§1), no client consumer, no test, and it would have to re-implement the budget/cache/kill-switch/typed-503 contract that submit/poll already enforce — a contract the spike proves is the actual v2 win. A faster transport in front of a 4 s/image source clears no fps threshold it could not already clear without it. The **gen-fps threshold (≥ 10)** fails; the path's only real contribution (transport latency) is not where the deficit lives.

### Path C — looped / crossfaded video clip (~$0.20/sec)

**Candidate:** Krea video generation (`~$0.20/sec`, L15), producing a short clip that loops, crossfaded between scene-states — true motion instead of stills.

**Where it attaches:** a new video adapter at L411 plus a `<video>` presentational layer beside `KreaArtLayer`. Both are NEW.

**Best case:** a 10 s clip *is* genuinely 24–30 fps of real motion once it arrives — it is the only path that delivers motion-grade frame rate at all, and a looped clip needs no per-frame generation.

**Threshold it misses:** economics and latency, not fps. At `~$0.20/sec`, one 10 s clip is **$2.00** — a single clip equals the *entire* `~$2.00/day` worst-case the 50-unit cap is sized for (L112). A handful of scene-state changes per session blows the day's budget on the first reader, and there is no per-second video budget gate on `origin/main` (the cap counts image units, L109). Time-to-first-frame is also far worse than stills (video generation is slower than 4 s/image). It clears the **fps** bar and decisively fails the **$/min-at-cap** bar (one clip = a full day's budget), with TTFF unmeasured-but-doc-worse. NEW video adapter + NEW `<video>` layer + NEW per-second budget gate are all required before it could even be tried.

**Fairness check:** a NO-GO is only fair if the *best* path's *best* case still misses a stated number. It does. Path A misses fps by 1–2 orders of magnitude *and* misses $/min. Path B's transport is fast but feeds the same slow generator, so it misses the same fps bar with no compensating win. Path C clears fps but one clip costs a full day's budget. No path clears both the fps and the cost threshold; the fastest transport (B) does not move the bottleneck.

---

## 3. Measured numbers (the M2 four metrics)

These come from the throwaway Playwright gate `apps/reading/e2e/_ams/stream-spike.spec.ts` (the `chromium`/Storybook project), driving the real `<Scene/>` compositor via the `ProceduralFloor` story (`apps/reading/src/scene/StreamSpike.stories.tsx`, story id `ams-v2-stream-spike--procedural-floor`). The spec ran with `contextOptions: { reducedMotion: "no-preference" }` so `useSceneClock` was **not** frozen (asserted live: `data-scene-frozen="false"`). Real values are persisted to `apps/reading/e2e/_ams/.artifacts/stream-spike-metrics.json`.

| Metric | Value | Source / units | How |
|---|---|---|---|
| (i) time-to-first-frame | **194 ms** (latest persisted run; jitters ~0.19–0.3 s across runs) | measured, procedural floor, ms | page nav-start (`PerformanceNavigationTiming.startTime`) → `scene-root` attached + first rAF tick, timed *inside* the page |
| (ii) sustained **floor** fps | **60.1 fps** | measured, over a 2000 ms window | **distinct Snow-canvas frames/sec** (the canvas bitmap genuinely changed 121× in 2000 ms); honest bar `MIN_FLOOR_FPS = 20`, cleared with headroom |
| (ii′) sustained **generative** fps | **not measured (no key)** | — | doc-derived ceiling: Flux ~4 s/img ⇒ **~0.25 gen fps** |
| (i′) time-to-first-**generated**-frame | **not measured (no key)** | — | doc-derived: Flux ~4 s/img submit→complete + up to 12 s poll budget |
| (iii) $/minute @ configured cap | **not measured (no key)** | — | doc-derived: 4 s/img = 15 img/min = **~$0.60/min**, exhausts the 50-unit cap in **~3.3 min** |
| (iv) budget-trip behaviour | **scene stays visible** (`true`) | measured, fallback state | `assertSceneVisible` PASSED on a scene-only band |

The two distinct fps rows are the heart of the question. **Floor fps (60.1) is not generative fps.** Crucially, this 60.1 is *not* "how often the browser tab fires `requestAnimationFrame`" — that bare cadence is ~60 in any foreground Chromium tab even when the clock is frozen and the canvases draw nothing, so it would be a vacuous proof of motion. The gate instead samples the **Snow canvas's real pixel buffer** repeatedly (`canvas.toDataURL`) and counts how many *distinct* frames it produced: **121 distinct bitmaps in the 2000 ms window** (recorded as `distinctCanvasFrames: 121`, alongside `browserRafFps: 60.1` kept separate so the two are never conflated). That every one of the 121 rAF ticks yielded a *different* bitmap (121 distinct / 121 ticks) is the proof: the canvas is genuinely repainting new content each frame, not holding a static image while the tab idly fires rAF. Snow's 140 particles advance with the clock's `t` (`snowAt(f, t, …)`), so a changing bitmap is direct evidence that `useSceneClock`/`subscribeSceneClock` is genuinely driving the Clouds and Snow canvas painters — were the clock frozen, the bitmap would be one static frame and this number would collapse toward 0. The generative ceiling is ~0.25 fps. The clock-driven floor and the generative ceiling differ by ~240×, which is the whole reason the "stream" is illusory: nothing generative moves at the rate the floor does.

**Budget-trip is the load-bearing measurement.** The `ProceduralFloor` story IS the forced no-key / over-budget / kill-switch state: its injected `alwaysFallback` fetcher resolves to `{enabled:false, isFallback:true, reason:"over_daily_budget", scene_key:null}` — the exact typed-503 fallback shape. The gate confirmed `data-scene-fallback="true"` and `KreaArtLayer` reporting `data-krea="fallback"` (it paints nothing), then `assertSceneVisible(page, {x:0.25, y:0.18, width:0.5, height:0.22})` PASSED on a scene-only band (no chrome, no caption). The committed screenshot (`stream-spike-procedural-floor.png`) visually confirms it: gradient sky + far peaks + drifting clouds + scattered snow + the honesty caption *"PROCEDURAL FLOOR — no key / over-budget (fallback). No live Krea."* **The scene keeps painting a varied, moving mountainscape when no generative frame ever arrives.** That is the v2 win, and it holds regardless of the verdict on streaming.

Per RULE 2 / RULE 3, the capture is the proof. The spec passed (`1 passed, 3.4s`) via `STORYBOOK_URL=http://localhost:6006 npx playwright test --project=chromium`. The prose above conforms to the capture; if they ever disagree, the capture wins. Note specifically that the floor-fps claim is *clock-dependent by construction* (it counts changing canvas bitmaps, not bare rAF ticks), so the 60.1 is genuine motion, not the tab merely firing rAF. (A harness note: the `ams-real`/vite-preview `webServer` would time out because the sandbox cannot build the SPA; setting `AMS_APP_URL=http://localhost:6006` sidesteps booting it. This does not touch the `chromium`-project spec, which navigates via its own `STORYBOOK_URL`.)

---

## 4. The engine contract SPR-05 implements

Everything in this section is **to be implemented by SPR-05** (which owns `src/scene/`). The spike implements none of it; it only proves the seam these contracts ride on already exists and behaves.

**Frame-source interface — compatible with `SceneFetcher`/`SceneArt`.** SPR-05 changes the *frame source* without touching any consumer by swapping the injected `SceneFetcher` (`apps/reading/src/krea/useKreaScene.ts` L58: `export type SceneFetcher = (scene: SceneState) => Promise<SceneResult>;`). `useKreaScene` re-fetches only when `sceneKeyOf(scene)` changes (its `[key]` effect dep, L173), never per frame, and never throws — it always returns non-null `art` (the deterministic placeholder on fallback). `useSceneArt` (`apps/reading/src/scene/useSceneArt.ts`) wraps it and exposes the frontend `SceneArt` shape `{ imageUrl, prevImageUrl, fadeKey, isFallback, status, reason }`. The cadence invariant is binding: **Krea is fetched only on mood change, never per frame / on the clock** (the clock is deliberately not a dep). Whatever SPR-05 makes the frame source — faster model, an L411 SSE/WS pump, a video adapter — it conforms to `SceneFetcher` returning a `SceneResult`; consumers are untouched.

**Crossfade rule — presentational, no fetch.** Frame swaps crossfade via `KreaArtLayer` (`apps/reading/src/scene/layers/KreaArtLayer.tsx`): two stacked divs, the incoming keyed on `art.fadeKey` (L63), opacity 0 → 0.82 over `transition "opacity var(--motion-slow) var(--ease-standard)"` (L41). `useSceneArt` bumps `fadeKey` on swap. The layer is **purely presentational and never fetches** — so increasing the frame source's rate cannot, by construction, increase the fetch rate; it only changes how often the crossfade fires. On `isFallback` the layer renders nothing (`data-krea="fallback"`) and the procedural floor is the whole picture.

**The 60 fps floor — `useSceneClock` is the rAF source; `ProceduralSky` is the static base.** The literal 60 fps floor is `useSceneClock` / `subscribeSceneClock` (`apps/reading/src/scene/useSceneClock.ts`, rAF loop at L103; imperative `subscribeSceneClock` at L161–225) driving the Clouds and Snow *canvas* painters. `ProceduralSky` (`apps/reading/src/scene/layers/ProceduralSky.tsx`) is **pure CSS + SVG, not a `<canvas>`, with no rAF loop of its own** — it is the always-painted static base (gradient + peak silhouette). The clock freezes to a single frame under `prefers-reduced-motion: reduce` (`FROZEN_T = 1500`, `frame = 0`). SPR-05 must keep the floor independent of the frame source: the floor animates at 60 fps off the clock whether or not a single generative frame ever arrives — which is exactly what the gate measured (60.1 distinct canvas frames/sec while `isFallback`, proving the canvas painters genuinely repaint on the clock, not merely that the tab fires rAF).

**Degradation — inherit the typed-503 semantics verbatim.** Budget-trip / kill-switch / offline / no-key all flow through the existing `krea_routes.py` contract: gate order kill-switch → no-key → over-budget → rate-limited (`_gate()` L576–590), the typed `DisabledResponse` 503 (L211) carrying a stable `reason` + `scene_key`, always 503 never 500 never hang. SPR-05's frame source — including any new L411 pump — **inherits this unchanged**: a tripped gate yields fallback and the floor keeps rendering. SPR-05 adds no money-routing and no new spend path that bypasses the cap/kill-switch.

---

## 5. Verdict

# NO-GO

**On a near-real-time *generative* stream.** The proposed/implied path — procedural floor plus periodic Krea art via the existing `/krea/scene` + `useSceneArt` (Path A) — cannot produce motion-grade generative frames at a defensible cost.

**The numbers that failed each threshold:**

- *Generative fps* — required **≥ 10 gen fps** for "near-real-time"; doc-derived ceiling is **~0.25 gen fps** (Flux ~4 s/image). Miss by ~40×. (`not measured (no key)`, doc-derived, carries the not-live caveat.)
- *$/minute at the configured cap* — a poll-driven pseudo-stream at 4 s/image is 15 img/min = **~$0.60/min**, **exhausting the 50-unit cap in ~3.3 minutes** of one reader's session. Fails any session-grade economics. (`not measured (no key)`, doc-derived.)

**Steelman of the rejected alternatives** (§2): Path B (SSE/WS frame-pump at the L411 seam) is the only architecturally "streaming" option, but its fast transport feeds the *same* ~0.25–1 gen fps generator — it moves zero of the deficit and is entirely NEW code re-implementing the budget/typed-503 contract. Path C (looped video, ~$0.20/sec) is the only path that clears the fps bar, but a single 10 s clip costs **$2.00 = a full day's budget** and needs a NEW video adapter, a NEW `<video>` layer, and a NEW per-second budget gate. No path clears both fps and cost; the best path's best case still misses a stated number, so the NO-GO is fair.

**What v2 actually gets — and it is the real win.** Visibility holds *either way*, and that is measured, not asserted: TTFF **194 ms** (page nav-start → first painted frame; ~0.19–0.3 s across runs), sustained floor **60.1 fps** (distinct canvas frames/sec — clock-driven repaint, not bare rAF cadence), and a budget-trip that keeps a varied, moving mountainscape on screen (`budgetTripSceneVisible: true`, screenshot-confirmed) when no generative frame ever arrives. The v2 shell should ship the **periodic-art-over-a-living-procedural-floor** design SPR-04 already built and §4 contracts: the 60 fps floor is the experience; Krea stills are a slow, mood-gated, budget-bounded *tint* on top via the crossfade — never the motion, never a stream.

**What would reverse this.** This verdict flips if, *with a real `KREA_API_TOKEN`*, a named sub-second turbo model is benchmarked end-to-end at **time-to-first-generated-frame < 500 ms** and **sustained ≥ 10 generated fps** at **≤ ~$0.10/minute at the 50-unit cap**. That $0.10/min cost gate is derived the same way the $0.60/min rejection is: the 50-unit cap is worth `50 × $0.04 = ~$2.00/day` (L112). At the rejected $0.60/min, `$2.00 / $0.60 ≈ 3.3 min` of one session burns the whole day — the rejection. To make a single uninterrupted reading session (call it ~20 min) survivable inside that same daily cap, spend must drop to `$2.00 / 20 min = ~$0.10/min` — i.e. the per-frame cost has to fall ~6× from the Flux rate (or one reader's session alone still exhausts the day, which is the same failure in slower motion). The specific future measurement is: submit→first-frame latency and a 2000 ms generative-fps window against that model through the L411 adapter, plus the live $/min at the configured cap — the three rows recorded here as `not measured (no key)`. Until those three are measured and clear those numbers, the generative stream stays a NO-GO and the procedural floor is the product.
