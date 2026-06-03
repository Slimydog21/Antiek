# `src/design/` — design-system source of truth

Single source of truth for Antiek's visual tokens. **Werner brand**: sun-yellow
outlining (`#F5DF24`) as the constant across day + night modes, layered
off-white + glacial day surfaces, layered off-black + dark-grey night surfaces.

## Files

- `tokens.ts` — canonical palette / shadow / type / radius constants. Imported
  by every component that needs a colour or shadow constant outside the
  Tailwind class system.
- `tokens.css` — CSS-var sibling, for non-TS contexts (Storybook docs).
- `elevation.ts` — stack depth → `shadow-z*` tiers + cascade offsets (PostHog
  Feel programme). See `FEEL_CONTRACT.md`.
- `FEEL_CONTRACT.md` — dual-store chrome modes (opaque-chunky vs glass-scene).
- `moodboard.stories.tsx` — visual gate; operator-signed.
- `Elevation.stories.tsx` — opaque vs glass reference swatches.

## Rules

1. **No component imports a colour or hex from anywhere else.** Every
   colour reference goes through `tokens.ts` or a Tailwind class.
2. `tailwind.config.js` MUST stay in sync with `tokens.ts`. A Vitest in
   S1 enforces this (catches accidental drift).
3. Palette ratification flows through this directory only.

## Full spec

See `docs/ui_redesign_posthog/sprint_00_foundations.html`
and `docs/ui_redesign_posthog/brand_werner.html`.
