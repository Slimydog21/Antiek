/** @type {import('tailwindcss').Config} */
// Antiek design tokens — Werner brand.
// Sun-yellow outlining is the brand constant. Day = layered off-whites +
// glacials. Night = ten-layer off-black "majestic night sky".
// Source of truth: src/design/tokens.ts. Keep these in sync.

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "media", // honours prefers-color-scheme
  theme: {
    extend: {
      colors: {
        // THE brand — invariant across modes
        sun: "#F5DF24",
        "sun-deep": "#B89A00",
        "sun-glow": "#FCE85E",

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
        // Night: sun-deep-cast glow
        "z1-night": "3px 3px 0 0 #8A7300",
        "z2-night": "5px 5px 0 0 #8A7300",
        "z3-night": "8px 8px 0 0 #8A7300",
        "lift-night": "12px 12px 0 0 #8A7300",
      },
      borderColor: {
        // The brand outline is the default border colour
        DEFAULT: "#F5DF24",
      },
      borderWidth: {
        edge: "2.5px",
      },
      borderRadius: {
        hog: "6px",
        "hog-lg": "10px",
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
