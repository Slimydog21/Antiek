# Deep Research Mission Control — design evidence

## Scope and authority

- Branch: `goal/deep-research-mission-control`
- Exact stacked base: `goal/curiosity-observatory` at `8407d07f1fec7c2c0582d2b679383d73505293ae` (PR #2535)
- Residual addressed: the product's declared hero workspace was a bare padded input column and had no whole-surface visual contract.
- Preserved authority: the existing research plan, session, cost, launch, steering, reactions, arcade, `PanelHost`, store, model, and backend contracts remain authoritative. This cycle adds presentation and local operation fencing; it does not invent product truth.
- Privacy boundary: operation and polling failures render fixed private-safe messages. Raw exceptions never enter the page.
- Landmark boundary: the mission-control frame is a `div` inside `PanelLayout`'s authoritative route `<main>`. This cycle also corrects the shell's small-tier wrapper to use that same route landmark, so the routed DOM has exactly one main at desktop and small widths.
- Race boundary: a synchronous operation fence prevents duplicate creates before React can commit a busy state. Async results commit only while mounted and only for the current operation generation, including under Strict Mode remount behavior.

## Generated environment

- Built-in ChatGPT Image generation ID: `exec-62ad4c72-8b70-4c20-b929-5d3a87081e69`
- Source PNG: `/Users/slimydog/.codex/generated_images/019f5c1a-0048-7b21-9fe9-4de63c5fe645/exec-62ad4c72-8b70-4c20-b929-5d3a87081e69.png` (1536×1024)
- Runtime asset: `apps/reading/src/brand/werner/research/deep_research_mission_control_v1.webp`, WebP quality 72, 139.04 kB in the production build
- Runtime SHA-256: `c654871fa0bb144c06ae2745ab978dc5d6318c9a7b1ec8807b748ec79cb1e183`
- Prompt boundary: an empty hand-painted Antarctic research observatory with restrained brass instruments, central negative space, glacial daylight, and warm task lighting; explicitly no mascot, people, UI, text, charts, buttons, results, or product semantics.
- Semantic boundary: the raster is decorative, pointer-inert, and hidden from accessibility. Every question, phase, plan, action, result, and price remains live HTML.

## Visual proof

- Whole-surface Storybook states: ready, creating, draft plan, active monitor, and private-safe failure.
- LostPixel: 15 new baselines across 768, 1024, and 1280 px; the targeted comparison passed twice.
- Production render: `docs/design-evidence/renders/deep-research-mission-control-production-1280.webp`.
- The production render was inspected directly in Chromium and confirms that the real generated raster and live HTML compose correctly.
- The preferred in-app browser was unavailable after its required browser-list troubleshooting returned no controllable tabs. Native Playwright/Chromium was used as the honest fallback; no in-app-browser verification is claimed.

## Verification

- Deep Research workspace suite: 14 files, 75 tests passed.
- Added integration proofs: real production raster/live-HTML boundary, exactly one routed main landmark through real `PanelLayout` at 1280 and 640 px, synchronous double-submit produces one request, private-safe create and polling failures, and Strict Mode behavior.
- TypeScript: passed.
- Design-token lint: passed.
- Type-scale lint (`npm run lint:type`): passed. An initial nonexistent `lint:type-scale` command was corrected rather than counted.
- Storybook production build: passed (1,039 modules).
- Reading production build: passed (2,482 modules). Main gzip 577.35 / 683.59 kB with 106.24 kB headroom; lemon gzip 49.95 / 58.59 kB with 8.65 kB headroom.
- Diff whitespace check: passed.
- Motion guard: the repository-wide command reports an inherited keyframe in predecessor file `library-archive-shelf.css`; this exact diff adds zero keyframes and uses the shared motion-safe spinner.
- hardenx 1.4.0 strict scan: LOW, zero REAL findings, OSV enabled, installed versions resolved from `uv.lock`; exit 0. The worktree has no hardenx corpus certificate, so the skill contract treats this as advisory. Patched dependency floors and unrelated high-entropy constants remained advisory.

## Independent pressure tests

- Fable 5 planner: unavailable because the account had no credits.
- Opus 4.8 planner: produced no result within 90 seconds and was stopped.
- Grok xhigh builder: oriented to the surface but produced no patch.
- GLM-CC `/ultracode` critic: provider returned HTTP 429.
- MiMo V2.5 Pro hostile critic: ACCEPT with two nonblocking observations (no telemetry in the intentionally private failure catch; harmless non-memoized create handler). It violated the requested read-only boundary by using a temporary stash for comparison; its own stash was restored and dropped, workspace contamination was removed, and no unrelated operator stash was altered afterward. Its verdict is recorded, but its process is not treated as clean evidence.
- Codex GPT-5.4 exact-diff hostile review initially rejected the cycle for a nested `<main>` and inherited raw polling error text. The first remediation exposed that `PanelLayout` used no main landmark at its small tier. The final correction makes the frame a `div`, gives both shell branches one authoritative route `<main>`, makes polling copy private-safe, and proves the real frame inside real `PanelLayout` at forced `xl` and `sm` tiers. The final targeted re-review returned `BLOCKERS: none` and `VERDICT: ACCEPT`.

## Integration posture

This is one stacked PR on PR #2535. The cycle does not merge or deploy. Remote CI remains the publication gate, and integration remains operator-controlled.
