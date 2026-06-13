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

        // Reserved-use accents (sparingly — never substitute for sun)
        aurora: "#16C2C2",
        // S11 a11y: previous #E33C2D × white text gave 4.24:1 (below
        // WCAG AA 4.5:1 for small text). Darkened to #CE3623 → 4.51:1.
        // Visual delta is ~5% red saturation — brand-acceptable.
        emperor: "#CE3623",
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
    },
  },
  plugins: [],
};
