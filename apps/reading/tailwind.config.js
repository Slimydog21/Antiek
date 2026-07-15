/** @type {import('tailwindcss').Config} */
// Antiek design tokens — Werner brand.
// Sun-yellow outlining WAS the brand default border; AMS-SPR-01 retuned the
// DEFAULT border to a calm neutral "light" rule while keeping sun as the
// Werner + bottom-bar accent. Day = layered off-whites + glacials. Night =
// ten-layer off-black "majestic night sky".
// Source of truth: src/design/tokens.ts (+ tokens.css for the rgba/var tokens).
// Keep these in sync — every value carrying an AMS-SPR-01 note mirrors one there.

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "media", // honours prefers-color-scheme
  theme: {
    extend: {
      colors: {
        // THE brand — invariant across modes
        sun: "#F5DF24",
        // Re-toned sun family (AMS-SPR-09 / CFEEL-FIX-1). These were the OLD
        // loud hexes (sun-deep #B89A00, sun-glow #FCE85E) AFTER tokens.css /
        // tokens.ts had already been re-toned to the weathered values — a
        // HIGH-severity token drift ("lived feel ≠ designed feel"): the ~45
        // utility consumers rendered the old loud values on screen. FIX: point
        // these keys at the CSS vars so they resolve through tokens.css and
        // cascade per theme automatically — day --sun-deep #9C8636 / night
        // #84722F, day --sun-glow #F1E08F / night #F2DE9A. This is strictly
        // MORE correct than a static day hex: several consumers (text-sun-deep
        // in VoiceToDraft / FloatMenu / ResearchPanel) carry NO dark: override,
        // so a static day hex would render the day ochre even at night; the
        // var resolves to the night token there. And the drift can never recur
        // — there is now ONE value, in tokens.css, the parity guard asserts.
        // Mirror: tokens.ts `sun.deep`/`sun.glow`, tokens.css --sun-deep/--sun-glow.
        "sun-deep": "var(--sun-deep)",
        "sun-glow": "var(--sun-glow)",

        // Neutral "light" chrome border (AMS-SPR-01). Was the default border
        // = sun #F5DF24; the operator asked to "replace that yellowness with
        // light." Day hex mirrors tokens.ts `rule.day` + tokens.css --rule
        // (#788596 — a calm blue-grey; the lightest neutral that still clears
        // WCAG 3:1 on white cards). Tailwind cannot media-swap a single color
        // key, so border-rule renders this day hex statically; night is
        // delivered via the CSS var (var(--border)/var(--rule) → #606C7E) on
        // elements that read it, and components carry an explicit
        // dark:border-charcoal-1 override. Keep in sync with tokens.ts/.css.
        rule: "#788596",

        // Preserved bottom-bar yellow accent (AMS-SPR-01; SPR-06 paints the
        // bar with this). Resolves to the brand lemon. Mirrors tokens.ts
        // `barAccent.day` + tokens.css --bar-accent. Night warmer glow is
        // delivered via var(--bar-accent) (#FFEC5F) for var-driven consumers.
        "bar-accent": "#F5DF24",

        // Glass surfaces (AMS-SPR-01; SPR-03/04/09). Inherently mode-dependent
        // rgba, so bg-glass / border-glass are wired to the CSS vars
        // (tokens.css) rather than a static hex — they track day + night
        // automatically. The contrast/scrim legibility contract lives in
        // tokens.ts `glass`.
        glass: "var(--glass-bg)",
        "glass-solid": "var(--glass-bg-solid)",

        // Day surface ramp (off-whites + glacials)
        "ice-0": "#FFFFFF",
        "ice-1": "#FBFCFD",
        "ice-2": "#F4F7FA",
        "ice-3": "#EAEFF4",
        "ice-4": "#DCE5ED",
        "glacial-1": "#C2D1DD",
        "glacial-2": "#9AB0C0",
        // shadow-1 was #64778A → 4.59:1 on white; opacity-blended
        // descendants (panels with 95% opacity) dropped to 4.17 +
        // failed the a11y audit. Darkened to #4F5F70 → 6.32:1 on
        // white, ~5.4:1 even with 95% panel opacity. Brand-acceptable;
        // the visual difference is one Munsell step darker.
        "shadow-1": "#4F5F70",
        "shadow-2": "#384858",
        ink: "#0F1419",

        // Night surface ramp (off-blacks + dark greys — majestic night sky)
        void: "#040508",
        "space-1": "#080A10",
        "space-2": "#0D1019",
        "charcoal-1": "#13171F",
        "charcoal-2": "#1B202A",
        "slate-1": "#252B36",
        "slate-2": "#323845",
        moonlight: "#6B7585",
        starlight: "#C4CCD7",
        bright: "#EEF1F6",

        // Scene transition palette (ATP-01) — dawn/dusk atmospheric tokens.
        // These mirror tokens.css --scene-* vars; ProceduralSky consumes them.
        "scene-dawn-top": "var(--scene-dawn-top)",
        "scene-dawn-mid": "var(--scene-dawn-mid)",
        "scene-dawn-horizon": "var(--scene-dawn-horizon)",
        "scene-dawn-ridge-far": "var(--scene-dawn-ridge-far)",
        "scene-dawn-ridge-mid": "var(--scene-dawn-ridge-mid)",
        "scene-dawn-ridge-near": "var(--scene-dawn-ridge-near)",
        "scene-dusk-top": "var(--scene-dusk-top)",
        "scene-dusk-mid": "var(--scene-dusk-mid)",
        "scene-dusk-horizon": "var(--scene-dusk-horizon)",
        "scene-dusk-ridge-far": "var(--scene-dusk-ridge-far)",
        "scene-dusk-ridge-mid": "var(--scene-dusk-ridge-mid)",
        "scene-dusk-ridge-near": "var(--scene-dusk-ridge-near)",

        // Reserved-use accents (sparingly — never substitute for sun)
        aurora: "#16C2C2",
        // S11 a11y: previous #E33C2D × white text gave 4.24:1 (below
        // WCAG AA 4.5:1 for small text). Darkened to #CE3623 → 4.51:1.
        // Visual delta is ~5% red saturation — brand-acceptable.
        emperor: "#CE3623",
      },
      backgroundImage: {
        // Authored transition skies. The horizon arrives before the 70% mark
        // so it remains visible above the unchanged ridge silhouettes instead
        // of being buried at the bottom edge of the plate.
        "scene-dawn-sky":
          "linear-gradient(to bottom, var(--scene-dawn-top) 0%, var(--scene-dawn-mid) 36%, var(--scene-dawn-horizon) 70%)",
        "scene-dusk-sky":
          "linear-gradient(to bottom, var(--scene-dusk-top) 0%, var(--scene-dusk-mid) 36%, var(--scene-dusk-horizon) 70%)",
      },
      boxShadow: {
        // Day: ink-cast chunky offset
        z1: "3px 3px 0 0 #0F1419",
        z2: "5px 5px 0 0 #0F1419",
        z3: "8px 8px 0 0 #0F1419",
        lift: "12px 12px 0 0 #0F1419",
        // Night: sun-deep-cast glow. Every consumer applies these only behind a
        // `dark:` variant (dark:shadow-z1-night …), so they fire ONLY in the
        // night subtree where --sun-deep cascades to the night value #84722F.
        // The cast colour was the OLD loud #8A7300 here AFTER tokens.css /
        // tokens.ts had re-toned the night cast to the weathered #84722F
        // (AMS-SPR-09) — the same drift as the sun-deep/glow keys. FIX: read
        // var(--sun-deep), byte-identical to how tokens.css --shadow-z* read it
        // (tokens.css:251-254), so these never drift from the night shadow
        // again. Mirror: tokens.ts `shadow.night` (#84722F).
        "z1-night": "3px 3px 0 0 var(--sun-deep)",
        "z2-night": "5px 5px 0 0 var(--sun-deep)",
        "z3-night": "8px 8px 0 0 var(--sun-deep)",
        "lift-night": "12px 12px 0 0 var(--sun-deep)",
      },
      borderColor: {
        // Default border = neutral "light" rule (AMS-SPR-01). Was the brand
        // sun #F5DF24; re-pointed to rule #788596 so the everywhere-border
        // reads calm and neutral, not bold yellow. Mirrors tokens.ts
        // `rule.day` + tokens.css --rule. Night (#606C7E) is delivered via
        // the CSS var on var(--border) consumers + dark:border-charcoal-1.
        DEFAULT: "#788596",
        // Explicit border-rule utility (mirror of colors.rule, day hex).
        rule: "#788596",
        // Translucent glass hairline (mode-tracking via the CSS var).
        glass: "var(--glass-border)",
      },
      borderWidth: {
        edge: "2.5px",
      },
      // Glass backdrop blur (AMS-SPR-01; SPR-03/04/09 use backdrop-blur-glass).
      // Mirrors tokens.css --glass-blur + tokens.ts `glass.*.blur` (12px).
      backdropBlur: {
        glass: "12px",
      },
      borderRadius: {
        hog: "6px",
        "hog-lg": "10px",
      },
      // Motion scale (U-05) — the named durations + easings the base
      // interactions use, so `duration-fast/base/slow` replace magic
      // `duration-75` numbers. Source of truth: src/design/motion.ts.
      transitionDuration: {
        fast: "80ms", // press
        base: "150ms", // hover / colour
        slow: "800ms", // signature-beat ceiling
      },
      transitionTimingFunction: {
        standard: "cubic-bezier(0.4, 0, 0.2, 1)",
        enter: "cubic-bezier(0, 0, 0.2, 1)",
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        // Tighter monospace for trajectory data; reading text stays default sans.
        mono: ['"JetBrains Mono"', "ui-monospace", "SFMono-Regular", "monospace"],
        serif: ["Charter", '"Iowan Old Style"', "Georgia", "serif"],
      },

      // Density-overridable spacing scale (CFEEL-S2 M1) — PostHog/Quill pattern.
      // Every value is `calc(var(--spacing) * <key>)`, so the WHOLE scale scales
      // with the single --spacing var (default 0.25rem in tokens.css). This
      // REPLACES Tailwind's default spacing scale, so it MUST enumerate every
      // default key or that utility silently disappears (a regression). It is
      // provably non-regressive on the default surface: Tailwind's default for
      // key N is (N/4)rem, and calc(0.25rem * N) == (N/4)rem for every N, so
      // p-4/gap-2/m-1/… resolve byte-identically to today. The literal `0px` /
      // `1px` for the `0` / `px` keys match Tailwind (a 0-multiplier calc would
      // also be 0, but the literals keep those two pixel-exact + readable). A
      // subtree can tighten ALL of this by setting [data-density] (tokens.css).
      // Source of the multiplier rule: spacing[N] === (N/4)rem in Tailwind's
      // defaultTheme; verified against tailwindcss/defaultTheme.
      spacing: {
        0: "0px",
        px: "1px",
        0.5: "calc(var(--spacing) * 0.5)", // 0.125rem
        1: "calc(var(--spacing) * 1)", // 0.25rem
        1.5: "calc(var(--spacing) * 1.5)", // 0.375rem
        2: "calc(var(--spacing) * 2)", // 0.5rem
        2.5: "calc(var(--spacing) * 2.5)", // 0.625rem
        3: "calc(var(--spacing) * 3)", // 0.75rem
        3.5: "calc(var(--spacing) * 3.5)", // 0.875rem
        4: "calc(var(--spacing) * 4)", // 1rem
        5: "calc(var(--spacing) * 5)", // 1.25rem
        6: "calc(var(--spacing) * 6)", // 1.5rem
        7: "calc(var(--spacing) * 7)", // 1.75rem
        8: "calc(var(--spacing) * 8)", // 2rem
        9: "calc(var(--spacing) * 9)", // 2.25rem
        10: "calc(var(--spacing) * 10)", // 2.5rem
        11: "calc(var(--spacing) * 11)", // 2.75rem
        12: "calc(var(--spacing) * 12)", // 3rem
        14: "calc(var(--spacing) * 14)", // 3.5rem
        16: "calc(var(--spacing) * 16)", // 4rem
        20: "calc(var(--spacing) * 20)", // 5rem
        24: "calc(var(--spacing) * 24)", // 6rem
        28: "calc(var(--spacing) * 28)", // 7rem
        32: "calc(var(--spacing) * 32)", // 8rem
        36: "calc(var(--spacing) * 36)", // 9rem
        40: "calc(var(--spacing) * 40)", // 10rem
        44: "calc(var(--spacing) * 44)", // 11rem
        48: "calc(var(--spacing) * 48)", // 12rem
        52: "calc(var(--spacing) * 52)", // 13rem
        56: "calc(var(--spacing) * 56)", // 14rem
        60: "calc(var(--spacing) * 60)", // 15rem
        64: "calc(var(--spacing) * 64)", // 16rem
        72: "calc(var(--spacing) * 72)", // 18rem
        80: "calc(var(--spacing) * 80)", // 20rem
        96: "calc(var(--spacing) * 96)", // 24rem
      },

      // App type-scale tokens + 24px chrome ceiling (CFEEL-S2 M2) — PostHog's
      // named app type scale. ADDS named keys (does not remove Tailwind's
      // defaults, which some components still use); each is [font-size,
      // line-height]. The 2xl == 24px is the CHROME CEILING: no in-app chrome
      // text should exceed it (reading-body/content is exempt — that's content,
      // not chrome). lint_type_scale.ts enforces the ceiling on chrome.
      fontSize: {
        xxs: ["10px", "12px"],
        xs: ["12px", "16px"],
        sm: ["14px", "20px"],
        base: ["16px", "24px"],
        lg: ["18px", "28px"],
        xl: ["20px", "28px"],
        "2xl": ["24px", "32px"], // chrome ceiling — the largest chrome size
      },

      // Opacity tokens (CFEEL-S2 M3) — PostHog's disabled/icon dim constants as
      // utilities (opacity-disabled / opacity-icon), each reading the CSS var so
      // a dimmed control is one token, not a scattered magic 0.65/0.8.
      opacity: {
        disabled: "var(--opacity-disabled)",
        icon: "var(--opacity-icon)",
      },
    },
  },
  plugins: [],
};
