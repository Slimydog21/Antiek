# Speak listening-room atmosphere — cycle decision

Date: 2026-07-14
Sprint: WERNER-ACT SPR-27

## Decision

Ship one empty ChatGPT Image listening room beneath Speak's existing HTML
SceneChrome. The bitmap owns dark timber, one ambient lantern, a dusk mountain
window, and nothing else. Werner, portraits, capture, microphone permission,
consent, transcription, controls, and oral-history state remain canonical HTML.

The original concept was rejected because its equipment and papers falsely
implied recording and transcript authority. The accepted edit removed all of
those elements and introduced no replacement props.

## Proof

- The 1672×941 provenance PNG and 124,088-byte runtime WebP have verified
  SHA-256 hashes and remain beneath the 128 KiB runtime ceiling.
- Taxonomy-derived tests cover every current and future Speak route and prove
  mutual exclusion from Research and Write. The combined suite passes 34 tests.
- TypeScript, token lint, production build, and Storybook build pass.
- Two substantive stories have zero-diff LostPixel baselines at 768, 1024,
  and 1280 pixels. The expanded 47-story axe audit passes.
- A fresh GPT-5.6-sol critic returned ACCEPT. HardenX strict reports LOW with
  0 REAL findings.

## Withheld authority

No recording, consent, transcript, portrait, microphone behavior, generated
oral history, additional mascot, video stream, provider call, hotspot, route
change, network spend, merge, or deployment is authorized by this decision.
