/**
 * Antiek design tokens — Werner brand.
 *
 *  sun-yellow outlining is the brand constant.
 *  day mode = layered off-whites + glacials.
 *  night mode = ten-layer off-black "majestic night sky".
 *  Werner's bill + feet match `sun.base` (the visual hook).
 *
 * See:
 *   docs/ui_redesign_posthog/brand_werner.html §5 (sun), §6 (day), §7 (night)
 *   docs/ui_redesign_posthog/sprint_00_foundations.html WP-0.1
 */

export type Mode = "day" | "night";

/** The single brand colour — invariant across modes. */
export const sun = {
  base: "#F5DF24", // sharp esoteric lemon, slightly green-leaning
  deep: { day: "#B89A00", night: "#8A7300" }, // hover / depth / dark-shadow
  glow: { day: "#FCE85E", night: "#FFEC5F" }, // highlight peaks
  highlight: {
    faint: "rgba(245,223,36,0.18)", // model-suggested highlights
    day: "rgba(245,223,36,0.45)", // operator highlighter, day
    night: "rgba(252,232,94,0.30)", // operator highlighter, night
  },
} as const;

/**
 * The default chrome border — neutral "light" (AMS-SPR-01).
 *
 * Was `sun.base` (#F5DF24). The operator called the everywhere-yellow
 * border "a bit too much of a bold yellow" and asked to "replace that
 * yellowness with light." `rule` is that replacement: a calm, low-chroma
 * blue-grey line — neutral, not yellow, and far less assertive than the
 * lemon. Yellow is NOT gone from the brand: it survives as `sun` (Werner
 * bill/feet) and as `barAccent` (the bottom bar). This token only retires
 * yellow from the *default* border role.
 *
 * VALUE CHOICE — the honest contrast/calm tradeoff (rigor #1). The sprint's
 * milestone-1 acceptance requires the new border ≥3:1 against its adjacent
 * surfaces (WCAG 1.4.11 non-text contrast). A truly *pale* line (e.g.
 * #C2CEDA, glacial-1) measures only ~1.6:1 on a white card — it would look
 * "light" but FAIL the floor and effectively vanish, which is worse than the
 * status quo. So `rule` is the LIGHTEST blue-grey that still clears 3:1 on
 * the primary card surfaces, not the palest grey imaginable. Measured (see
 * handoff contrast table for the full grid):
 *   day   #788596 on ice-0 #FFFFFF → 3.75:1 ✓   on ice-1 #FBFCFD → 3.65:1 ✓
 *                  on ice-2 (page) #F4F7FA → 3.49:1 ✓ ; ice-4 divider 2.94 (n/a:
 *                  a border is drawn against card/page faces, not the divider band)
 *   night #606C7E on card #1B202A → 3.07:1 ✓   on space-2 (page) #0D1019 → 3.57:1 ✓
 * It reads calm and neutral next to the old lemon while remaining a definite,
 * accessible line. Where a component wants a high-contrast emphasis edge it
 * should use `ink`/`bright` or `barAccent`, never lean on the default rule.
 */
export const rule = {
  day: "#788596", // calm blue-grey, lightest neutral clearing 3:1 on white cards
  night: "#606C7E", // calm slate, lightest neutral clearing 3:1 on the night card
} as const;

/**
 * The preserved bottom-bar yellow accent (AMS-SPR-01, consumed by SPR-06).
 *
 * The operator kept yellow "in style for the bottom tab." This names that
 * intent so the NavRail/bottom bar can paint with a *semantic* accent token
 * rather than reaching for raw `sun`. It resolves to the sun family in both
 * modes (day = the lemon itself; night = the warmer glow so it reads on the
 * dark sky). Decoupling this from the default border is the deliberate
 * compromise: the brand yellow concentrates on the one surface that should
 * carry it, instead of diffusing across every chrome edge.
 */
export const barAccent = {
  day: sun.base, // #F5DF24 — the brand lemon
  night: sun.glow.night, // #FFEC5F — warmer glow, legible on the night sky
} as const;

/**
 * Glass / transparency surfaces (AMS-SPR-01, consumed by SPR-03/04/09).
 *
 * The mountainscape scene (SPR-04) sits behind the working surfaces; these
 * tokens are the semi-transparent panels + windows that let it show through.
 *
 *   bg          — the translucent panel fill (alpha tuned per mode).
 *   border      — the translucent hairline edge of a glass panel.
 *   blur        — the backdrop-filter blur radius.
 *   bgSolid     — OPAQUE fallback for prefers-reduced-motion / no-scene /
 *                 low-power: identical hue to `bg` at alpha 1 so a panel
 *                 degrades to a flat card without a layout/colour jump.
 *
 * LEGIBILITY CONTRACT (text contrast floor): body text over glass must meet
 * WCAG AA 4.5:1. Glass alone does NOT guarantee that — a busy scene behind
 * can drop effective contrast. The consumer (SPR-03/04/09) MUST place text
 * on a scrim: either (a) raise panel alpha toward `bgSolid`, or (b) add a
 * solid text-backing band. The token layer documents the floor; the scene
 * layer enforces it. Day glass is a near-white frost; night glass a deep
 * slate frost — both chosen so that AT THE STATED ALPHA, body `text`
 * (#0F1419 day / #EEF1F6 night) over the *solid* fallback already clears
 * 4.5:1, leaving the scrim only to recover what scene-bleed costs.
 */
export const glass = {
  day: {
    bg: "rgba(251,252,253,0.72)", // card-soft (#FBFCFD) @ 0.72 — frost over scene
    bgSolid: "#FBFCFD", // opaque fallback == card-soft, no colour jump
    border: "rgba(15,20,25,0.12)", // ink (#0F1419) @ 0.12 — translucent hairline
    blur: "12px", // backdrop-filter blur radius
  },
  night: {
    bg: "rgba(27,32,42,0.66)", // charcoal-2 (#1B202A) @ 0.66 — frost over night sky
    bgSolid: "#1B202A", // opaque fallback == charcoal-2 card
    border: "rgba(238,241,246,0.14)", // bright (#EEF1F6) @ 0.14 — translucent hairline
    blur: "12px",
  },
} as const;

/**
 * 10-step surface ramps. Ordered light → dark for day,
 * void → starlight for night. Background, fill, and divider
 * tones all index into these.
 */
export const surface: Record<Mode, readonly string[]> = {
  day: [
    "#FFFFFF", // 0  ice-0       pure white (top card face, rare)
    "#FBFCFD", // 1  ice-1       default card
    "#F4F7FA", // 2  ice-2       page background
    "#EAEFF4", // 3  ice-3       trough / inset
    "#DCE5ED", // 4  ice-4       divider band
    "#C2D1DD", // 5  glacial-1   subdued surface
    "#9AB0C0", // 6  glacial-2   disabled / muted
    // S11 a11y: darkened from #64778A so opacity-blended descendants
    // still hit WCAG AA 4.5:1 against ice-0/ice-1 backgrounds.
    "#4F5F70", // 7  shadow-1    secondary text
    "#384858", // 8  shadow-2    low-emphasis ink
    "#0F1419", // 9  ink         primary text + hard borders
  ],
  night: [
    "#040508", // 0  void         deepest layer
    "#080A10", // 1  space-1      sub-page
    "#0D1019", // 2  space-2      page background
    "#13171F", // 3  charcoal-1   trough
    "#1B202A", // 4  charcoal-2   card (the "top plane" at night)
    "#252B36", // 5  slate-1      elevated
    "#323845", // 6  slate-2      higher plane
    "#6B7585", // 7  moonlight    muted text
    "#C4CCD7", // 8  starlight    body text
    "#EEF1F6", // 9  bright       headlines
  ],
} as const;

/** Named aliases over the ramp for readability inside components. */
export type SurfaceAliases = {
  page: string;
  card: string;
  cardSoft: string;
  inset: string;
  divider: string;
  muted: string;
  textMuted: string;
  text: string;
  border: string; // ← was always sun; re-pointed to neutral `rule` per AMS-SPR-01
};

export function aliasFor(m: Mode): SurfaceAliases {
  const r = surface[m];
  if (m === "day") {
    return {
      page: r[2],
      card: r[0],
      cardSoft: r[1],
      inset: r[3],
      divider: r[4],
      muted: r[6],
      textMuted: r[7],
      text: r[9],
      border: rule.day, // was sun.base #F5DF24; toned to neutral light per AMS-SPR-01
    };
  }
  return {
    page: r[2],
    card: r[4],
    cardSoft: r[3],
    inset: r[2],
    divider: r[3],
    muted: r[7],
    textMuted: r[7],
    text: r[9],
    border: rule.night, // was sun.base #F5DF24; toned to neutral light per AMS-SPR-01
  };
}

/** Chunky offset shadows: ink-cast on day, sun-deep-glowing on night. */
export const shadow = {
  day: {
    z1: "3px 3px 0 0 #0F1419",
    z2: "5px 5px 0 0 #0F1419",
    z3: "8px 8px 0 0 #0F1419",
    lift: "12px 12px 0 0 #0F1419",
  },
  night: {
    z1: "3px 3px 0 0 #8A7300",
    z2: "5px 5px 0 0 #8A7300",
    z3: "8px 8px 0 0 #8A7300",
    lift: "12px 12px 0 0 #8A7300",
  },
} as const;

export type ShadowKey = keyof (typeof shadow)["day"];

/** Werner mascot palette. Bill + feet lock to sun — the single constant that makes the mark the brand.

   These five drive the canonical <Werner mood="..." /> (U-02). The component renders
   at rail size (28px, mark fidelity) and hero (120px+, character fidelity) from the
   same geometry. Abstract dot rejected: a stranger must call the rail mark "a cute
   penguin" not "a dot". See brand/README.md for the four-slot restraint rule. */
export const werner = {
  day: {
    coat: "#0F1419",
    belly: "#FBFCFD",
    bill: sun.base,
    foot: sun.base,
    eye: "#0F1419",
  },
  night: {
    coat: "#0A0D14",
    belly: "#DCE2EA",
    bill: sun.base,
    foot: sun.base,
    eye: "#DCE2EA",
  },
} as const;

/** Exactly the four moods the restraint rule permits. Used only in the four named
   slots; never mid-content, never more than one on screen. */
export type WernerMood = "idle" | "thinking" | "empty" | "celebrate";

/** Reserved-use accents — use sparingly; never substitute for sun. */
export const accent = {
  aurora: { day: "#16C2C2", night: "#3FE0DC" }, // secondary, AI-thinking states
  // emperor (danger). S11 a11y audit darkened day variant from
  // #E33C2D → #CE3623 so white text hits the WCAG AA 4.5:1 floor.
  emperor: { day: "#CE3623", night: "#FF6155" }, // danger only
} as const;

/**
 * Motion scale (U-05). One small set of durations + easings so motion
 * timing is a token, not a magic number scattered across components.
 *
 * `fast`  — the press: the offset-shadow snap on a button/card tap.
 *           Short enough to read as tactile, not as travel.
 * `base`  — the everyday hover lift + colour/opacity transitions.
 * `slow`  — the ceiling for a signature delight beat. No flourish may
 *           run longer than this; Werner's 800 ms celebrate one-shot
 *           sits under it.
 *
 * `standard` is the default ease for interactions; `enter` (ease-out)
 * for elements arriving. GPU-cheap properties only — transform/opacity.
 * Werner's pose timings (idle 4200 ms, thinking 1200 ms, celebrate
 * 800 ms) live in werner/animated/animations.css and predate this
 * scale; `slow` is set to 800 ms so the celebrate beat is the
 * longest sanctioned flourish rather than an outlier.
 */
export const motion = {
  duration: {
    fast: "80ms", // press
    base: "150ms", // hover / colour
    slow: "800ms", // signature-beat ceiling (== Werner celebrate)
  },
  easing: {
    standard: "cubic-bezier(0.4, 0, 0.2, 1)", // interaction default
    enter: "cubic-bezier(0, 0, 0.2, 1)", // arriving elements
  },
} as const;

export type MotionDuration = keyof typeof motion.duration;
export type MotionEasing = keyof typeof motion.easing;

export const radius = { sm: "4px", md: "6px", lg: "10px" } as const;

/** The brand outline thickness used on every Lemon primitive. */
export const edgeWidth = "2.5px" as const;

export const type = {
  sans: '"Inter", system-ui, -apple-system, sans-serif',
  mono: '"JetBrains Mono", ui-monospace, SFMono-Regular, monospace',
  // reading prose only (MasterMdViewer, Notebook prose blocks)
  serif: '"Charter", "Iowan Old Style", Georgia, serif',
} as const;
