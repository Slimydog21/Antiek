/** @type {import('tailwindcss').Config} */
// Antiek design tokens: "paper, ink, and one sun".
//
// Every colour key resolves to a CSS variable in src/design/tokens.css (the
// single source of truth); none holds a hex. Keys that take an /opacity
// modifier read the channel triplet: rgb(var(--x-rgb) / <alpha-value>).
// check_token_parity.ts fails the build if a key ever holds a literal again.
//
// Theme: `dark:` is driven by <html data-theme="dark">, which index.html sets
// before first paint from the stored preference (light | dark | system).
//
// Legacy keys keep their names and point at the semantic layer, so no call
// site needs a rewrite. Where one key had two jobs, the per-utility maps below
// split it: `text-sun-deep` is the brand as TEXT (--sun-ink) while
// `border-sun-deep` stays the weathered edge; `text-aurora` is teal while
// `bg-aurora` stays the AI-cognition fill; `bg-emperor` is a white-text-safe
// fill while `text-emperor` is the theme's danger text colour.

import defaultColors from "tailwindcss/colors.js";

/** rgb(var(--<name>-rgb) / <alpha-value>) */
const ch = (name) => `rgb(var(--${name}-rgb) / <alpha-value>)`;

// ice-* as a PIGMENT is paper in both themes: white text on a fill (danger,
// ink, the dark rail, a book spine) and the white of a drawn mark (BrainMark's
// lobes under ink folds, on the sun key). Only bg-ice-* is a surface that
// follows the theme. fill-ice-0 once followed it too, and the brand mark on
// the dock went dark on dark at night (1.13:1).
const icePigment = Object.fromEntries([0, 1, 2, 3, 4].map((n) => [`ice-${n}`, ch("fixed-paper")]));

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: ["selector", '[data-theme="dark"]'],
  // Hover lifts must not stick after a tap on touch screens.
  future: { hoverOnlyWhenSupported: true },
  theme: {
    extend: {
      colors: {
        // ── the brand ─────────────────────────────────────────────
        sun: ch("sun"),
        "sun-hover": ch("sun-hover"),
        "sun-press": ch("sun-press"),
        // The brand as TEXT: day #75620F, night the sun itself.
        "sun-ink": ch("sun-ink"),
        // The weathered ochre EDGE (>= 3:1 as a line). text-sun-deep is
        // remapped to sun-ink in textColor below.
        "sun-deep": ch("sun-deep"),
        "sun-glow": "var(--sun-glow)",
        "sun-light": "var(--sun-light)",
        "sun-light-soft": "var(--sun-light-soft)",
        "sun-light-deep": "var(--sun-light-deep)",
        "bar-accent": ch("bar-accent"),
        "keycap-edge": ch("keycap-edge"),

        // ── semantic surfaces, lines, text ────────────────────────
        page: ch("bg-page"),
        card: ch("bg-card"),
        "card-soft": "var(--card-soft)",
        hairline: ch("border-hairline"),
        rule: ch("border-rule"),
        focus: ch("focus"),
        wash: "var(--wash)",

        // ── legacy day ramp → semantic (follows the theme) ────────
        "ice-0": ch("bg-card"),
        "ice-1": ch("bg-card"),
        "ice-2": ch("bg-page"),
        "ice-3": ch("bg-inset"),
        "ice-4": ch("border-hairline"),
        "glacial-1": ch("border-hairline"),
        "glacial-2": ch("border-rule"),
        // shadow-1 is secondary text (text-2); as a fill it follows too.
        "shadow-1": ch("text-2"),
        // shadow-2 FILLS stay dark in both themes (the hover of an ink
        // button, the dark float menu); its text use is text-2 (below).
        "shadow-2": ch("fixed-ink-2"),
        // ink is the fixed pigment: ink on the sun, ink buttons, the dark
        // rail. It does not flip (text-ink dark:text-bright stays correct).
        ink: ch("fixed-ink"),
        "ink-soft": ch("ink-soft"),
        "ink-mute": ch("ink-mute"),

        // ── states ───────────────────────────────────────────────
        danger: ch("danger"),
        success: ch("success"),
        stale: ch("stale"),
        "not-run": ch("not-run"),
        // Links and evidence. DEFAULT only: Tailwind's teal-50…950 steps
        // stay available (no key disappears).
        teal: { ...defaultColors.teal, DEFAULT: ch("teal") },
        // AI-cognition fill (thinking, emergent outputs). Text → teal.
        aurora: ch("aurora"),
        // One red, one name: emperor is danger.
        emperor: ch("danger"),

        // ── glass + media ─────────────────────────────────────────
        glass: "var(--glass-bg)",
        "glass-solid": "var(--glass-bg-solid)",
        "media-well": "var(--media-well)",

        // ── night ramp: primitives, used under dark: (and on the dark
        //    islands that stay dark in both themes). Their values equal
        //    the night semantic tokens: dark:bg-charcoal-2 is the night
        //    card, dark:text-moonlight is the night text-3 (5.0:1). ──
        void: ch("void"),
        "space-1": ch("space-1"),
        "space-2": ch("space-2"),
        "charcoal-1": ch("charcoal-1"),
        "charcoal-2": ch("charcoal-2"),
        "slate-1": ch("slate-1"),
        "slate-2": ch("slate-2"),
        moonlight: ch("moonlight"),
        starlight: ch("starlight"),
        bright: ch("bright"),
      },
      // Per-utility splits: a key whose TEXT job differs from its fill/edge job.
      textColor: {
        "1": ch("text-1"),
        "2": ch("text-2"),
        "3": ch("text-3"),
        "sun-deep": ch("sun-ink"),
        aurora: ch("teal"),
        "shadow-2": ch("text-2"),
        starlight: ch("text-2"),
        ...icePigment,
      },
      fill: icePigment,
      stroke: icePigment,
      backgroundColor: {
        inset: ch("bg-inset"),
        // bg-emperor is a FILL under white text: 5.03:1 in both themes.
        emperor: ch("danger-fill"),
      },
      borderColor: {
        DEFAULT: ch("border-rule"),
        rule: ch("border-rule"),
        // 442 dark:border-charcoal-1 call sites meant "the night rule";
        // they now get it (3.55:1 on the night card, was 1.10:1).
        "charcoal-1": ch("border-rule"),
        aurora: ch("teal"),
        glass: "var(--glass-border)",
      },
      boxShadow: {
        // Day: cast in the fixed ink (#0F1419)
        z1: "3px 3px 0 0 var(--fixed-ink)",
        z2: "5px 5px 0 0 var(--fixed-ink)",
        z3: "8px 8px 0 0 var(--fixed-ink)",
        lift: "12px 12px 0 0 var(--fixed-ink)",
        // Night: cast in var(--sun-deep) (night value #84722F). Applied only
        // behind dark:, byte-identical to tokens.css --shadow-z*.
        "z1-night": "3px 3px 0 0 var(--sun-deep)",
        "z2-night": "5px 5px 0 0 var(--sun-deep)",
        "z3-night": "8px 8px 0 0 var(--sun-deep)",
        "lift-night": "12px 12px 0 0 var(--sun-deep)",
      },
      borderWidth: {
        edge: "2.5px",
      },
      backdropBlur: {
        glass: "12px",
      },
      borderRadius: {
        hog: "6px",
        "hog-lg": "10px",
      },
      // Motion scale (U-05). DEFAULT makes a bare `transition` /
      // `transition-colors` run on the token, not on Tailwind's constant.
      transitionDuration: {
        DEFAULT: "var(--motion-base)",
        fast: "80ms", // press
        base: "150ms", // hover / colour
        slow: "800ms", // signature-beat ceiling
      },
      transitionTimingFunction: {
        DEFAULT: "var(--ease-standard)",
        standard: "cubic-bezier(0.4, 0, 0.2, 1)",
        enter: "cubic-bezier(0, 0, 0.2, 1)",
      },
      // The z ladder (src/design/zIndex.ts == tokens.css --z-*).
      zIndex: {
        raised: "var(--z-raised)",
        window: "var(--z-window)",
        mascot: "var(--z-mascot)",
        modal: "var(--z-modal)",
        popover: "var(--z-popover)",
        "ad-overlay": "var(--z-ad-overlay)",
        toast: "var(--z-toast)",
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "-apple-system", '"Segoe UI"', "sans-serif"],
        mono: [
          '"JetBrains Mono"',
          "ui-monospace",
          '"SF Mono"',
          "SFMono-Regular",
          "Menlo",
          "Consolas",
          '"Liberation Mono"',
          "monospace",
        ],
        serif: ["Charter", '"Iowan Old Style"', '"Source Serif 4"', "Georgia", "serif"],
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
        // 11px is the legibility floor (PostHog's smallest step); 10px retired.
        xxs: ["11px", "16px"],
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
