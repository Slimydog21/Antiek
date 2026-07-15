# Curiosity Observatory — design evidence

Date: 2026-07-15
Base: `432b787fae86e5af34f00bf84704e0cdcbaa021c` (`goal/library-archive-shelf`)

## Residual repaired

`BrainstormStation` previously presented a generic central `PanelHost` surface. On desktop it could not select a question from its collapsed mobile-only list, and its loading, empty, and failure behavior had no whole-surface visual contract. The Curiosity Observatory gives that lifecycle an authored home while leaving the existing watch-list and thought-partner panels as the workspace wings.

## Generated environment

- Generator: OpenAI image generation (`image_gen`), generation `exec-48f89526-ca3d-4289-9b6e-f0e6a657142d`.
- Source prompt boundary: an empty polar observatory environment only—no mascot, books, papers, questions, interface, or text—so product semantics remain live HTML.
- Runtime asset: `apps/reading/src/brand/werner/brainstorm/curiosity_observatory_environment_v1.webp`.
- Runtime SHA-256: `66aa1e7cbce29e9e5fe88ffae102e0811905fc5d58aeaa01fa38c4d3781b523f`.
- Runtime size: 128,364 bytes (WebP quality 72); source PNG was 2.6 MB.
- Canonical Werner remains a separate fixed component at the thought station. No generated mascot pixels are used.

## Production raster proof

[Production render at 1280×720](./renders/curiosity-observatory-production-1280.webp) was captured from the built Storybook in Chromium after switching the fixture to production ambience, waiting for the imported WebP to decode, and waiting two animation frames. It proves the real raster, live HTML question desk, and canonical Werner compose together. The component test separately asserts that production mode imports the named observatory asset and does not apply the still-fixture class.

Lost-Pixel opens five differently scaled Chromium pages concurrently. Chromium produced imperceptible one-colour-level drift across 10–18% of pixels when the same full-bleed WebP was scaled in those pages; Lost-Pixel hard-codes pixelmatch sensitivity to zero. The committed state/layout fixtures therefore freeze local motion and replace only the decorative raster with a deterministic CSS observatory wash. They continue to exercise all live HTML, responsive geometry, Werner placement, and state transitions. This separation avoids both flaky approval and a false claim that the regression matrix verifies GPU raster decoding.

## Behavioral contract

- The first authoritative response item becomes the desktop selection; refresh preserves a selection only by surviving question ID.
- Monotonic load and launch generations fence stale completions and unmounts, including React StrictMode effect replay.
- A synchronous in-flight ref prevents duplicate launch sends before React commits state.
- A successful launch handle is authoritative: navigation continues even when the best-effort list refresh fails.
- List and launch failures show fixed private-safe language. A list refresh failure retains last-known questions.
- The environment is decorative, pointer-inert, empty-alt, and `aria-hidden`; product semantics remain selectable HTML.
- Werner uses its canonical sanctioned pose animation; the loading orbit uses the shared motion-safe utility and stops for reduced motion.

## Verification

- Focused Vitest: 8/8 passing (selection/raster boundary, empty, retry/privacy, superseded load, StrictMode, duplicate launch, refresh-after-success failure, private launch failure).
- TypeScript: passing.
- Token lint and type-scale lint: passing.
- Production `build:check`: passing; main gzip 576.67 KB of 683.59 KB, Lemon gzip 49.95 KB of 58.59 KB.
- Storybook production build: passing.
- Lost-Pixel: 12/12 deterministic shots passing twice across populated, empty, loading, and error at 1280, 1024, and 768.
- `git diff --check`: passing.
- hardenx strict scan: LOW, zero real findings; no dependency or configuration changes.
- MiMo V2.5 Pro critic initially blocked dead `.dark` selectors and undefined variables; both were repaired with media-query dark mode and existing design tokens. Fresh review: ACCEPT.
- GLM-CC `/ultracode` critic was unavailable due HTTP 429; this is recorded as an engine gap, not a fabricated review.
