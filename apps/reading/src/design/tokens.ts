/**
 * Antiek design tokens: "paper, ink, and one sun".
 *
 * The TS mirror of src/design/tokens.css. Three layers, as in the CSS:
 *
 *   primitive  theme-invariant palette (the sun, fixed ink/paper, the night ramp)
 *   semantic   what a colour is FOR, per theme: bgPage, text3, focus…
 *   legacy     the older exports (surface, rule, inkMute, accent…), now derived
 *              from `semantic` so a canvas painting `surface.day[2]` paints the
 *              same page colour the CSS does.
 *
 * token-parity.test.ts asserts every semantic value here equals the resolved
 * value in tokens.css for both themes; tokens.contrast.test.ts computes every
 * text/background and UI pair from THIS module (no contrast figure in a
 * comment is trusted; the test is the number).
 */

export type Mode = "day" | "night";
export type Theme = "light" | "dark";

/** Theme-invariant palette. Mirrors tokens.css section 1. */
export const primitive = {
  sun: "#F5DF24",
  sunHover: "#F6E33C",
  sunPress: "#EFD80B",
  fixedInk: "#0F1419",
  fixedInk2: "#384858",
  fixedPaper: "#FFFFFF",
  dangerFill: "#B82E1C",
  void: "#040508",
  space1: "#080A10",
  space2: "#0D1019",
  charcoal1: "#13171F",
  charcoal2: "#1B202A",
  slate1: "#252B36",
  slate2: "#323845",
  moonlight: "#858F9F",
  starlight: "#C4CCD7",
  bright: "#EEF1F6",
} as const;

export type SemanticTokens = {
  bgPage: string;
  bgCard: string;
  bgInset: string;
  borderHairline: string;
  borderRule: string;
  text1: string;
  text2: string;
  text3: string;
  sunInk: string;
  sunDeep: string;
  keycapEdge: string;
  teal: string;
  aurora: string;
  danger: string;
  success: string;
  stale: string;
  notRun: string;
  focus: string;
  wash: string;
};

/**
 * The semantic layer, per theme. Day is PAPER; the `light` object is the one
 * place to edit to change the day ground (glacial return values are listed in
 * tokens.css). Mirrors tokens.css sections 2 / 2b.
 */
export const semantic: Record<Theme, SemanticTokens> = {
  light: {
    bgPage: "#FBF9F4",
    bgCard: "#FFFEFB",
    bgInset: "#F4F1E8",
    borderHairline: "#E6E0D2",
    borderRule: "#8A8473",
    text1: primitive.fixedInk,
    text2: "#4F5F70",
    text3: "#5F6B79",
    sunInk: "#75620F",
    sunDeep: "#9C8636",
    keycapEdge: primitive.fixedInk,
    teal: "#0B7A7A",
    aurora: "#16C2C2",
    danger: primitive.dangerFill,
    success: "#237242",
    stale: "#8A5A00",
    notRun: "#5B4BB7",
    focus: primitive.fixedInk,
    wash: "rgba(15,20,25,0.06)",
  },
  dark: {
    bgPage: primitive.space2,
    bgCard: primitive.charcoal2,
    bgInset: primitive.charcoal1,
    borderHairline: "#262C38",
    borderRule: "#6A7689",
    text1: primitive.bright,
    text2: "#9AA3B2",
    text3: primitive.moonlight,
    sunInk: primitive.sun,
    sunDeep: "#84722F",
    keycapEdge: "#84722F",
    teal: "#3FE0DC",
    aurora: "#3FE0DC",
    danger: "#FF6155",
    success: "#6ECB8F",
    stale: "#E0A84A",
    notRun: "#A99BFF",
    focus: primitive.sun,
    wash: "rgba(238,241,246,0.08)",
  },
} as const;

const L = semantic.light;
const D = semantic.dark;

/**
 * The brand. `base` is the constant (bottom tab, Brain bill, primary fill);
 * `deep` is the weathered ochre EDGE (>= 3:1 as a line); text in the brand
 * colour uses `semantic.*.sunInk`, never `deep` (3.3:1 as text).
 */
export const sun = {
  base: primitive.sun,
  hover: primitive.sunHover,
  press: primitive.sunPress,
  deep: { day: L.sunDeep, night: D.sunDeep },
  glow: { day: "#F1E08F", night: "#F2DE9A" },
  highlight: {
    faint: "rgba(232,217,140,0.18)", // model-suggested highlights
    day: "rgba(232,217,140,0.45)", // operator highlighter, day
    night: "rgba(242,222,154,0.30)", // operator highlighter, night (== glow.night rgb)
  },
} as const;

/** The weathered "light" sun family (AMS-SPR-09). Theme-invariant. */
export const sunLight = {
  base: "#E8D98C",
  soft: "#F0E6B8",
  deep: L.sunDeep, // one weathered ochre, two names
} as const;

/** The meaningful boundary line (fields, keycap edges, tables). */
export const rule = { day: L.borderRule, night: D.borderRule } as const;

/** The bottom-bar accent. Stays LOUD in both themes (AMS-SPR-09). */
export const barAccent = { day: primitive.sun, night: "#FFEC5F" } as const;

/** The media well: dark in both themes so letterboxed media recedes. */
export const mediaWell = { day: primitive.charcoal2, night: primitive.void } as const;

/**
 * Glass surfaces over the scene. `bgSolid` is the opaque reduced-motion /
 * no-scene fallback (== the card). Body text over glass must keep AA 4.5:1;
 * the consumer adds a scrim when the scene is busy (see GlassSurface).
 */
export const glass = {
  day: {
    bg: "rgba(255,254,251,0.72)", // bgCard @ 0.72
    bgSolid: L.bgCard,
    border: "rgba(15,20,25,0.12)", // fixed ink @ 0.12
    blur: "12px",
  },
  night: {
    bg: "rgba(27,32,42,0.66)", // charcoal-2 @ 0.66
    bgSolid: D.bgCard,
    border: "rgba(238,241,246,0.14)", // bright @ 0.14
    blur: "12px",
  },
} as const;

/**
 * The 10-step ramps the canvases index into, now DERIVED from the semantic
 * layer (they used to hold their own glacial hexes). Index meaning is
 * unchanged: day [0] card … [2] page … [9] ink; night [2] page, [4] card,
 * [7] muted text, [9] bright.
 */
export const surface: Record<Mode, readonly string[]> = {
  day: [
    L.bgCard, // 0  ice-0      card face
    L.bgCard, // 1  ice-1      card
    L.bgPage, // 2  ice-2      page
    L.bgInset, // 3  ice-3      inset / well
    L.borderHairline, // 4  ice-4      hairline band
    L.borderHairline, // 5  glacial-1
    L.borderRule, // 6  glacial-2
    L.text2, // 7  shadow-1   secondary text
    primitive.fixedInk2, // 8  shadow-2   low-emphasis ink (fixed)
    primitive.fixedInk, // 9  ink
  ],
  night: [
    primitive.void, // 0
    primitive.space1, // 1
    primitive.space2, // 2  page
    primitive.charcoal1, // 3  inset
    primitive.charcoal2, // 4  card
    primitive.slate1, // 5
    primitive.slate2, // 6
    primitive.moonlight, // 7  muted text (== night text-3)
    primitive.starlight, // 8
    primitive.bright, // 9
  ],
} as const;

/** Named aliases over the ramp (legacy shape; values from `semantic`). */
export type SurfaceAliases = {
  page: string;
  card: string;
  cardSoft: string;
  inset: string;
  divider: string;
  muted: string;
  textMuted: string;
  text: string;
  border: string;
};

export function aliasFor(m: Mode): SurfaceAliases {
  const s = m === "day" ? L : D;
  return {
    page: s.bgPage,
    card: s.bgCard,
    cardSoft: s.bgPage,
    inset: s.bgInset,
    divider: s.borderHairline,
    muted: s.text3,
    textMuted: s.text2,
    text: s.text1,
    border: s.borderRule,
  };
}

/** Legacy muted-text keys, now the semantic roles: ink-soft = text-2, ink-mute = text-3. */
export const inkSoft = { day: L.text2, night: D.text2 } as const;
export const inkMute = { day: L.text3, night: D.text3 } as const;

/** Chunky offset shadows: ink-cast by day, sun-deep-cast by night. */
export const shadow = {
  day: {
    z1: "3px 3px 0 0 #0F1419",
    z2: "5px 5px 0 0 #0F1419",
    z3: "8px 8px 0 0 #0F1419",
    lift: "12px 12px 0 0 #0F1419",
  },
  night: {
    z1: "3px 3px 0 0 #84722F",
    z2: "5px 5px 0 0 #84722F",
    z3: "8px 8px 0 0 #84722F",
    lift: "12px 12px 0 0 #84722F",
  },
} as const;

export type ShadowKey = keyof (typeof shadow)["day"];

/** Brain mascot palette. Bill + feet lock to the sun. */
export const mascot = {
  day: {
    coat: primitive.fixedInk,
    belly: "#FBFCFD",
    bill: sun.base,
    foot: sun.base,
    eye: primitive.fixedInk,
  },
  night: {
    coat: "#0A0D14",
    belly: "#DCE2EA",
    bill: sun.base,
    foot: sun.base,
    eye: "#DCE2EA",
  },
} as const;

/** Exactly the four moods the restraint rule permits. */
export type MascotMood = "idle" | "thinking" | "empty" | "celebrate";

/**
 * Reserved accents. `aurora` is the AI-cognition FILL (never text: 2.2:1 on
 * paper; text uses `teal`). `emperor` is danger (one red, one name).
 */
export const accent = {
  aurora: { day: L.aurora, night: D.aurora },
  emperor: { day: L.danger, night: D.danger },
} as const;

/** Danger: the emperor alias (same object, so the two can never drift). */
export const danger = accent.emperor;

/** Done / met / passed / VERIFIED. */
export const success = { day: L.success, night: D.success } as const;

/**
 * Research + honesty states: semantic ALIASES (var() references), mirrored by
 * tokens.css section 3. Each resolves to a colour that reads as TEXT in both
 * themes, so one token serves the dot and the label; a state always carries a
 * word (and an icon), never colour alone.
 */
export const state = {
  working: "var(--sun-ink)",
  blocked: "var(--danger)",
  done: "var(--success)",
  stopped: "var(--text-2)",
  muted: "var(--text-3)",
  verified: "var(--success)",
  conflicting: "var(--danger)",
  stale: "var(--stale)",
  notRun: "var(--not-run)",
} as const;

/**
 * Motion scale (U-05). `base` is also Tailwind's DEFAULT transition, so a
 * bare `transition` utility runs on the token, not on Tailwind's constant.
 */
export const motion = {
  duration: {
    fast: "80ms", // press
    base: "150ms", // hover / colour
    slow: "800ms", // signature-beat ceiling (== Brain celebrate)
  },
  easing: {
    standard: "cubic-bezier(0.4, 0, 0.2, 1)", // interaction default
    enter: "cubic-bezier(0, 0, 0.2, 1)", // arriving elements
  },
} as const;

export type MotionDuration = keyof typeof motion.duration;
export type MotionEasing = keyof typeof motion.easing;

/** Pitch family (AI Role Lineup): day grass, night deep turf. */
export const pitch = {
  day: { base: "#4C8F4F", mid: "#3D7A41", deep: "#2F6633" },
  night: { base: "#2E5C33", mid: "#244A29", deep: "#1B3A20" },
} as const;

export const radius = { sm: "4px", md: "6px", lg: "10px" } as const;

/** The brand outline thickness used on every Lemon primitive. */
export const edgeWidth = "2.5px" as const;

/**
 * Three faces, one job each. Inter (interface) and JetBrains Mono (data,
 * provenance) ship as self-hosted woff2; the fallbacks name installed faces
 * so a missing file never lands on Courier. Charter is the reading face.
 */
export const type = {
  sans: '"Inter", "Inter Fallback", system-ui, -apple-system, "Segoe UI", sans-serif',
  mono: '"JetBrains Mono", "JetBrains Mono Fallback", ui-monospace, "SF Mono", SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace',
  serif: '"Charter", "Iowan Old Style", "Source Serif 4", Georgia, serif',
} as const;

/**
 * Link Monster — Weirdmageddon incinerator palette (feature-scoped).
 *
 * Source: docs/specs/link-monster-art-direction.md §2 (Krea-profiled,
 * Gravity Falls Weirdmageddon + industrial-incinerator). Feature-scoped:
 * these tokens are consumed ONLY by the /link-monster furnace stage
 * (monsterSketch.ts canvas + LinkMonster.css chrome). Sibling invariant:
 * every value is byte-identical to the --lm-* block in tokens.css.
 */
export const linkMonster = {
  skyDeep: "#1A0A0F",       // apocalypse crimson (sky base)
  skyMid: "#3D0C28",        // rift magenta (sky mid)
  horizon: "#FF6B2B",       // ember amber (horizon glow)
  fur: "#1E4D8C",           // cerulean pelt (monster body)
  furShadow: "#0B1D3A",     // deep abyss (fur shadow)
  rim: "#00FFD4",           // electric cyan (blacklight rim)
  fireCore: "#FFFBE6",      // white-hot core
  fireMid: "#FF7A18",       // molten orange
  fireOuter: "#E81E0D",     // inferno red
  steel: "#3A3D42",         // gunmetal (grate teeth)
  nickel: "#8B9099",        // brushed nickel (bevel highlight)
  node: "#22D3A7",          // cosmic teal (graph nodes)
  edge: "#B266FF",          // plasma violet (graph edges)
  runeGlow: "#7FFF00",      // toxic green (rune glow)
  runeBase: "#D4E8D0",      // pale sage (rune base)
  ember: "#FFB347",         // data ember (particles)
  voidBlack: "#0A0A12",     // void black (UI panels)
  smoke: "#2A2D35",         // chimney smoke
  magenta: "#FF00FF",       // neon magenta (accents)
  boneWhite: "#E8E0D8",     // bone white (text)
} as const;

export type LinkMonsterToken = keyof typeof linkMonster;
