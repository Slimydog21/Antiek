# Werner authored waking-pose evidence — Cycle 568

Status: asset validated; runtime adoption rejected and deferred.

## Decision

Preserve the identity-anchored ChatGPT Image waking pose as design evidence,
but give it no product authority. The live mascot has no truthful persistent
`waking` or dawn lifecycle, so this change intentionally adds no imports,
scene-map entry, public mood, event binding, Storybook baseline, or runtime
behavior. The recorded dawn `POSE_GAPS` remain open.

## Image provenance

The built-in ChatGPT Image tool edited `werner_default_v5_transparent.png` on
2026-07-14. Its C2PA metadata identifies `gpt-image` version `2.0`; no more
specific backend checkpoint or seed was exposed. The generation call ID is
`exec-498f1f81-7114-4dcc-843c-7507b238eeb1` in Codex thread
`019f5c1a-0048-7b21-9fe9-4de63c5fe645`. The exact revised prompt was:

```text
Use case: identity-preserve
Asset type: canonical transparent mascot pose for Antiek UI scene states
Input image: Image 1 is the exact identity, character-design, line-weight, palette, shading, proportions, and rendering-style reference for Werner the penguin.
Primary request: Create a dawn-waking pose of this exact same Werner. He has just woken at first light: a small wholesome yawn, eyes softly half-open, body upright, one flipper raised in a gentle stretch while the other remains relaxed. The pose should read clearly at 64–120 px and feel calm, companionable, and quietly funny—not energetic celebration, not sleeping, not thinking, not distressed.
Identity invariants: preserve the exact rounded pear-shaped body, black head/back/flippers, warm off-white face and belly, saturated lemon-yellow bill and feet, black outline character, cute proportions, and polished hand-illustrated finish from Image 1. Keep exactly one Werner, full body visible, no clothing, no accessories, no text.
Composition: centered full-body character, generous even padding, no cropping, square canvas.
Backdrop: perfectly flat solid #ff00ff chroma-key background for later background removal. The background must be one uniform color with no shadows, gradients, texture, reflections, floor plane, or lighting variation. Do not use #ff00ff anywhere in Werner.
Constraints: no cast shadow, contact shadow, reflection, scenery, sun, snow, bed, alarm clock, props, watermark, or typography. Change only the pose/expression; do not redesign the character.
```

The retained files are content-addressed as follows (SHA-256):

- anchor: `30c0d3f8bdf3baa243e624811174b28ec9205aadfc24181e775036c835a34f57`
- chroma master: `58ba9e469da5a2cf89dc11c42624df3baf0f488b03025f8274cd62c2eca0a04b`
- transparent derivative: `93f08879401d48618f4be9eb9eda0715bf08b3d39ad4417011c2800706b21495`

The raw 1254 × 1254 output was copied without modification to the chroma
master. The derivative is reproducible from that master with the repository
color-correction script (Git blob `a3dac94a3974eebd980088fb97e07eccf43b38d6`)
and the imagegen helper (Git blob
`50539877b05c946ea2dcaaee6fbed778bf17cb53`):

```sh
python3 apps/reading/src/brand/werner/color_correct.py \
  --image apps/reading/src/brand/werner/poses/werner_waking_v1_chroma.png
python /Users/slimydog/.codex/skills/.system/imagegen/scripts/remove_chroma_key.py \
  --input apps/reading/src/brand/werner/poses/werner_waking_v1_chroma_corrected.png \
  --out apps/reading/src/brand/werner/poses/werner_waking_v1_transparent.png \
  --auto-key border --soft-matte --transparent-threshold 12 \
  --opaque-threshold 220 --despill --force
rm apps/reading/src/brand/werner/poses/werner_waking_v1_chroma_corrected.png
```

Measured alpha evidence: all four corners are alpha 0; alpha bounds are
`(284, 161)–(1003, 1084)`; nonzero coverage is 31.08%; 4,044 pixels are partial
alpha; and 1,596 pixels exactly match brand sun. The canonical idle anchor
covers 27.78%, so the waking pose is comparably framed rather than radically
zoomed. Host visual inspection found one Werner, a clean silhouette, readable
waking action, and no visible magenta fringe.

## Production audit

The first implementation attempt routed dawn scenes through
`wernerSceneMap`. A caller audit disproved that path: `Werner scene=...`,
`wernerSceneMap`, and `wernerMoments` have no production callers. The live
`PenguinMascot` renders `WernerRig`, which currently supplies the canonical
idle Werner, while `Scene` is independent and exposes only day/night defaults.
The attempted integration therefore changed a Storybook proof surface, not the
product. All of that code and its three generated visual baselines were
removed.

The nearest live signal—pointer-idle sleep—is a bounded 2.4-second emote rather
than a persistent asleep state. Treating the next pointer action as “waking”
would be false and would require an explicit precedence contract across emotes,
fishing, walking, dragging, games, route changes, and reduced motion.

## Adversarial review

OpenAI's freshness auditor proposed a visible episode-caption strip. MiMo
refuted it because it duplicated physical emotes and existing error toasts.
Grok's real audit call returned HTTP 402 (balance exhausted). Fable 5's real
planning call stayed alive without output and was terminated after the bounded
window; no Fable verdict is claimed. A separate GPT architecture critic chose
verdict B: preserve the generated assets and provenance-only contract, but
drop the scene-map/runtime/test/baseline changes because no truthful production
signal exists.

## Adoption gate

The transparent asset remains deliberately unreferenced design evidence. A
future implementation may adopt it only after the product owns either a real
persistent waking lifecycle or a user-visible time-of-day source and specifies
deterministic precedence, interruption, cleanup, accessibility, and
reduced-motion behavior. Until then, do not claim this closes either dawn pose
gap or appears in the product.

## Withheld authority

No runtime image generation, route, event, scene behavior, cursor behavior,
game behavior, backend, network, model spend, merge, or deployment is added.
Dusk gaze, settled night, and toboggan effects remain separate pose decisions.
