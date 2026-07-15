# Library archive shelf — cycle evidence

Date: 2026-07-15
Base: `74ccf1cc25b6f7af3efe72c87acc33201b572076` (`goal/research-index-keyboard`)

## Residual closed

The Library previously used generic generated-color covers and exposed only basic loading/error behavior. This cycle authors the whole full-page shelf as an Antiek polar archive, while preserving workspace-window ownership and keeping every semantic or interactive fact in HTML.

## Authored image contract

- Generator: built-in ChatGPT Image (the user-designated primary image engine).
- Generation ID: `exec-ccabaf04-8638-43d4-af7c-76c7a3703db6`.
- Source: generated 1536×1024 PNG at `/Users/slimydog/.codex/generated_images/019f5c1a-0048-7b21-9fe9-4de63c5fe645/exec-ccabaf04-8638-43d4-af7c-76c7a3703db6.png`.
- Runtime: `library_archive_environment_v1.webp`, 113,274 bytes, SHA-256 `b5fe29bb59dd03c6b9eca02a25f427f22eb75bca8f47de0f91cc55cd4ca7ffca`.
- Prompt boundary: empty limestone-and-walnut polar archive; no mascot, people, animals, books, paper, screens, controls, text, logos, or semantic product state.

The raster is decorative, pointer-inert, empty-alt, and rendered only behind the full-page Library. Titles, rights status, counts, controls, loading, errors, empty state, covers, and navigation remain authoritative accessible HTML. The in-window Library keeps its existing transparent body and does not add a second glass or environment.

## Correctness sharpen rounds

- Added monotonic load and curation generations so superseded requests cannot overwrite the current tab or surface stale errors.
- Reasserted mount state during React StrictMode setup replay and fenced all post-await writes.
- Tab/reload invalidation now clears stale books, errors, curation output, prompt, and busy state synchronously.
- Errors use authored non-leaking copy, an honest unavailable count, and a retry action; loading, error, empty, and populated states are mutually exclusive.
- Real cover URIs retain authority. Failed images fall back to deterministic, token-bound CSS spines and reset when the URI changes.
- Cards constrain intrinsic width and overflow at all three verified breakpoints; reduced-motion disables the loading animation.

## Verification

- `npm test -- --run src/modes/Library/Library.test.tsx`: 15/15 passed.
- `npm run typecheck`: passed.
- `npm run build:check`: passed; production bundle remained within limits.
- `npm run build-storybook`: passed.
- Token lint and type-scale lint: passed earlier in this cycle.
- `git diff --check`: passed.
- LostPixel: 12 deterministic baselines authored for populated, empty, loading, and error states at 1280, 1024, and 768 px. The error 1024 raster was directly inspected after the final count-copy change.
- `hardenx . --strict --json`: LOW, zero concrete findings; four generic advisories and three dropped candidates; no dependency or configuration changes.
- In-app Browser setup returned no available browser instance, so no interactive-browser proof is claimed. Storybook compilation, LostPixel Chromium capture, direct raster inspection, tests, and production build provide the bounded proof for this cycle.

## Independent criticism and engine record

- Codex architecture review found StrictMode replay, stale-response, stale-curation, and cover-failure risks. Each blocking finding was repaired and regression-tested before final review.
- A fresh Codex merge critic then blocked the false retry copy “Your shelf is unchanged” because reload intentionally clears prior results. The copy and regression assertion were repaired; the narrow exact-diff re-review returned ACCEPT.
- MiMo V2.5 Pro independently returned ACCEPT after inspecting lifecycle fences, cover fallback, accessibility, authority, responsive layout, and tests. It noted optional tab-panel linkage and a stronger StrictMode measurement as non-blocking sharpen items.
- GLM-CC `/ultracode` was invoked as requested but returned HTTP 429; no GLM review is claimed.
- Grok builder and Fable planning were invoked; Grok made no edits and Fable reported exhausted credits. The final implementation and evidence do not attribute work to either engine.

The governing executable acceptance contract is `docs/htmlspec/library-archive-shelf.html`.
