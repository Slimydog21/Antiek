# AUDITOR.md — the PostHog-parity audit procedure (cold-executable)

**Sprint:** ALC SPR-03 · **You are a judge, not a workman.**
This is the complete, self-contained procedure an agent (or a `/caffenagent` verifier) executes to grade Antiek's living-background experience against the PostHog craft rubric. You need nothing but this file, the rubric, and the Antiek working tree.

## Inputs (every path named — cold-executable)

| Input | Path |
|---|---|
| The rubric (16 anchors, 4 dimensions × 0-3) | `docs/parity/posthog-craft-rubric.md` |
| The reading log (what the citations mean) | `docs/parity/posthog-reading-log.md` |
| Rubric version (pin) | PostHog SHA **`9c06e96956f68b6cd67e39e30df8ff736e1fcaad`** — cited in every rubric cell as `@SHA`; PostHog citations are evidence-of-a-bar, you do NOT need a PostHog clone to grade Antiek |
| Surface under audit | `apps/reading/` in the Antiek working tree being graded |
| Output you write | `docs/parity/audit-<YYYY-MM-DD>.md` |

You may grade from source + existing Storybook/screenshots; running the frontend is optional but preferred for the FALLBACK surface (see below).

## Surfaces in scope

Grade the living-background experience and its shell surfaces (the SPR-05..08 terrain) — NOT Research/Write/Speak features.

1. **Scene layers** — `apps/reading/src/scene/scene.css`, `apps/reading/src/scene/Scene.tsx` (the living background; SPR-05/06 terrain).
2. **Shell controls** — `apps/reading/src/index.css` + `apps/reading/src/AppShell.tsx` + `apps/reading/src/shell/` (chrome, launcher windows, panels; SPR-08 terrain).
3. **Werner** — `apps/reading/src/werner/`, `apps/reading/src/brand/werner/` (mascot motion/state — graded for craft only, NEVER for hedgehog-resemblance; see firewall).
4. **Reading-mode states** — reading-surface components and their authored states (`apps/reading/src/components/`, `apps/reading/src/modes/`).
5. **The FALLBACK / procedural floor** — see next section; grade it as FIRST-CLASS.

## The FALLBACK is graded as first-class (not a degraded state)

In this spec's posture the procedural floor is a FEATURE, not a downgrade. Grade the no-scene / `prefers-reduced-motion` / opaque-fallback experience as a first-class surface on all four dimensions:
- **Visual crispness:** crispness must HOLD when the scene is off (`apps/reading/src/design/tokens.css` `--glass-bg-solid` opaque fallbacks).
- **Motion & life:** motion must DEGRADE GRACEFULLY, not vanish — the scene freezes to one static, legible frame (`apps/reading/e2e/glass-reduced-motion.spec.ts`). Grade *whether it degrades gracefully*, not merely whether it stops.
- **Product character & evidence-backed craft:** the fallback state should itself be authored (a named story / an asserted e2e state), not an accident.
A surface that is beautiful with the scene on and broken with it off does NOT earn the on-state grade.

## Evidence requirement — no uncited grades

Every grade MUST cite Antiek `file:line` OR a screenshot path. A grade with no evidence is invalid and must be re-done. When you count (named stories, `var()` consumers, reduced-motion handlers, committed snapshots, `.feel-focusable` consumers on the in-scope controls), record the count and the command/path you counted from. Re-resolve every line number on the live tree — do not trust the rubric's baseline-2026-06 spot-check numbers.

## You are a judge — you may NOT propose fixes

**FORBIDDEN:** proposing, sketching, or implementing any fix, refactor, or improvement. Do not write "to reach 3, do X." Grades and findings ONLY. Fixing is the job of SPR-05/06/07/08 — the auditor stays a judge so the before-photo and the gate stay honest. A finding describes WHAT IS (with evidence and a grade), never WHAT SHOULD BE DONE. If you catch yourself writing a recommendation, delete it.

## Output format → `docs/parity/audit-<YYYY-MM-DD>.md`

Write exactly this shape:

```markdown
# Parity audit — <YYYY-MM-DD>
Rubric version: PostHog SHA 9c06e96956f68b6cd67e39e30df8ff736e1fcaad
Antiek tree: <git SHA or "working tree @ <date>">
Auditor context: <run 1 | run 2 | independent>

## Graded table
| Dimension | Scene | Shell | Werner | Reading-mode | Fallback | Dimension grade |
|---|---|---|---|---|---|---|
| Visual crispness | n/3 | n/3 | n/3 | n/3 | n/3 | n/3 |
| Motion & life | … | … | … | … | … | … |
| Product character | … | … | … | … | … | … |
| Evidence-backed craft | … | … | … | … | … | … |

(Dimension grade = the honest roll-up across surfaces; state the rule you used, e.g. "lowest in-scope surface" or "weighted by SPR ownership." A 2-with-named-exception is written `2*` and the exception named in findings.)

## Per-dimension findings
### Visual crispness — <grade>/3
- <surface>: <grade>/3 — <countable evidence> (cite apps/reading/<file>:<line> or <screenshot>)
- …
### Motion & life — <grade>/3
- …
### Product character — <grade>/3
- …
### Evidence-backed craft — <grade>/3
- …

## Fairness notes (where Antiek meets or beats PostHog)
- <dimension>: <evidence Antiek already owns the bar>

## Honest embarrassments (the before-photo's job)
- <dimension/surface>: scored n/3 because <evidence> — recorded without softening.
```

The baseline run (M5) writes its first run to `docs/parity/baseline-2026-06-12.md` using this same format; the second independent run + the diff go to `docs/parity/baseline-stability-check.md`.

## Stability rule — flag the RUBRIC, not the code

Two auditor runs on UNCHANGED code must agree within **±1 grade level on every dimension**. If two independent contexts diverge by >1 on any dimension, the anchors are too loose to gate on: **flag the RUBRIC (tighten the anchor, re-run), NOT the code.** The code did not change between runs; only the rubric's discriminating power is on trial. Record the side-by-side diff. The rubric is not done until stability holds.

## DOWNSTREAM GATE LANGUAGE (the clause SPR-05/06/07/08/09 cite)

> **Parity gate.** Each elevation sprint is gated by the parity audit. **SPR-05** must reach its target on **visual crispness (scene)**; **SPR-06** on **motion & life**; **SPR-07** on **product character**; **SPR-08** on **visual crispness (shell)**; **SPR-09** must reach target on **all four dimensions vs the 2026-06-12 baseline**. "**≥ target**" means **grade 3**, OR **grade 2 with a single named, justified exception recorded in the audit** (e.g. the living-scene ambient-motion exception, or image-snapshot RAIL A explicitly deferred). **No dimension may regress below its 2026-06-12 baseline grade** on any sprint — a sprint that raises its owned dimension while dropping another below baseline FAILS its gate. The auditor produces the grade; the sprint cites this clause and the baseline number it must beat; no interpretation required.

Keep this clause verbatim when a sprint cites it.

## Run checklist (cold)
1. Read `docs/parity/posthog-craft-rubric.md` fully (incl. the firewall + the two logged DECISIONs: living-scene exception, rail decomposition).
2. For each surface × dimension, count what the rubric names; cite `file:line`.
3. Grade the FALLBACK as first-class.
4. Award the highest fully-met level; mark `2*` + name the exception where applicable.
5. Write `docs/parity/audit-<date>.md` in the format above. No fixes. No uncited grades.
6. If this is run 2: diff against run 1; if any dimension differs by >1, flag the rubric.
