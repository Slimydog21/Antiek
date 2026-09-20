# Werner research lens — execution record

Date: 2026-07-13

Branch: `goal/werner-research-lens`

Base: `goal/werner-activity-spine-v2` / PR #2047

## Decision

Reading and research routes select a `research-lens` station activity. Other
routes retain `ice-fishing`. Selection is a pure pathname policy: it has no
random rotation, timer state, persistence, content reads, network calls, or
permission to move Werner.

The interactive lens is HTML/CSS. The generated observatory image is design
evidence only; its apparent text and graph are pixels and therefore cannot be
product authority, accessible controls, or acceptance evidence.

The legacy `VITE_WERNER_ICE_FISHING` flag gates only ice fishing. It does not
disable the independent research lens. Reduced-motion disables every custom
cursor instrument and preserves the native cursor.

## Implemented boundary

- Exact knowledge-work routes: `/`, `/deep-research`, `/my-research`,
  `/readings`, and `/meta-readings`.
- Knowledge-work prefixes: `/inv/`, `/deep-research/`, and `/read/`.
- Trailing slashes normalize before selection; false positives such as
  `/deep-researcher` retain ice fishing.
- `ResearchLensCursor` consumes only `live`, `pointerIdle`, and `tabHidden`
  from `useMouseFollow`.
- The overlay is `aria-hidden` and `pointer-events: none`; it never intercepts
  knowledge-work controls.
- No new keyframe was added. The idle state uses a tokenized opacity transition,
  and reduced-motion removes even that transition.

## Evidence

- Focused Vitest gate: 9 files, 52 tests passed.
- TypeScript project check: passed.
- Motion guard: passed as part of the focused gate.
- Token lint: passed; 80 grandfathered hardcoded hex values, baseline 120, no
  newly introduced hex.
- Type-scale lint: passed; no new chrome font size above 24 px.
- Production build: passed; 867 modules transformed. Existing dynamic/static
  import and bundle-size warnings remain.
- Storybook build before the final feature-flag decoupling: passed; the final
  change affects shell activation only and is covered by focused tests and the
  production build.
- `git diff --check`: passed before this record; run again at handoff.
- Hardenx strict result: exit 0, LOW band, 0 REAL findings, 14 repository-wide
  advisories, and 7 filtered findings.

Generated-image provenance:

- Asset: `docs/design-evidence/werner-research-observatory-v1.png`
- Dimensions: 1672 × 941
- SHA-256:
  `d572354e447fc61fdea1ada8cc74f028ef95bc5ec3a215fd43fb0e4fba254cbc`
- Model path: ChatGPT Image, using the canonical transparent Werner pose as
  reference. See the adjacent provenance Markdown file.

## Independent review and corrections

An independent Codex review found two material issues, both corrected before
handoff:

1. A custom lens breathing keyframe bypassed the repository motion guard. The
   keyframe and animation were removed; the motion guard now passes.
2. The research lens was inadvertently coupled to the ice-fishing feature flag.
   Activation is now activity-specific, with a regression test proving that a
   disabled fishing flag does not disable research routes or hide the native
   cursor on utility routes.

The other requested CLI engines did not produce review approval: Grok returned
a quota error, the GLM ultracode invocation stopped at readiness, MiMo parsed
the image prompt as a file path, and an exploratory GPT planning run was
interrupted after it failed to converge. These are recorded as orchestration
gaps, not positive evidence.

## Known limits and honest non-claims

- Live visual acceptance is **NOT PROVEN**. The required in-app browser exposed
  no controllable tab in this session, and the browser skill forbids silently
  substituting a different browser path. Storybook compilation is not visual QA.
- A broad local review run reported 36 failures across 10 files because its
  environment exposed an invalid `window.localStorage`; the real motion-guard
  failure in that run was fixed. This slice relies on the focused deterministic
  gate above, not a claim that the whole local suite is green.
- Base PR #2047 currently has one unrelated CI failure in
  `MyResearch.test.tsx`: expected `2 running`, received `3 running`. Its Werner
  tests and 180 other test files passed. This slice does not rewrite unrelated
  research-state aggregation.
- The lens does not magnify or inspect document content. It is a legible cursor
  instrument, not a fake semantic or optical capability.

## Re-derived next slice

After both stacked PRs are reviewable, visually verify pointer precision,
contrast, idle treatment, route transitions, and reduced-motion behavior in an
actual in-app browser. Then build one small, independently gated Werner station
activity whose job is tied to a real reading interaction—preferably a
highlight-to-chase affordance—without giving the mascot movement, document, or
network authority. Do not begin an activity picker or persistent activity store
until real use demonstrates that deterministic route selection is insufficient.
