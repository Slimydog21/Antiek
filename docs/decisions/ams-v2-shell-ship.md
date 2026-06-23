# Antiek Mountain Shell v2 — shipped to prod (the two v1 failures killed)

**Date:** 2026-06-01
**Branch:** `caffen/AMS2-integration` → `main` (PR #49, merge `491c031`)
**Source spec:** `~/specs/antiek-mountain-shell-v2/` (10 sprints) + the on-repo
record `docs/ams-v2/` (verification report, verified-interfaces §11, stream-spike).
**Status:** ✅ Shipped + LIVE on `antiek.ai`. Backend deliberately NOT deployed
(AMS2's only backend touch is a comment).

## Why this re-execution existed (the v1 failures it had to kill)

The v1 mountain-shell shipped green CI and an **invisible** result — the
generative scene never showed on the default route — and its spec **drifted from
the code** (the pages described `#scene-root` / a streaming route / `g`-chord
hotkeys that the code never had). AMS2 v2 was re-executed under two binding rules:
**(R2)** every sprint adds a real-browser Playwright experience-gate asserting the
*visible* outcome (vitest-only is not "done"), and the anti-fiction write-back
reconciles the spec to the as-built code so it stops being fiction the moment it
diverges. Both v1 failures are now verified dead — see
`docs/ams-v2/mountain-shell-v2-verification.md` (Anti-fiction ledger §6).

## Merge ledger (the 10 sprints, all in `491c031`)

| Sprint | What shipped | Merge SHA |
|---|---|---|
| SPR-01 | grounding + real-app experience-gate harness (the linchpin) | `c485b12` |
| SPR-02 | generative-stream feasibility spike → **NO-GO** (doc-only) | `60c4ba2` |
| SPR-03 | glass surface — the mountain is visible on `/` | `5e0f5c0` |
| SPR-04 | floating windows are the default interaction | `dc6187e` |
| SPR-05 | living generative background (procedural floor + periodic art) | `63351b6` |
| SPR-06 | rigged penguin — feet move, white box killed | `834c456` |
| SPR-08 | uniform `⌘+key` hotkeys (vim chords removed) | `693de2b` |
| SPR-07 | bottom-bar labels + `⌘` chips + igloo "Home" caption | `7bd7e7a` |
| SPR-09 | light-yellow tokens (weathered accents, loud bar, AA) | `af21f19` |
| SPR-10 | integration + experience matrix + resilience matrix + anti-fiction write-back | `4120438` |

(SPR-08 was sequenced before SPR-07 because SPR-07 consumes SPR-08's
`chipBindings()` map.)

## The decisions worth auditing later

- **The generative stream is a NO-GO (recorded, not built).** SPR-02's spike
  rejected a server-pushed scene stream; SPR-05 ships the **procedural 60fps
  floor + periodic Krea art over the existing `SceneFetcher` seam** instead.
  `interfaces/research/api/krea_routes.py` keeps exactly three routes; there is
  **no `useSceneStream.ts` and no streaming route**. The "streaming" language
  that survives in the SPR-02/05/10 spec pages is the *rejected* path, recorded
  verbatim — not the shipped one. Rationale: `docs/ams-v2/stream-spike.md`.
- **The default route is `modes/ResearchWorkstation/index.tsx`** — idle `/` is
  `<StartResearch embedded/>` (a bg-free root, so the scene shows through the
  margins); the dense IDE is the active `/inv/:id` view. The SPR-03 page's
  `ResearchWorkstation.tsx` citation was stale; the write-back fixes it.
- **Hotkeys are `⌘O`/`⌘I` + per-product `⌘`-combos, not `g`-chords.** The
  `g`-chords were removed in SPR-08; the SPR-07 page's `bindingForProduct("home")
  → g h` notation is the pre-SPR-08 stale form, corrected in the write-back.
- **The yellow re-tone is var-deep only.** SPR-09 softened the design *tokens*
  (`apps/reading/src/design/tokens.css` + `tokens.ts`) and proved AA, but the
  Tailwind mirror (`apps/reading/tailwind.config.js`) still carries the loud
  hexes for ~56 utility consumers — a **disclosed follow-up**, not done here
  (out of SPR-09 scope). Tracked as **D17** in `engineering_deferrals.md`.
- **v2 is the build default; v1 is the wired rollback.** `VITE_ANTIEK_UI ?? "v2"`
  selects the v2 shell; `VITE_ANTIEK_UI=v1` + redeploy falls back to
  `apps/reading/src/AppLegacy.tsx`. Rollback is a flag flip, not a revert.

## Proof + what "live" was verified against

- **All 5 v1-failure regression anchors green**; the full `ams-real` experience +
  resilience suite is **37 passing (+1 operator-only `test.fixme`)**. The
  resilience matrix (`apps/reading/e2e/ams-v2-resilience-matrix.spec.ts`) covers
  reduced-motion / offline / no-Krea-key / multi-window degradation; the
  experience matrix (`apps/reading/e2e/ams-v2-experience-matrix.spec.ts`) covers
  the 9 visible-outcome criteria. CI on PR #49 was green honestly (Cloudflare
  Pages, axe-core, lostpixel, pytest, tsc) — nothing faked or downgraded.
- **Live on `antiek.ai`** (Cloudflare Pages, auto-from-`main`): verified by
  version marker — the served prod bundle hash changed `index-DEeTsWr9.js` →
  `index-CrI7TvA6.js` during the deploy window, and the new bundle contains the
  AMS2-unique string `"workflow in a window"` that is **absent from pre-#49 main**
  (`9aeb2c9`). The new v2 code is provably running.

## What was deliberately NOT done

- **No backend deploy.** AMS2's only backend change is a *comment* in
  `interfaces/research/api/krea_routes.py` — no behavior change — so the v2 shell
  runs identically against the current backend. The prod backend's deploy-lag of
  other sessions' accumulated `main` work is a **separate operator decision**,
  not bundled into this UI ship.
- **The pre-existing UI-redesign-track Storybook failures**
  (navigation-ia / flywheel / speak-publish) are **not AMS2 regressions** —
  verified failing identically at the `ebfb36a` baseline (the fairness check:
  confirmed before blaming AMS2). Flagged for the UI-redesign-track owner.

## Operator-discretion follow-ups

1. **Set `KREA_API_TOKEN` in prod** to enable live Krea generative art. The
   procedural floor ships fine without it (the routes return a typed-503
   graceful-absence), so this is optional polish, **not a gate** — that is why it
   is recorded here and not in `operator_gate_actions.md`.
2. **D17** — re-tone `apps/reading/tailwind.config.js` to mirror the softened
   vars (see `engineering_deferrals.md` D17).
3. **Backend deploy of accumulated non-AMS2 `main`** — operator's call, separate
   from this PR.

## Files (the on-repo record)

- `docs/ams-v2/mountain-shell-v2-verification.md` — the verification report
  (§1 verified-by-test, §2 NO-GO, §4 follow-ups, §5 ship+rollback, §6 anti-fiction).
- `docs/ams-v2/verified-interfaces.md` §11 — the as-built reconciliation.
- `docs/ams-v2/stream-spike.md` — the NO-GO record.
- `docs/ams-v2/e2e-harness.md`, `docs/ams-v2/spr-03-occlusion-audit.md` — supporting.
