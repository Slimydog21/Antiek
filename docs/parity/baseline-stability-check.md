# Baseline stability check — ALC SPR-03

**Purpose:** Two independent baseline auditors graded the *same unchanged* Antiek
main tree (branch `caffen/ALC-SPR-03`, HEAD `16ff381d8ee4bad6c4f858e0d696fa7ae8140643`).
This check tests whether the parity rubric is sharp enough that two cold readers
land within tolerance of each other — i.e. that the rubric *discriminates* rather
than leaving grades to auditor taste.

**Tolerance rule:** every dimension must agree within **+/-1 grade** (`|runA - runB| <= 1`).
If ANY dimension's delta `> 1`, the rubric anchors for that dimension are too loose
to discriminate, the verdict is **FAIL**, and the defect is routed to a sharpen
round — the rubric is tightened, **NOT** the code.

## Runs compared

- **Run A:** `docs/parity/baseline-2026-06-12.md` — "run 1 — INDEPENDENT baseline (run A). No other baseline report read."
- **Run B:** `docs/parity/.baseline-runB.md` — "independent baseline (run B) — graded cold, no other auditor report seen"

Both auditors graded the identical tree with the identical rubric version
(PostHog SHA `9c06e96956f68b6cd67e39e30df8ff736e1fcaad`).

## Side-by-side grades and deltas

| Dimension | Run A | Run B | Delta `|A-B|` | Within +/-1? |
|---|---|---|---|---|
| Crispness (Visual crispness) | 1 | 2 | 1 | yes |
| Motion (Motion & life) | 3 | 2 | 1 | yes |
| Character (Product character) | 1 | 1 | 0 | yes |
| Evidence-craft (Evidence-backed craft) | 2 | 2 | 0 | yes |

**Max delta:** 1. **Dimensions exceeding +/-1:** none.

## Verdict

**PASS.**

Every dimension agrees within the +/-1 tolerance. Two cold, independent auditors
reading the same unchanged tree with the same rubric never diverged by more than
one grade on any dimension, and agreed exactly on the grade for character and
evidence-craft. **Caveat (important — grade-agreement is not fact-agreement):**
on evidence-craft the two runs ORIGINALLY agreed on the *grade* (both 2) for
OPPOSITE reasons — Run A asserted RAIL A (image-snapshot visual regression) was
*entirely absent* (0 committed PNG snapshots) and capped at 2 on that absence;
Run B found RAIL A *present but weak* (381 committed Lost-Pixel baselines, single-
theme, flagship-excluded, non-blocking in CI) and capped at 2 on that weakness.
Same number, contradictory underlying fact. The numeric +/-1 verdict therefore
PASSES, but evidence-craft is NOT a clean example of auditor agreement — see the
seam note below. The BLOCKING sharpen fix has since reconciled the RAIL-A fact
across both runs (both now read present-but-weak), and the grade stayed 2 in both.
The rubric discriminates well enough on the *grades* to serve as a parity baseline;
no sharpen round is triggered by the numeric check.

## Notes on the soft seams (recorded for the record)

Two seams are 1-grade disagreements *within* tolerance (crispness, motion); a third
seam (evidence-craft) is a same-grade / opposite-fact divergence that the numeric
delta cannot see. None fails the check, but all three are worth logging in case a
future run drifts — and the evidence-craft seam is the reason grade-delta alone is
an insufficient stability signal:

- **Crispness (A=1, B=2):** Both auditors found the identical evidence — the
  `.feel-focusable` bundle is built but has zero in-scope consumers, and
  `ProductsLauncher` uses bare `:focus` not `:focus-visible`. They diverged on
  whether the *per-control* `:focus-visible` ring on `NavRail` is enough to clear
  the L1 floor. Run A applied the rubric's "bundle exists but controls don't use it
  = 1" caveat to the whole surface; Run B credited NavRail's inline ring as clearing
  the bare-`:focus` L1 symptom (-> 2). The anchor that admits both readings is the
  coverage caveat's scope: *does an unconsumed shared bundle force a 1 even when
  individual controls inline an equivalent designed `:focus-visible` ring?* This is
  the seam to watch.
- **Motion (A=3, B=2):** Both credited the systemic universal reduced-motion guard
  and Werner/Fallback at 3. They diverged on the roll-up: Run A rolled the dimension
  to its top hand-authored system (3), Run B applied lowest-in-scope-surface strictly
  and let the not-yet-wired shared panel `enter` primitive plus partial token adoption
  on scene/shell hold the floor at 2. The anchor seam is whether an *authored-but-
  unwired* primitive (`motion.ts` "not yet wired to a consumer") counts against the
  motion floor.
- **Evidence-craft (A=2, B=2 — but on opposite facts):** this seam is NOT a grade
  delta; it is a *fact* divergence masked by a grade coincidence, which is exactly
  why grade-delta alone is an insufficient stability signal. Run A asserted RAIL A
  was entirely absent ("zero committed visual-regression PNG snapshots ... verified
  by grep") and capped the dimension at 2 on that absence. Run B counted RAIL A as
  present-but-weak — 381 committed Lost-Pixel baselines under
  `apps/reading/.lostpixel/baseline/` (127 stories × 3 viewports), single-theme,
  flagship `workspace-demo--scene` excluded via `apps/reading/lostpixel.config.ts:51-54`
  `filterShot`, and wired INFORMATIONAL in `.github/workflows/visualtest.yml:53-60` —
  and capped at 2 on that weakness. The two runs landed on the same number for
  contradictory reasons; the +/-1 check waved it through because it only inspects the
  number. Run A was the wrong one (the 381 baselines verify on the live tree:
  `find apps/reading/.lostpixel/baseline -name '*.png' | wc -l` = 381). The BLOCKING
  sharpen fix has reconciled the fact — both runs now read present-but-weak — without
  changing either grade. The seam to watch: a fact-divergence hidden behind a
  grade-coincidence, distinct from the crispness/motion grade-delta seams.

The crispness and motion seams stayed inside +/-1 here. If a subsequent baseline
pushes either to a delta of 2, the fix is to add an explicit anchor sentence
resolving the question above — tighten the rubric, not the tree. The evidence-craft
seam carries a second lesson independent of any future delta: grade-delta is
necessary but not sufficient for stability; the auditor protocol should also require
the underlying per-rail facts to agree, since a fact-divergence can hide behind a
grade-coincidence as it did here.
