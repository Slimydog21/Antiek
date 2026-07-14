# Scene authored transition palettes — cycle 573

## Decision

Give dawn and dusk independent static landscape palettes with six authored roles each: sky top, sky middle, sky horizon, and far/middle/near ridge. Keep day and night class semantics unchanged. The pure `LANDSCAPE_PALETTE` map is the only component-facing authority; CSS variables own values and Tailwind owns literal emitted utilities/background images.

## Evidence

- Exact base: PR #2097 head `90c0102ab33ef0fe122936df5f66842750b4b45c`.
- `ProceduralSky.tsx` previously grouped dawn with day and dusk with night for every color role; only ridge seed geometry differed.
- GPT-5.6-sol returned `REVISE IDEA`: the product gap was real, but four simultaneous plates require static scene tokens rather than OS-theme aliases, and the canvas weather palette must remain separate.
- The first MiMo diff had two rejected defects: a uniqueness test appended the daypart key and therefore could never detect duplicates, and dynamically interpolated Tailwind class names were invisible to the content scanner. Both were replaced with genuine tuple comparison and literal class strings.
- The first pixel capture showed the transition colors existed but placed the horizon stop behind the silhouettes. Named dawn/dusk background-image tokens move the horizon to 70%, exposing a restrained atmospheric band without moving any ridge.

## Palette

| Mood | Sky top / middle / horizon | Ridge far / middle / near |
| --- | --- | --- |
| Dawn | `#D4DEE2` / `#E4E9E7` / `#E6D8B5` | `#B7C5CB` / `#879BA8` / `#506574` |
| Dusk | `#182235` / `#26384A` / `#4B7777` | `#394A5C` / `#273749` / `#121C2B` |

Day and night continue to use their pre-cycle utility tuples exactly.

## Rejected alternatives

- Theme-mapped aliases: dishonest when dawn, day, dusk, and night render together under one OS media state.
- `accent.aurora`: reserved for AI-thinking interaction; atmospheric teal must not impersonate it.
- Raw/dynamic Tailwind construction: risks purge and token drift.
- Runtime ChatGPT Image/Krea bitmap: violates deterministic offline HTML-native fallback and cost authority.
- Generic orange/magenta transition art: visually loud and hostile to a reading workstation.

## Verification contract

- Four genuine unique palette tuples; all transition ridge roles differ from their binary neighbor.
- Day/night exact class strings pinned.
- All eight literal transition utilities consumed by the component are emitted in production CSS: two named sky images and six ridge fills. The six sky color roles are compiled into the named images rather than emitted as unused standalone classes.
- Focused deterministic matrix/component tests, token lint/parity, TypeScript, build, Storybook, and `git diff --check` green.
- Three inspected LostPixel baselines at 768/1024/1280; fresh scoped rerun reports zero difference.
- Generated diptych remains documentation-only and has no application import.
- The local accessibility wrapper is not evidence for this cycle: it exited zero while all 41 audited stories failed to load, and it did not include Daypart Fidelity. Its generated report was discarded. Accessibility qualification therefore remains the exact-head remote axe check; the changed scene remains `aria-hidden` and no story captions or semantic text changed.

## Reversal condition

Retune individual values only when the same fixed-viewport proof shows ridge collapse, lost horizon atmosphere, or reading/chrome contrast regression. A continuous time-interpolated palette, animated sky, or runtime-generated scene requires a new spec and authority review.
