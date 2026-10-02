# `src/design/` — design-system source of truth

Single source of truth for Antiek's visual tokens: "paper, ink, and one sun".
Day is warm paper, night the off-black sky, the sun (`#F5DF24`) the one brand
fill. See DESIGN_LANGUAGE.md "Canonical tokens" for the semantic layer.

## Files

- `tokens.ts` — canonical palette / shadow / type / radius constants. Imported
  by every component that needs a colour or shadow constant outside the
  Tailwind class system.
- `tokens.css` — the runtime source of truth: primitives, the semantic layer
  (day in `:root`, night in `[data-theme="dark"]` + a no-JS fallback), legacy
  aliases, the z ladder.
- `theme.ts` / `useTheme.ts` — theme (light/dark/system) and motion
  preferences: the React side of the `index.html` pre-paint boot script.
- `tokenCss.ts` — parses tokens.css like the browser does, for the gates.
- `elevation.ts` — stack depth → `shadow-z*` tiers + cascade offsets (PostHog
  Feel programme). See `FEEL_CONTRACT.md`.
- `FEEL_CONTRACT.md` — dual-store chrome modes (opaque-chunky vs glass-scene).
- `moodboard.stories.tsx` — visual gate; operator-signed.
- `Elevation.stories.tsx` — opaque vs glass reference swatches.

## Rules

1. **No component imports a colour or hex from anywhere else.** Every
   colour reference goes through `tokens.ts` or a Tailwind class.
2. Every `tailwind.config.js` colour key resolves to a tokens.css var, and
   tokens.ts `semantic` equals tokens.css per theme: `check_token_parity.ts`
   and `token-parity.test.ts` enforce both.
3. Palette ratification flows through this directory only.

## Full spec

See `docs/ui_redesign_posthog/sprint_00_foundations.html`
and `docs/ui_redesign_posthog/brand_werner.html`.
