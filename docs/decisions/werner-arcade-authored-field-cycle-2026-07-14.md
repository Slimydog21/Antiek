# Werner arcade authored field — Cycle 570

Status: implemented; code and rendered visual adoption verified locally.

## Decision

Use one bundled ChatGPT Image-authored night-archive plate only behind the
passive field of the opt-in Paperclip Zombies wait game. Game targets, fort,
evidence traces, HUD, status copy, hitboxes, input, score, waves, research
lifecycle and cursor ownership remain deterministic code.

The base surface is always painted first. The authored plate may replace only
the field interior after a valid image load; it is clipped away from the fort,
HUD and status bands. The complete procedural terrain/grid remains the
unloaded, error and teardown fallback rather than an empty or blocked canvas.

## Visual adoption gate

Rendered target and HP-pip legibility is proven. The in-app browser exposed
no controllable tab, and Lost Pixel 3.22 ignored the attempted shot filter,
started all 726 captures, then hit the known unrelated AISidecar exception
before the arcade story. The run was stopped and no baseline was accepted.
The first remote PR run then reported zero diff because the committed baseline
slug (`deepresearch`) did not match LostPixel's generated slug
(`deep-research`); additions are non-blocking in the current configuration.
That green result is rejected as evidence. A scoped local LostPixel 3.22 run
captured only the Playing story after a story-only deterministic Enter press
and a 750 ms settling interval. The 768/1024/1280 captures all show wave 01,
the authored field, a spawn-edge target and its HP pip, code-native fort,
trace, HUD and status, and native-canvas cursor ownership. The target remains
immediate against the deliberately quiet right edge. The prior exact-host
procedural captures are retained under
`docs/evidence/werner-arcade-authored-field/` as fallback proof; loader and
paint-order tests cover error and teardown without game-state drift.

The first canonical active-wave baselines proved timing-dependent in remote CI
(4.60–7.40%) because targets advance continuously. That nominally successful
job is also rejected: the repository does not currently set
`failOnDifference`. The canonical Playing baselines therefore capture the
deterministic authored ready plate at the corrected generated slug. The
inspected active-wave matrix is retained separately under
`docs/evidence/werner-arcade-authored-field/` as human contrast evidence, not
as a false deterministic regression oracle. The awaited Storybook `play`
lifecycle refuses to complete until the validated backdrop readiness marker
exists. The story-only harness decodes and caches the exact bundled plate
before opting into the lazy game, so the canvas cannot mount on an uncached
asset during remote capture. Backdrop readiness also sends a redraw-only token to `ArcadeMount`,
which invokes `render` against the existing context without re-running
`init`, replacing the cartridge, or changing game state. A fresh scoped local
run then reported exact zero difference at 768/1024/1280. Production game
initialization, focus and input do not wait on visual proof instrumentation.
SPR-19 is now counted as implemented. The existing feature flag remains
production-default-off; this transport grants no deployment authority.

The legacy repository-wide visual sweep does not set `failOnDifference` and
therefore cannot prove this adoption. CI now runs a three-shot story-ID-scoped
gate before that sweep. It requires every named canonical baseline before
capture, every named current plate after capture, and an empty diff directory;
missing evidence or any target delta reds the PR and activates the existing
current/diff artifact upload. The normal workspace-demo exclusion also uses
the actual Storybook `id` field rather than the not-yet-generated `shotName`,
repairing its previously ineffective filter.

## Asset provenance

The built-in ChatGPT Image tool generated the 1,586 × 992 master on 2026-07-14
in Codex thread `019f5c1a-0048-7b21-9fe9-4de63c5fe645`, call
`exec-3f7ed49e-3f66-45df-96f8-b916c55f3b8c`. The exact prompt requested a
quiet, hand-painted Antarctic night archive, broad low-contrast travel lanes,
restrained night-token colors, and explicitly prohibited characters,
paperclips, enemies, targets, fort, HUD, text, icons, controls, gore, and
interactive-looking objects. The exact prompt was:

```text
Use case: stylized-concept
Asset type: passive background plate for Antiek's 480×300 Paperclip Zombies canvas minigame
Primary request: Create a quiet, richly authored night archive landscape under pressure—an atmospheric Antarctic research-file field rendered as a polished hand-painted game background, with broad matte shapes and subtle depth. It should feel like an eccentric scholarly field station after midnight, wholesome and mysterious rather than violent.
Scene/backdrop: dark navy snow-and-paper terrain, distant low shelves and abstract file-box silhouettes melted into the horizon, faint aurora haze and soft moonlit ice planes. Reserve the leftmost 6% as visually quiet because deterministic code paints a fort there. Keep the rightmost 10% and the central horizontal travel lanes especially quiet and low contrast for tiny moving targets.
Style/medium: polished editorial game illustration with tactile paper, ink wash, and restrained screen-print texture; unmistakably Antiek, not generic neon arcade pixel art.
Composition/framing: landscape 8:5 composition designed to crop/downsample to exactly 480×300. Important atmosphere only within the middle field; no essential detail at edges. Broad tonal masses, excellent legibility at small size.
Lighting/mood: midnight-blue, calm tension, subtle wonder, low contrast through the central field.
Color palette: deep ink navy, muted icy blue-gray, very restrained warm parchment; avoid bright yellow and bright cyan so code-native HUD, HP pips, and traces retain semantic contrast.
Constraints: background/environment only. Absolutely no characters, penguins, paperclips, zombies, enemies, people, creatures, crosshairs, targets, weapons, blood, gore, buttons, HUD, fort, score, wave, lives, text, letters, numbers, icons, evidence traces, status plates, frames, borders, logos, or watermark. No interactive-looking objects. No high-frequency rubble, stars, sparkles, bloom, film grain, or sharp microdetail in the central field. No cast shadows implying hidden actors.
```

SHA-256:

- master PNG: `aaea237ba259aabbf19ad8e71d1b053e962c3f8387a901a493543f3924216fcf`
- runtime JPEG: `2a2ac39246bab865c8e4245546951a2c2c37b0f55ccef9f19d7017c1d8847045`

The runtime asset is reproducible with macOS `sips`: center-crop the master to
1,584 × 990, resize to 480 × 300, then encode JPEG at quality 74. It is 17 KB,
opaque, exact-canvas-sized, and was visually inspected after compression.

## Architecture adjudication

GPT-5.6-sol and MiMo V2.5 Pro independently returned `ACCEPT IDEA`. Both
required a bundled static asset, fallback-first rendering, unchanged logic and
code-native semantic chrome. They disagreed on whether `drawImage` belongs in
the cartridge or pure visual adapter. The adapter is the only correct clipping
owner: drawing before `drawZombiesScene` would be immediately covered by its
opaque fallback field, while drawing afterward would cover chrome and targets.
The selected seam passes an optional already-loaded image reference into the
pure projection and performs no loading, timing, state, or network work there.

GLM `/ultracode --effort max` activated but dropped the supplied objective; no
GLM verdict is claimed. Grok was not called because the operator reported its
tokens exhausted.

## Withheld authority

No gameplay, spawn, speed, wave, scoring, lives, hitbox, fort geometry, focus,
input, cursor suspension, research state, reduced-motion policy, route,
runtime generation/fetch, backend, spend, merge, or deployment change.
