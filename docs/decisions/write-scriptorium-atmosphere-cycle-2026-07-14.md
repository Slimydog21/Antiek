# Write scriptorium atmosphere — cycle decision

Date: 2026-07-14
Sprint: WERNER-ACT SPR-26

## Decision

Ship one empty ChatGPT Image scriptorium beneath Write's existing HTML
SceneChrome. The runtime bitmap owns only walnut floor, limestone arch, empty
alcove, lantern, snow, and mountain light. Werner, drafts, source blocks,
books, writing tools, editor state, controls, and interaction remain HTML.

The original concept was rejected because nearly every foreground pixel
competed with a canonical product owner. The accepted edit removed all of
those elements and introduced no replacement props.

## Proof

- The 1671×941 provenance PNG and 113,742-byte runtime WebP have verified
  SHA-256 hashes; the runtime asset stays below 128 KiB.
- Taxonomy-derived tests mount the layer on every current and future Write
  route, preserve Research's atmosphere, and leave Read/Speak/shared behavior
  unchanged. The combined Research/Write suite passes 24 tests.
- TypeScript, token lint, production build, and Storybook build pass.
- Two substantive stories have zero-diff LostPixel baselines at 768, 1024,
  and 1280 pixels. The rebuilt 45-story axe audit passes, including both.
- A fresh GPT-5.6-sol CLI critic returned ACCEPT. HardenX strict reports LOW
  with 0 REAL findings.

## Withheld authority

No generated draft, bitmap editor, additional mascot, animated/video stream,
Krea/Modal call, hotspot map, route/activity change, content mutation, network
spend, merge, or deployment is authorized by this decision.
