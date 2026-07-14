# Research observatory atmosphere — cycle decision

Date: 2026-07-14
Sprint: WERNER-ACT SPR-25

## Decision

Ship one mascot-free, UI-free ChatGPT Image environment beneath Research's
existing HTML SceneChrome. The runtime bitmap owns only alpine shelter,
lantern, mountain, sky, and aurora atmosphere. Werner, documents, evidence,
graphs, citations, controls, state, and interaction remain canonical HTML.

The original concept was rejected for runtime use because it duplicated Werner
and painted fake product surfaces. A first edit removed those elements; a
second edit removed the remaining telescope after independent review found it
could still read as an instrument or control.

## Proof

- The 1672×941 provenance PNG and 109,152-byte runtime WebP have recorded,
  verified SHA-256 hashes; the runtime asset stays below the 128 KiB ceiling.
- A taxonomy-derived test mounts the atmosphere on every current and future
  Research route. Non-Research tests prove the exact prior body DOM/classes;
  shared routes remain bare. All 16 focused tests pass.
- TypeScript, token lint, production build, and Storybook build pass.
- Two substantive stories have zero-diff LostPixel baselines at 768, 1024,
  and 1280 pixels. The rebuilt 43-story axe audit passes, including both.
- A fresh GPT-5.6-sol CLI critic returned ACCEPT after its exhaustive-route
  finding was repaired. HardenX strict reports LOW with 0 REAL findings.

## Review honesty

Fable 5 was unavailable due exhausted usage credits. Opus 4.8 and MiMo did not
produce terminal verdicts. GLM-CC `/ultracode` at maximum effort and the
GLM-Codex fallback both returned HTTP 429. Those engine gaps are recorded and
are not represented as approvals. The OpenAI critic's first REVISE verdict
caused removal of the telescope, restoration of non-Research DOM parity,
real integration/a11y evidence, and taxonomy-derived route coverage.

## Withheld authority

No additional workflow atmosphere, mascot or pose, animated/video stream,
Krea/Modal call, generated document, hotspot map, route/activity change,
second scene clock, content mutation, network spend, merge, or deployment is
authorized by this decision.
