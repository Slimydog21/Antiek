# Antiek Living Caliber — Verification & Activation Bundle (ALC SPR-09 capstone)

_Assembled 2026-06-14 on branch `caffen/ALC-SPR-09` (off `caffen/ALC-integration` @ `3263cc5d` = all 8 elevation sprints + the product-character remediation). **No live Krea call was made; no secret was handled; nothing was committed, pushed, or merged.** This is a docs-only capstone artifact._

This is the merge-readiness evidence bundle for the **Living Caliber** elevation — the spec
that lifted the living-background experience from a feature to a **graded done-bar** across
four craft dimensions. It does three things, in one document, so a reviewer never has to
reconstruct the story:

- **M6 — Evidence bundle** (below): every parity claim, artifact-linked, so a reviewer can
  verify any line in one click or one command.
- **M1 — Staged operator preflight checklist** ([§M1](#m1--staged-operator-live-activation-preflight)):
  the copy-paste-ready live-Krea activation, citing the
  [SPR-02 runbook](../../../../infrastructure/runbooks/krea.md) by section. The agent never
  touches the secret value.
- **M7 — PR-to-main draft** ([§M7](#m7--pr-to-main-draft-prcrouch-discipline)): the PR body the
  operator will use. **The operator merges; the agent does not open the PR.**

The honesty contract of this bundle is stated up front in
[§0 — What remains operator-gated / unverified](#0--what-remains-operator-gated--unverified):
the four caliber dimensions are graded on the **procedural / fallback floor** (which the rubric
grades first-class) plus the offline-verifiable surface. The spec's **thesis — "first real Krea
art on antiek.ai, billed and proven" — is NOT YET PROVEN.** It awaits the operator. Read §0 first.

---

## 0 — WHAT REMAINS OPERATOR-GATED / UNVERIFIED

**The thesis is not proven yet.** The Living Caliber spec set out to put the **first real Krea
art on antiek.ai, billed and proven**. As of this bundle, that has produced **no live
artifacts**:

- **No live smoke transcript** — `tools/krea_smoke.py` has never returned a live `200` from
  this codebase against a real `KREA_API_TOKEN`. ([smoke tool](../../../../tools/krea_smoke.py);
  [runbook §4](../../../../infrastructure/runbooks/krea.md))
- **No browser fallback→live crossfade capture** — the live-art crossfade *in motion* (the one
  thing that needs a real key to observe) has not been recorded.
- **No dashboard balance / decrement reading** — no "before" balance screenshot, no observed
  ~1-unit (≈$0.007) decrement, no de-bill (`cached:true`) confirmation against a live balance.
- **No cost envelope** — the real per-session / monthly $ envelope is unmeasured; the projection
  in [mountain-shell-verification.md](../mountain-shell-verification.md) ("a few cents/day,
  hard-capped") is an assumption awaiting operator sign-off.

**Plainly: the live-art-active confirmation is the one gate only the operator can close.** The
four caliber dimensions below are graded on the **procedural / fallback floor** — which the
[PostHog craft rubric](../../../../docs/parity/posthog-craft-rubric.md) grades as **first-class,
not a degradation** — plus the offline-verifiable surface (tokens, focus rings, motion guards,
Storybook state-authorship, the 60fps trace under simulated load). Everything that *can* be
verified without a key has been; the live-art-active layer is recorded as **awaiting operator
activation** and does **not** prop up any grade.

The activation path is fully staged — see [§M1](#m1--staged-operator-live-activation-preflight).

---

## M6 — EVIDENCE BUNDLE

### Status: all four caliber dimensions MEET the gate (offline/fallback floor) — live-art-active confirmation pending operator

Every dimension is **≥ target** (grade 3, OR grade 2 with a single named, justified exception
recorded in the [final audit](../../../../docs/parity/audit-final-2026-06-13.md)), every
dimension is **≥ its 2026-06-12 baseline**, and **nothing regressed** when the eight sprints
combined. The verdict and every count below were re-resolved on the integrated tree @ `3263cc5d`
(plus the additive product-character remediation) by an **independent capstone audit** that
graded the integrated surface *before* reading the per-sprint audits, hunting adversarially for a
combine-regression or an inflated grade.

### 6.1 — Parity delta table (baseline-2026-06-12 → final)

Source of truth: [`docs/parity/audit-final-2026-06-13.md`](../../../../docs/parity/audit-final-2026-06-13.md)
(headline verdict + corrected delta table + gate-clause verdict + per-dimension findings +
stability cross-check). Supporting artifacts, each one click away:
[baseline-2026-06-12.md](../../../../docs/parity/baseline-2026-06-12.md) ·
[baseline-stability-check.md](../../../../docs/parity/baseline-stability-check.md) ·
[posthog-craft-rubric.md](../../../../docs/parity/posthog-craft-rubric.md) ·
[audit-spr05](../../../../docs/parity/audit-spr05-2026-06-13.md) ·
[audit-spr06](../../../../docs/parity/audit-spr06-2026-06-13.md) ·
[audit-spr07](../../../../docs/parity/audit-spr07-2026-06-13.md) ·
[audit-spr08](../../../../docs/parity/audit-spr08-2026-06-13.md).

| Dimension | Baseline 2026-06-12 | Final 2026-06-13 (integrated) | Gate? | Owning sprint |
|---|---|---|---|---|
| **Visual crispness** | 1 | **2\*** | MEETS — 2 + named **Werner-2** exception (mascot, no interactive control to refine); shell floor lifted 1→3 | SPR-08 |
| **Motion & life** | 3 (Run-A) / 2 (Run-B) | **3** | MEETS — target; the strongest dimension, no combine-regression | SPR-06 |
| **Product character** | 1 | **3** | MEETS — **+2 over baseline; a clean 3 on EVERY in-scope surface** (Reading-mode 3, Shell 3, Scene 3, Werner 3\*, Fallback 3 — co-location 100% on reading-mode/shell/scene; the two last-floor surfaces, Scene's stateful KreaArtLayer+SceneStatusBadge and the Shell's SceneChrome, are now storied; co-location<85% exc. RESOLVED 2026-06-14) | SPR-07 (+ remediation + capstone polish + scene/shell pass) |
| **Evidence-backed craft** | 2 | **2\*** | MEETS — 2 + named **RAIL-A** exceptions (single-theme / non-blocking / flagship-excluded) | SPR-09 |

\* = a grade whose floor is a **named, justified exception** recorded in the audit (see
[§6.4](#64--named-justified-exceptions-each-honest-each-with-its-recovery-path)). Roll-up rule
(same one the baseline and every per-sprint audit used): **lowest in-scope surface**, not the
average — the no-regression gate is per-surface, so an honest dimension reports its floor.

**Product character — the honest history.** The 2026-06-13 capstone first graded product
character **1/3 — a MISS**: the reading-mode floor tripped the rubric's verbatim level-1 absence
anchor ("exactly 1 named story for a component with ≥2 meaningful states") on
`ResearchThis.stories.tsx` (1 story / ≥3 states) and `VoiceNote.stories.tsx` (1 story / ≥6
states). The capstone refused to ship a missed bar with an asterisk and looped SPR-07. A
**scoped, additive remediation** then authored named, co-located Storybook stories for four
reading-mode stateful surfaces (ResearchThis 1→4, VoiceNote 1→7, new PersonalSpace 4, new
MetaReading 4), each driving the **real** component reducer through a Storybook-only `fetch`/mic
stub — not hollow renders. That cleared the L1 anchor on every in-scope reading component and
lifted the dimension to an honest **2\*** (capped at 2 because co-location was then **58%**). A
**capstone-polish pass (2026-06-14)** then authored co-located named-state stories for the five
remaining reading-mode components — `ArxivFrame.stories.tsx` (4), `Attribution.stories.tsx` (5),
`ReadingCompanion.stories.tsx` (3), `TalkToBook.stories.tsx` (6), and the Reading shell
`index.stories.tsx` (7, the shell's OWN top-level loading / not-found / error / preview-only /
removed / read-on-arXiv states — it is a real composition root with own-states, **not**
document-excluded) — taking reading-mode co-location to **100% (12/12 ≥ the L3 85% bar)**.
Finally a **scene/shell pass (2026-06-14)** closed the two surfaces that were still the dimension
floor: the Shell's last un-storied control-bearing component (`SceneChrome.stories.tsx`, 6) took
shell control-bearing co-location **5/6 → 6/6 = 100%**; and the Scene's two STATEFUL components
were storied — `KreaArtLayer.stories.tsx` (3: `LiveArtFront`/`MidCrossfade`/`FallbackRendersNothing`,
driving the REAL `crossfadeReduce` two-slot machine over `SceneArt` fixtures, `frozen`, **no live
Krea call**) and `SceneStatusBadge.stories.tsx` (3: `OperatorFallbackWithReason`/`OperatorLiveNull`/
`NonOperatorAbsent`, driving the auth×fallback 3-state matrix through the real `AuthCtx.Provider`) —
which, with the 6 visual layers + the `Scene` composite already storied, took scene co-location
**7/9 → 9/9 = 100%** (no L0/L1 scene component remains). **Product character is now a clean 3 on
EVERY in-scope surface** — Reading-mode 3, Shell 3, Scene 3, Werner 3\*, Fallback 3 — so the
**dimension floor is 3**; the co-location<85% exception is **RESOLVED**, not deferred, and the
prior Scene/Shell 2-floor is **RESOLVED** by storying their last un-storied components. The only
`*` still carried under product character is Werner's daypart-standing-art gap (operator+Krea art,
recorded not faked), which rolls up to 3. The full re-grade is the
[final audit's capstone-polish addendum](../../../../docs/parity/audit-final-2026-06-13.md)
(ADDENDUM 2, top of file); the pre-remediation MISS is preserved verbatim in the body below, so
the before-photo stays honest.

**Stability cross-check.** The integrated grades agree within ±1 with the four per-sprint audits
on three of four dimensions; the one flagged divergence (SPR-07 self-graded product character 3
vs the integrated 1, pre-remediation — a 2-level gap on identical code) is recorded as a
**rubric-anchor looseness**, resolved in favor of the rubric's literal Storybook-co-location
criterion, then closed by the remediation. Details:
[audit §STABILITY](../../../../docs/parity/audit-final-2026-06-13.md).

### 6.2 — What each elevation sprint shipped (merge SHAs)

One line each. Every SHA below resolves to a real commit on `caffen/ALC-integration`
(`git log -1 <sha>` — verified 2026-06-14).

| Sprint | Merge SHA | What it shipped |
|---|---|---|
| SPR-01 | `69e05dd` | Krea proxy honesty-vocabulary headers + secret-leak guard doc (the `id:secret` shape, the leak-proof smoke). |
| SPR-02 | `16ff381` | Krea substrate: proxy + daily budget + rate limit + kill-switch + typed-503 offline fallback; the [SPR-02 runbook](../../../../infrastructure/runbooks/krea.md) (rotation/funding/wiring/smoke) the M1 checklist cites. |
| SPR-03 | `62ee025d` | The parity harness: [PostHog craft rubric](../../../../docs/parity/posthog-craft-rubric.md) + graded auditor + the honest [2026-06-12 baseline](../../../../docs/parity/baseline-2026-06-12.md). |
| SPR-04 | `3666e266` | Fallback observability: `GET /krea/status` (`key_present` BOOLEAN — never token bytes — kill-switch state, budget cap), the failure ring, WARNING logs, operator badge; the **503 diagnostic ladder** the M1 smoke walks (the smoke's `DECISION_TABLE`, [krea_smoke.py:80-149](../../../../tools/krea_smoke.py)). |
| SPR-05 | `50ef7b6a` | Scene visual crispness: elevated the procedural floor to a first-class winter mountain (scene 3/3). [audit-spr05](../../../../docs/parity/audit-spr05-2026-06-13.md). |
| SPR-06 | `658b5131` | Motion & life: continuous drift, interruptible crossfades, parallax breath; **60fps proven under 4x throttle** ([trace below](#63--the-60fps-trace-spr-06)). [audit-spr06](../../../../docs/parity/audit-spr06-2026-06-13.md). |
| SPR-07 | `db0f8556` | Product character: scene-reactive Werner mascot + deterministic delight moments + §5 system-state copy (loading/empty/error live regions). [audit-spr07](../../../../docs/parity/audit-spr07-2026-06-13.md). |
| SPR-08 | `3263cc5d` | Shell crispness: killed the F-1 z-stacking risk, tokenized the glass, every control every state (`feel-focusable` dual-tone focus ring across all 6 control-bearing shell components); repaired the inherited SPR-07 `build-storybook` break. [audit-spr08](../../../../docs/parity/audit-spr08-2026-06-13.md). |

(The integration tip `3263cc5d` is SPR-08's merge commit; the product-character remediation +
capstone-polish pass are additive working-tree changes on top — `*.stories.tsx` (the 4 from the
first remediation + the 5 from the capstone polish: ArxivFrame/Attribution/ReadingCompanion/
TalkToBook/index-shell) + a Storybook-only `storyFetch.tsx` + the audit addenda, **no
runtime/prod source touched**.)

### 6.3 — The 60fps trace (SPR-06)

Artifact: [`apps/reading/e2e/_ams/.artifacts/scene-perf-4x-throttle.json`](../../e2e/_ams/.artifacts/scene-perf-4x-throttle.json).

Captured 2026-06-13 under a **4x CPU throttle** (the deliberately hostile condition), with the
full composition live — `appshell + project-tree dock + active parallax drift + live krea
crossfade in-flight`:

| Metric | Value | Budget |
|---|---|---|
| p50 frame time | **16.7 ms** | ≤ 16.7 ms (60fps) |
| p95 frame time | **33.4 ms** | within window under 4x throttle |
| max frame time | 50 ms | — |
| **longFrames** | **0** | 0 |
| longTasks | 0 | 0 (longTask API supported) |
| frames sampled | 97 | — |

The crossfade is **in-window** (the crossfade composition was live during the capture and
produced zero long frames). This is the offline-verifiable motion proof; the live-art crossfade
*as a user sees it with a real key* is the operator-gated confirmation (see §0).

### 6.4 — Named justified exceptions (each honest, each with its recovery path)

These are the exceptions that let the dimensions clear the gate at `2*` rather than 3. Each is
recorded in the [final audit](../../../../docs/parity/audit-final-2026-06-13.md), not papered
over.

1. **Werner daypart-standing-art gap** (`POSE_GAPS`,
   [`src/brand/wernerSceneMap.ts:96`](../../src/brand/wernerSceneMap.ts)). There is **no
   daypart-distinct standing-pose art** — the resting pose is `idle` both day and night
   (6 honest gaps recorded). What a user *can* observe today is the **transition moment** (the
   one-shot `thinking`/`celebrate` flash on the day↔night flip), not a standing day-vs-night
   resting pose. **Recovery path:** an operator + Krea art session authors the bespoke daypart
   poses. This is the named exception that lets Werner clear visual crispness at 2\* (a mascot
   exposes no interactive `:focus-visible` control to refine to the L3 bar) and product
   character at 3\*.

2. **~~Product character capped at 2\*, not 3 — co-location 58% < 85%.~~ RESOLVED 2026-06-14
   (capstone polish).** The previously-un-storied stateful surfaces —
   [`TalkToBook.tsx`](../../src/modes/Reading/TalkToBook.tsx),
   [`ArxivFrame.tsx`](../../src/modes/Reading/ArxivFrame.tsx),
   [`ReadingCompanion.tsx`](../../src/modes/Reading/ReadingCompanion.tsx),
   [`Attribution.tsx`](../../src/modes/Reading/Attribution.tsx), and the Reading shell
   [`index.tsx`](../../src/modes/Reading/index.tsx) — now each ship a co-located `*.stories.tsx`
   that authors their non-default states (loading / empty / error / each variant / each tier) as
   distinct named stories driving the **real** component code path. **Reading-mode co-location is
   now 100% (12/12 ≥ the L3 85% bar)** and reading-mode product character is a **clean 3**. The
   shell `index.tsx` was storied (not document-excluded) because it authors genuine top-level
   own-states — `Opening` / `NotFound` / `Error` / `PreviewOnly` / `Removed` / `ReadOnArxiv` plus
   the resolved `HostedBody` (`index.tsx:270-285,368-406`). **The earlier Scene/Shell 2-floor is
   ALSO RESOLVED (2026-06-14, scene/shell pass):** the Shell's last un-storied control-bearing
   component now ships [`SceneChrome.stories.tsx`](../../src/shell/SceneChrome.stories.tsx) (6),
   taking shell control-bearing co-location **5/6 → 6/6 = 100%**; and the Scene's two STATEFUL
   components now ship co-located stories —
   [`KreaArtLayer.stories.tsx`](../../src/scene/layers/KreaArtLayer.stories.tsx) (3:
   `LiveArtFront`/`MidCrossfade`/`FallbackRendersNothing`, driving the REAL `crossfadeReduce`
   two-slot machine over `SceneArt` fixtures, `frozen`, **no live Krea call**) and
   [`SceneStatusBadge.stories.tsx`](../../src/scene/SceneStatusBadge.stories.tsx) (3:
   `OperatorFallbackWithReason`/`OperatorLiveNull`/`NonOperatorAbsent`, driving the documented
   auth×fallback 3-state matrix through the real `AuthCtx.Provider`) — which, with the 6 visual
   layers + the `Scene` composite already storied, takes scene co-location **7/9 → 9/9 = 100%**
   (no L0/L1 scene component remains). **Product character is now a clean 3 on every in-scope
   surface — Reading-mode 3, Shell 3, Scene 3, Werner 3\*, Fallback 3 — dimension floor 3.** The
   only `*` still carried under product character is Werner's daypart-art gap (#1 above), which
   rolls up to 3.

3. **Evidence-craft RAIL-A** — Lost-Pixel image-snapshot rail is **present-but-weak**. 381
   committed baselines, but: (a) **effectively single-theme** (only 3 of 381 carry a dark/night
   variant); (b) **flagship excluded** — `lostpixel.config.ts:51-53` skips
   `workspace-demo--scene` (framer-motion spring nondeterminism), so the living-scene centerpiece
   is not pixel-gated; (c) **INFORMATIONAL (non-blocking) in CI** — `visualtest.yml:60` runs
   `npx lost-pixel || echo "::warning…"`. **Clean-3 path:** dual-theme baselines + blocking CI +
   flagship included. (The flagship is still enforced behaviorally via
   `glass-reduced-motion.spec.ts` + the motion-guard ratchet — it is excluded from the *pixel*
   rail, not from enforcement.)

4. **Lost-Pixel shell baseline RE-MINT — deferred to the operator's canonical CI/reference
   rendering env.** The committed corpus is stale + this-host-mismatched; re-minting it on a dev
   Mac would be a **fake green** (a baseline minted on the wrong renderer certifies nothing). The
   re-mint belongs in the operator's reference rendering environment, where it can be
   dashboard-approved.

5. **`STORYBOOK_DISABLE_TELEMETRY=1` needed for non-interactive build (CI env note).** A
   headless / non-interactive `build-storybook` or `visualtest` run should set
   `STORYBOOK_DISABLE_TELEMETRY=1` so the Storybook telemetry prompt never blocks the build. This
   bundle's own verification run used it (see [§6.5](#65--ci--build-status-offline-gates)). Wire
   it as a CI env var on the visual-test job.

6. **Live-art-active confirmation awaits operator (SPR-09 M2/M3).** No live Krea token in this
   environment; the live-art crossfade in motion is unobservable here. The procedural/fallback
   floor (graded first-class) IS observable and complete. See [§0](#0--what-remains-operator-gated--unverified)
   and [§M1](#m1--staged-operator-live-activation-preflight).

### 6.5 — CI / build status (offline gates)

| Gate | Command | Result |
|---|---|---|
| build-storybook | `STORYBOOK_DISABLE_TELEMETRY=1 npm run build-storybook` | **PASS — exit 0**, built in ~12s (re-run 2026-06-14 after the capstone-polish stories landed) |
| Reading-mode stories indexed | `storybook-static/index.json` | **52** `src/modes/Reading/` story entries present (the 25 new capstone-polish stories — ArxivFrame 4, Attribution 5, ReadingCompanion 3, TalkToBook 6, BookReader-shell 7 — all indexed), **no "Unable to index"** |
| Reading-mode co-location | components-with-co-located-story / in-scope components | **12/12 = 100%** (≥ the L3 85% bar) |
| copyLint | `npx vitest run src/shared/copyLint.test.ts` | zero NEW banned patterns from this pass (only failures = pre-existing `src/modes/Notebook/index.tsx:106,110` `block_id` leak, not in any reading-mode file) |
| TS strict | `npx tsc -b` | exit 0 (re-run 2026-06-14) |
| Reading-mode vitest | `npx vitest run src/modes/Reading` | 11 files / 98 tests passed (re-run 2026-06-14) |
| design/scene/shell/werner vitest | feel-focus 22, motion+werner 33 | green (per final audit, 2026-06-13) |

**Operator/CI-env gates (NOT green-in-sandbox, by honesty):** Lost-Pixel visual regression
(re-mint deferred, see exception 4); Playwright real-browser e2e + device FPS (no compositor in
the sandbox); axe a11y CI step (the hook *blocks* on serious/critical, but the CI wiring is
informational — and was already informational at the baseline SHA, so it is **not** a
combine-regression); and the entire **live-Krea** layer (§0).

---

## M1 — STAGED OPERATOR LIVE-ACTIVATION PREFLIGHT

This is the **copy-paste-ready** live-Krea activation. It follows
[`infrastructure/runbooks/krea.md`](../../../../infrastructure/runbooks/krea.md) by section. **The
agent never handles the secret value** — the steps marked **OPERATOR** involve the token or the
billing account; the steps marked **AGENT-VERIFIABLE** are non-secret and an agent can run them.

**Each step is a ≤2-minute copy-paste.** Work local first, then prod.

> Runbook fidelity note: every command below is transcribed from the cited runbook section. If a
> runbook command has drifted from the tree, the runbook is the bug to fix first — these steps
> were checked against `krea.md` on 2026-06-14 and matched.

### STEP 0 — ROTATE the leaked key — **OPERATOR** (runbook §5; §1 to mint)

A previously-used key leaked in plaintext into a spec-run ledger on 2026-06-12 (redacted same
day; **rotation still pending**). This is preflight step zero.

1. Mint a fresh token at <https://www.krea.ai/settings/api-tokens> (toggle to the correct
   **workspace** first; name it datewise, e.g. `antiek-prod-2026-06`). — runbook §1.
2. Do **not** revoke the old key yet — revoke it in **STEP 4** *after* the new key is verified
   working (a leaked Krea key has no uptime reason to keep, but revoke-after-verify avoids a
   blind window). Copy the new value once, straight into STEP 2's wiring, and nowhere else
   (never a chat / ledger / commit / transcribed command line — that exact move caused the leak).
   — runbook §5 steps 1, 5.

### STEP 1 — FUND + confirm the SEPARATE prepaid API balance — **OPERATOR** (runbook §2)

The API bills from a **prepaid USD balance separate from any web subscription's compute units.**
An empty balance answers HTTP 402 on every call — now legible as the typed `no_api_balance`
reason. A Pro/Max plan does **not** fix a 402.

1. Top up at <https://www.krea.ai/app/api> ($5 minimum; presets $10/$25/$50/$100). For first
   contact $5–$10 is plenty — the default `bfl/flux-1-dev` model is $0.007/request, so the full
   default daily cap (50 units) burns ~$0.35/day; $5 survives ≥14 maxed-out days. — runbook §2, §7.
2. **Screenshot the balance number now** — this is the billing **"before"** reading STEP 4
   reconciles against.

### STEP 2 — WIRE the token — **OPERATOR** (runbook §3; editor-based by design)

The secret never hits a command line / transcript — it goes in via an editor.

**Local (dev Mac):** append to `~/Desktop/Antiek/.env` (gitignored; nothing auto-loads it):

```
KREA_API_TOKEN=<paste-token-here>
```

Then source it into the shell that starts the server:

```bash
cd ~/Desktop/Antiek
set -a; source .env; set +a
```

**Prod (Hetzner VM):** edit via `sudoedit` (editor-based — the value never reaches a transcribed
command), then restart so systemd re-reads `EnvironmentFile` at unit start:

```bash
ssh -i ~/.ssh/antiek_ed25519 root@<vm-ip>
# Before assuming, check the live file — prints a COUNT, never the value (runbook §3 step 0):
grep -c '^KREA_API_TOKEN=.' /etc/antiek/secrets.env   # 0 → wire below; 1 → you are ROTATING (still fine, replace it)
sudoedit /etc/antiek/secrets.env                       # fill the KREA_API_TOKEN= line
systemctl restart antiek
sleep 2
systemctl is-active antiek                              # expect: active
```

Leave the optional knobs (`KREA_KILL_SWITCH`, `KREA_DAILY_UNIT_CAP`, …) commented unless STEP 4
or runbook §6/§7 gives a reason.

### STEP 3 — VERIFY the wiring — **AGENT-VERIFIABLE** (non-secret; runbook §4 plumbing)

`GET /krea/status` reads `key_present` as a **BOOLEAN** (never token bytes —
[`krea_routes.py:1310,1328-1329`](../../../../infrastructure/runbooks/krea.md)), plus the
kill-switch state and the budget cap. An agent can run this — it prints no secret.

**Local:**

```bash
curl -s http://127.0.0.1:8000/krea/status | python3 -m json.tool
# expect: "key_present": true, "enabled": true, kill-switch off, budget cap as configured
```

**Prod (on-box; bearer via command substitution — nothing echoed):**

```bash
ssh -i ~/.ssh/antiek_ed25519 root@<vm-ip>
export ANTIEK_OPERATOR_TOKEN="$(grep -m1 '^ANTIEK_OPERATOR_TOKEN=' /etc/antiek/secrets.env | cut -d= -f2-)"
curl -s -H "Authorization: Bearer $ANTIEK_OPERATOR_TOKEN" https://api.antiek.ai/krea/status | python3 -m json.tool
```

### STEP 4 — SMOKE the capped first contact — **OPERATOR runs; AGENT reads the output** (runbook §4)

Run [`tools/krea_smoke.py`](../../../../tools/krea_smoke.py) with `KREA_DAILY_UNIT_CAP=3` (worst
case 3 × $0.007 ≈ $0.02). It is **secret-safe by construction** — it never reads the token,
strips query strings from printed URLs, and proves both via `tests/test_krea_smoke.py`. It calls
`GET /krea/scene` twice with an identical scene-state.

**Local:**

```bash
cd ~/Desktop/Antiek
set -a; source .env; set +a              # loads the token for the server, silently
./.venv/bin/python tools/krea_smoke.py --serve   # --serve forces KREA_DAILY_UNIT_CAP=3 into its own server
```

**Prod (on-box):**

```bash
ssh -i ~/.ssh/antiek_ed25519 root@<vm-ip>
export ANTIEK_OPERATOR_TOKEN="$(grep -m1 '^ANTIEK_OPERATOR_TOKEN=' /etc/antiek/secrets.env | cut -d= -f2-)"
cd /opt/antiek && python3 tools/krea_smoke.py --base-url https://api.antiek.ai
```

Read the exit code and the printed result:

- **Exit 0 (live art verified):** the first call returned `200`; **verify the printed image URL
  fetches**; the **2nd identical call returned `cached:true`** (the de-bill proof — an identical
  scene-state must never re-bill); then **close the loop at the dashboard** —
  <https://www.krea.ai/app/api> should show the balance decremented by **≈1 unit (≈$0.007)** vs
  the STEP 1 "before" screenshot.
- **Exit 3 (typed 503 fallback):** generation is disabled — **walk SPR-04's diagnostic ladder**
  (the smoke's printed `DECISION_TABLE` row, [krea_smoke.py:80-149](../../../../tools/krea_smoke.py)).
  Most likely rows: `no_api_balance` → top up (STEP 1, a 402 is money not the key);
  `no_key` → re-check STEP 2 wiring + restart; `kill_switch` → an appended panic line; `upstream_error`
  401 → the token is wrong/revoked, rotate (STEP 0).
- **Exit 1** (the repeat re-billed) or **Exit 2** (transport/auth) → bug; read the decision-table
  row and the server logs (`journalctl -u antiek`).

### STEP 5 — The inherited 5-step browser checklist + cost envelope — **OPERATOR** (real browser)

Run the live-Krea browser checklist from
[mountain-shell-verification.md → "Operator live-Krea checklist"](../mountain-shell-verification.md):

1. Load the app with the key set.
2. Toggle OS light↔dark; confirm the **sky art refreshes on mood change (and only then)**,
   crossfading over the procedural sky.
3. Confirm procedural snow/clouds/penguin still read **on top** of the art.
4. Drive usage to the daily cap; confirm a clean **fall back to procedural** (no errors, no
   blank) and that the kill-switch forces fallback.
5. Confirm the **real monthly $ envelope** matches expectations and **sign off** — this is the
   cost-envelope reading §0 lists as currently unmeasured.

**Emergency stop, if anything runs away:** kill-switch FIRST (runbook §6) —
`printf '\nKREA_KILL_SWITCH=1\n' >> /etc/antiek/secrets.env && systemctl restart antiek`, then
revoke the key upstream.

---

## M7 — PR-TO-MAIN DRAFT (PRcrouch discipline)

> **This is a DRAFT for the operator to use. The agent did NOT open this PR.** The operator
> creates and merges the PR; the agent's job was to make it approvable. Base: `Slimydog21/Antiek`
> `main`. Head: `caffen/ALC-integration`.

---

**Title:** Antiek Living Caliber — elevate the living background to a graded done-bar (8 sprints + capstone)

**Summary**

This PR lands the **Living Caliber** elevation: the living-background experience graded to a
**done-bar across four craft dimensions** measured against an independently-built PostHog craft
rubric. It contains all 8 elevation sprints plus the SPR-09 non-live capstone deliverables.

**What it contains**

- **SPR-01..08** (merge SHAs `69e05dd`, `16ff381`, `62ee025d`, `3666e266`, `50ef7b6a`,
  `658b5131`, `db0f8556`, `3263cc5d`): the Krea proxy + budget/kill-switch/typed-503 fallback
  substrate; the parity harness (rubric + graded auditor + honest baseline); `/krea/status`
  fallback observability + the 503 diagnostic ladder; the first-class procedural winter-mountain
  scene; continuous-drift / interruptible-crossfade motion with a 60fps proof; the scene-reactive
  Werner mascot + §5 system-state copy; and the shell-crispness pass (tokenized glass, dual-tone
  `feel-focusable` focus ring on every control, F-1 z-stacking killed, `build-storybook`
  repaired).
- **Capstone (SPR-09, non-live):** the evidence bundle
  `apps/reading/docs/ams-v2/living-caliber-verification.md` (this doc) + the product-character
  remediation (additive Storybook stories — no runtime source touched) + the final parity audit
  `docs/parity/audit-final-2026-06-13.md`.

**Parity verdict — all four dimensions MEET the gate** (on the procedural/fallback floor, which
the rubric grades first-class), each ≥ baseline, nothing regressed:

| Dimension | Baseline → Final | Gate |
|---|---|---|
| Visual crispness | 1 → 2\* | MEETS (named Werner-mascot exception) |
| Motion & life | 3 → 3 | MEETS (target) |
| Product character | 1 → **3** | MEETS (+2 lift; a **clean 3** on every in-scope surface — Reading-mode/Shell/Scene co-location all 100%, KreaArtLayer+SceneStatusBadge+SceneChrome now storied; co-location<85% exception RESOLVED; dimension floor 3) |
| Evidence-backed craft | 2 → 2\* | MEETS (named RAIL-A exceptions) |

Full evidence, every claim artifact-linked: `apps/reading/docs/ams-v2/living-caliber-verification.md`.

**Honest note — live activation still pending.** The spec's thesis — *first real Krea art on
antiek.ai, billed and proven* — is **NOT yet proven**. No live smoke transcript, no live
crossfade capture, no dashboard decrement, no measured cost envelope exists. The four dimensions
are graded on the procedural/fallback floor + the offline-verifiable surface. The live-art-active
confirmation is the one gate only the operator can close; the full copy-paste activation is staged
in this PR's evidence bundle (§M1).

**CI status**

- **Offline gates GREEN:** `build-storybook` (exit 0, with `STORYBOOK_DISABLE_TELEMETRY=1` for
  non-interactive runs), `tsc -b`, the design/scene/shell/werner + reading-mode vitest suites,
  the motion-guard ratchet, the backend Krea pytest.
- **Operator/CI-env items (not green-in-sandbox, by honesty):** Lost-Pixel visual regression —
  the baseline **re-mint is deferred to the operator's canonical reference rendering env**
  (re-minting on a dev Mac would be a fake green); Playwright real-browser e2e + device FPS; the
  axe CI step is informational (the hook blocks; the wiring was already informational at the
  baseline SHA — not a regression introduced here); and the **live-Krea** layer above.

**What you (operator) are approving**

1. Merging all 8 Living Caliber sprints + the capstone docs to `main`.
2. Acknowledging the named justified exceptions (Werner daypart art; RAIL-A
   single-theme/non-blocking/flagship-excluded; Lost-Pixel re-mint deferred) as recorded, not
   faked. (The product-character "co-location <85%" exception is now **RESOLVED on every surface** —
   reading-mode, shell, and scene co-location are all 100%; product character is a **clean 3** with
   the dimension floor at 3. The only `*` carried under product character is Werner's daypart-art
   gap, which rolls up to 3.)
3. That the **live-art-active confirmation remains yours to close** post-merge via the §M1
   checklist — merging this PR does **not** assert the thesis is proven; it lands the verified
   floor and stages the activation.

_The operator merges; the agent does not._

---

## Provenance

- Branch: `caffen/ALC-SPR-09` off `caffen/ALC-integration` @ `3263cc5d`.
- No live Krea call; no secret handled; no commit/push/merge performed by the agent.
- Every link in this bundle was resolved on disk on 2026-06-14; the runbook sections cited exist
  in [`infrastructure/runbooks/krea.md`](../../../../infrastructure/runbooks/krea.md);
  `build-storybook` was re-run green (exit 0) for §6.5.
