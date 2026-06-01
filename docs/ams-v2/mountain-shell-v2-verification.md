# Antiek Mountain Shell v2 — Verification Report (SPR-10 capstone)

> **What this is.** The closing proof for the AMS-v2 corrective re-execution. v1
> shipped *green & invisible* (972 passing vitest tests, no mountain on screen)
> and *fiction persisted* (it cited interfaces that never existed and was never
> reconciled). This report ties every falsifiable success criterion to a passing
> **real-browser** assertion or an honestly-named operator-only gap, records the
> as-built reality, and documents ship + rollback — so neither v1 failure can
> recur.
>
> **Baseline:** branched from `origin/main` @ `ebfb36a`. **Integration branch:**
> `caffen/AMS2-integration`. Every sprint was built in an isolated worktree,
> adversarially critiqued, sharpened, and merged on green; the orchestrator
> independently re-ran each gate before merge.

---

## 1. Verified by test (real app, `VITE_ANTIEK_UI=v2`, no Krea key)

Every criterion below is a **passing Playwright assertion against the real Vite
app** on the real route (`loginAndGotoApp` mocks `/auth/me` at the network layer —
no app-code bypass; no Krea key — RULE 3). The consolidated proof lives in
`apps/reading/e2e/ams-v2-experience-matrix.spec.ts` (9 criteria) +
`apps/reading/e2e/ams-v2-resilience-matrix.spec.ts` (criterion #9); each row also
has a dedicated per-sprint gate. **Full `ams-real` suite: 37 passing, 1
operator-only skip** (re-run by the orchestrator at capstone time).

| # | Success criterion | Proven by | Merge |
|---|---|---|---|
| 1 | The moving mountain scene fills a non-trivial fraction of `/` (pixel-sampled, not "the component exists") | `experience-matrix criterion[mountain]` + `glass-surface.spec.ts` (with a live **negative control** proving the band is non-vacuous) + `ams-shell anchor[scene]` | SPR-03 `5e0f5c0` |
| 2 | Glass landings over the scene; an asset opens a transparent ad-bordered window | `criterion[glass]` + `glass-surface.spec.ts` + `windows-default.spec.ts` (house-fallback never blank) | SPR-03 / SPR-04 |
| 3 | A product click opens a window **by default** (no manual ⊞); ≥3 windows coexist over the scene | `criterion[windows]` + `windows-default.spec.ts` (3 proofs) + `ams-shell anchor[window]` | SPR-04 `dc6187e` |
| 4 | The penguin is alive: walk-cycle feet move, ≥4 emotes, **no white box**, waddles to a clicked/hotkeyed button | `criterion[penguin]` + `penguin.spec.ts` (feet pixel-diff falsified by a frozen-limb control; transparent PNGs alpha=0) + `ams-shell anchor[penguin]` | SPR-06 `834c456` |
| 5 | Uniform `⌘+key` (no vim chords), shown on the control + in a `⌘`-only HUD; user-assignable + persisted | `criterion[hotkeys]` + `hotkeys-command-scheme.spec.ts` (⌘E navigates, chord dead, HUD chord-free, custom survives reload) + `ams-shell anchor[hotkeys]` + no-chord grep guard | SPR-08 `693de2b` |
| 6 | The igloo home button shows a **visible "Home" caption** | `criterion[igloo]` + `navrail-labels.spec.ts` + `ams-shell anchor[igloo]` (assertLabeled requires a visible text node, not just aria-label) | SPR-07 `7bd7e7a` |
| 7 | The bold yellow softened to a weathered light; bottom-tab keeps its loud identity; AA holds | `criterion[yellow]` + `token-retone.spec.ts` (accent ≠ lemon, bar = `#F5DF24`, AA) + `tokens.contrast.test.ts` (12/12) | SPR-09 `af21f19` |
| 8 | Open, decluttered landscape; the "from the library" flanks no longer confuse; the ad slot never blanks | `criterion[open]` + `navrail-labels.spec.ts` + `HouseSlot.test.tsx` (single provenance, slot never blank) | SPR-07 `7bd7e7a` |
| 9 | **Never breaks**: offline / no-key / over-budget / reduced-motion all render a complete, legible app; the scene stays a visible backdrop; motion stills | `resilience-matrix` (reduced-motion frozen-but-painted + motion stilled; offline → procedural backdrop; no-key default; windows still open over the degraded scene) + `glass-reduced-motion.spec.ts` + `scene-living.spec.ts` | SPR-03 / SPR-05 |

The five v1 regression anchors (`scene` / `window` / `penguin` / `hotkeys` /
`igloo`) — encoded as red lights in `ams-shell.spec.ts` at SPR-01 — are **all
un-fixme'd and green**.

---

## 2. The generative stream — honest NO-GO (no fabricated figures)

SPR-02's feasibility spike (`docs/ams-v2/stream-spike.md`) returned, verbatim:

> **NO-GO** on a near-real-time *generative* stream. Doc-derived ceiling ~0.25
> generated fps (Flux ~4 s/image) against a ≥10 fps requirement; a poll-driven
> pseudo-stream at ~$0.60/min exhausts the 50-unit daily cap in ~3.3 minutes.

So **no streaming endpoint was built** (`interfaces/research/api/krea_routes.py`
keeps exactly three routes — `/krea/scene`, `/krea/generate`, `/krea/jobs/{id}` —
enforced by `test_krea_stream.py`), and **no `useSceneStream.ts` was created** (the
existing `SceneFetcher` type *is* the §4 frame-source seam; inventing a "stream"
hook on a NO-GO would itself be fiction). What ships is the **60 fps procedural
floor + periodic mood-gated Krea art**, measured in-browser: time-to-first-frame
~196 ms, sustained floor 60.1 fps (distinct Snow-canvas frames/sec — proven
clock-driven, not bare rAF, and falsified by a frozen-clock control). Live
generative fps / cost are recorded as **"not measured (no key)"**, never invented.

**Reversal condition (for a future sprint):** a named sub-second turbo model
benchmarked end-to-end at TTFGenF < 500 ms, ≥ 10 generated fps, ≤ ~$0.10/min at
the configured cap, attached at the `krea_routes.py` ~L411 adapter seam with a
real `KREA_API_TOKEN`.

---

## 3. Operator-only gaps (CI cannot close these — honestly named, not faked)

1. **Live Krea generative art.** Needs `KREA_API_TOKEN` in
   `/etc/antiek/secrets.env` + a backend restart. CI has no key by design, so the
   scene is proven *procedural-only*; the live-art layer (periodic crossfade over
   the floor) is exercised only when the operator supplies a key. The degradation
   path (no-key → procedural, never blank) **is** proven.
2. **Per-entity custom-hotkey OS-collision audit.** The assignable safe range +
   `detectConflict` (blocks reserved/owned combos) + persistence-survives-reload
   are unit- and browser-proven. Whether an operator-chosen `⌘`-combo collides
   with a *real browser/OS/extension* shortcut on the operator's actual machine
   cannot be tested in the sandbox (`experience-matrix criterion[hotkeys/custom]`
   is an intentional `test.fixme` recording this).

---

## 4. Honest gaps + carried-forward follow-ups (not regressions)

- **Pre-existing Storybook (chromium-project) failures — NOT caused by AMS2.**
  Six specs from the earlier UI-redesign sprint track fail on the integration
  branch: `navigation-ia.spec.ts` ×3, `speak-publish.spec.ts` ×2,
  `flywheel.spec.ts` ×1. **Verified pre-existing:** these exact six fail
  *identically* when built + run against `origin/main` @ `ebfb36a` (the AMS2
  baseline) — AMS2 edited none of these spec files and introduced **zero** new
  Storybook regressions. They are flagged here for the UI-redesign-track owner;
  they are out of scope for this shell re-execution and do not gate the v2 shell
  (whose own `ams-real` matrix is fully green).
- **Yellow re-tone is var-deep only (Tailwind mirror follow-up).** SPR-09 softened
  the CSS custom properties (`--sun-glow`, `--sun-hl-*`, `--sun-deep` → ~0.34
  chroma + a new `--sun-light` ramp) but, per its ownership boundary, did **not**
  touch `apps/reading/tailwind.config.js`, which still carries the loud
  `sun-deep: #B89A00` / `sun-glow: #FCE85E`. ~56 component consumers that resolve
  through Tailwind utilities (`text-sun-deep`, `bg-sun-glow`, `border-sun-deep`)
  therefore still render the loud hue on screen. To fully realize "softer chrome",
  a future sprint should re-tone the `tailwind.config.js` mirror to match
  (`sun-deep → #9C8636`, `sun-glow → #F1E08F` day), **keeping** `bg-sun` /
  `--bar-accent` loud (`#F5DF24`) and re-running the contrast + ams-real gates.
  No CI guard currently catches this var↔Tailwind divergence.
- **Minor deferred nits** (tracked in the spec ledger, none gating): SPR-08 binds
  `⌘G` (browser Find-Next, page-interceptable) to a Research sub-action — consider
  a punctuation key; the `SCENE_MARGIN_REGION` literal is reused across specs (now
  imported consistently) — a shared export would harden it; the `.artifacts/` test
  output dirs are gitignored.

---

## 5. Ship + rollback

- **Ship.** Merge `caffen/AMS2-integration` to `main`. The v2 shell is the build
  default (`apps/reading/src/main.tsx`: `VITE_ANTIEK_UI ?? "v2"`). Production needs
  no flag to get v2. Live Krea art additionally requires `KREA_API_TOKEN` (gap §3.1);
  without it the procedural floor ships and is fully functional.
- **Rollback.** Set `VITE_ANTIEK_UI=v1` in the production env and redeploy — the
  flag (already wired before AMS2, `main.tsx:25` → `AppLegacy.tsx`) renders the
  legacy shell. No code revert required. `.env.example` documents this.
- The v1 verification doc (`apps/reading/docs/mountain-shell-verification.md`) is
  left **untouched**; this v2 report is a sibling, not a replacement.

---

## 6. Anti-fiction ledger

`docs/ams-v2/verified-interfaces.md` is finalized (SPR-10 §11): every cited
interface resolves on the merged branch, reconciled to the as-built reality — the
key deltas being that `ResearchWorkstation` is `modes/ResearchWorkstation/index.tsx`
(not `ResearchWorkstation.tsx`), `useSceneStream.ts` was deliberately **not**
created, the hotkey bindings are `⌘O`/`⌘I` (vim chords removed), the stream is
NO-GO, and the yellow re-tone is var-deep. The v1 fictions (`#scene-root`,
`FloatingSurface`, `SubActionLauncher`) remain confirmed-absent and the ref-lint
(`tools/specs/verify_spec_refs.ts`) keeps that class of error mechanically
impossible. **Zero fictional interfaces survive.**
