# Werner night-watch v1 — provenance

Date: 2026-07-14

- Origin: ChatGPT Image identity-guided edit using canonical idle and authored dusk poses
- Generated RGB source: `werner-night-watch-source-v1.png`
- Runtime alpha-cut pose: `apps/reading/src/brand/werner/poses/werner_night_watch_v1_transparent.png`
- Source SHA-256: `122c01100e2efd52e956f09cf05699e8f11d7d7a7c10816cb393eca2e769f056`
- Runtime SHA-256: `52791d704795cc06223abbf4f448618fa9c72f3fa70287cc3bce6479b0aa9b0c`

The accepted pose keeps Werner awake, centered, grounded, and companionable.
It preserves the canonical coat, warm-white belly, sun-yellow bill and feet,
outline, proportions, and open eyes. It contains no sleep cue, yawn, thinking
gesture, celebration, moon, star, aurora, snow, glow, prop, text, scenery,
shadow, clothing, or second character.

ChatGPT Image returned a 1254×1254 RGB source with a baked checkerboard. The
first alpha pass left isolated neutral speckles, which visual inspection
rejected. A critic then caught that partially transparent neutral boundary
pixels could composite as a pale matte on the night surfaces. The final
topology-preserving cut follows the connected checkerboard down to neutral
mid-grey (`--near-white-min 180 --hard-cut`) and retains no partial-alpha or
pale neutral boundary pixels. The cutter's ordinary `226`/feathered defaults
remain unchanged for the older non-checkerboard pose family.
The final 1024×1024 RGBA derivative has fully transparent canvas edges, subject
bounds `(271,154)–(748,843)`, 800,840 fully transparent pixels, and an opaque
belly sample. Runtime never imports the RGB source or calls a provider.
