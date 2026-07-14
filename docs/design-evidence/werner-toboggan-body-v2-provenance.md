# Werner toboggan body v2 — generation provenance

Date: 2026-07-14  
Tool: built-in ChatGPT Image (`image_gen`)  
Mode: identity-preserving precise-object edit, followed by local chroma-key removal

## Edit target

`apps/reading/src/brand/werner/poses/werner_tobogganing_v1_transparent.png`

The v1 file remains untouched as the authored provenance source. The runtime
candidate is a sibling v2 asset, not a destructive replacement.

## Prompt

Preserve Werner exactly as drawn in the low forward toboggan pose: silhouette,
proportions, face, eye, beak, colors, outlines, shading, flipper, and both feet.
Remove only horizontal speed streaks, snow puffs/dots, and the ground shadow.
Reconstruct affected body areas from adjacent body colors and outlines. Do not
redesign, rotate, crop, rescale, beautify, add a sled, or alter anatomy. Render
Werner alone on a perfectly flat `#ff00ff` chroma-key background with no shadow,
reflection, text, logo, or watermark.

## Alpha extraction

The project’s installed imagegen helper sampled the border key and applied a
soft matte plus despill. A deterministic centered crop then removes excess
transparent padding without resampling the subject. Measured runtime output:
1024×1024 RGBA, alpha extrema 0–255, every border pixel transparent, 26.96%
of pixels above half opacity, and subject alpha bounds
`(84, 284)–(941, 726)`. The half-opacity mask is one connected component
(282,702 pixels); there are zero magenta-key pixels at any nonzero alpha.

## Direct visual review

The deterministic Storybook plate was reviewed at 768 px and 1280 px browser
widths after the scoped Lost Pixel run. At 24, 32, and 64 px Werner remains a
recognizable low forward slide, with a clean silhouette and no visible magenta
fringe. The explicit-reduced 32 px cell retains the complete body and removes
the speed layer. The runtime asset and all three committed baselines were also
inspected at native resolution: no source snow, horizontal source streak,
ground shadow, or invented sled remains. The only speed marks in the animated
cells are the wrapper's three code-native SVG lines.

Baselines:

- `brand-werner-animations--toboggan-spinner-fidelity__[w768px].png`
- `brand-werner-animations--toboggan-spinner-fidelity__[w1024px].png`
- `brand-werner-animations--toboggan-spinner-fidelity__[w1280px].png`
