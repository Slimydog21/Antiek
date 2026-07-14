# Werner dusk-gaze v1 — provenance

Date: 2026-07-14

- Origin: ChatGPT Image identity-guided edit using canonical idle and thinking poses
- Generated RGB source: `werner-dusk-gaze-source-v1.png`
- Runtime alpha-cut pose: `apps/reading/src/brand/werner/poses/werner_dusk_gaze_v1_transparent.png`
- Source SHA-256: `50d8708d15520d7b053373d12a790b73b63c2b19d22e11bf7d1d415f3b058b85`
- Runtime SHA-256: `d491c16a9a6c7bdce5cc0bb59604568a215ebe36057060d22ed72b5c4047cfab`

The accepted pose keeps Werner's canonical coat, warm-white belly, sun-yellow
bill and feet, outline, proportions, and calm temperament. His planted body
faces mostly forward while his open eyes and head turn gently toward the fading
light. It contains no wink, thinking gesture, bubble, icon, text, prop, scenery,
shadow, clothing, or second character.

ChatGPT Image returned a 1254×1254 RGB source with a baked checkerboard, so that
file is provenance only. The existing topology-preserving `cut_pose_bg.py`
pipeline removed only the connected neutral surround; a 1024×1024 derivative
has real RGBA alpha, 745,128 fully transparent pixels, subject bounds
`(235,148)–(765,912)`, and an opaque belly sample. Runtime never uses the RGB
source or calls an image provider.
