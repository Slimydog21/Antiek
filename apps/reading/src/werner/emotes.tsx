import type { ReactNode } from "react";

import Werner from "../brand/Werner";
import {
  WernerCaughtAFish,
  WernerSleeping,
  WernerThinking,
  WernerTobogganSpinner,
} from "../brand/werner/animated";

/**
 * Werner emote vocabulary (SPR-05).
 *
 * The emotes are NOT new art. The operator's lock (decision D3) is that
 * Werner is SVG/CSS and recolour-driven — so each emote maps onto one of
 * the EXISTING animated marks rather than drawing a new pose. This file is
 * just the vocabulary + the mapping; the marks own their own keyframes and
 * their own reduced-motion collapse (brand/werner/animated/animations.css).
 *
 * Emote → existing mark map (rigor #5 — the reuse ledger a maintainer reads
 * to know what is reused vs. new):
 *
 *   curious   → WernerThinking      (the aurora-dot "considering" beat —
 *                                    a head-tilt-ish "what's this?" read)
 *   happy     → WernerCaughtAFish   (the one-shot flipper-raise celebration)
 *   thinking  → WernerThinking      (same mark, named for the AI-working read)
 *   sleeping  → WernerSleeping      (the breathing + zZz idle pose)
 *   dizzy     → WernerTobogganSpinner (the spin — a surprised/dizzy reaction)
 *   hit       → WernerCaughtAFish   (SPR-10's Tom-&-Jerry button bump — a
 *                                    short celebratory pop on arrival; the
 *                                    squash/translate is added by the stage
 *                                    wrapper, the mark supplies the flourish)
 *
 * No emote authors a new SVG. `hit` is a COMPOSITION (SPR-10's bump) layered
 * over an existing mark, per that sprint's out-of-scope rule.
 */

export type EmoteKind =
  | "curious"
  | "happy"
  | "thinking"
  | "sleeping"
  | "dizzy"
  | "hit";

export const EMOTE_KINDS: readonly EmoteKind[] = [
  "curious",
  "happy",
  "thinking",
  "sleeping",
  "dizzy",
  "hit",
];

/**
 * How long each emote plays before WernerStage returns to its ambient
 * state. These track the underlying mark's own keyframe duration so the
 * state machine flips back to idle/following exactly when the visual beat
 * ends — not before (a dead frame) and not long after (Werner stuck
 * "emoting" with nothing moving). The one-shot marks (fish) run ~800ms;
 * the looping marks (thinking/sleeping) we hold for a readable beat.
 */
export const EMOTE_DURATION_MS: Record<EmoteKind, number> = {
  curious: 1200, // one full thinking-dot cycle reads as a considering glance
  happy: 800, // matches werner-fish-* one-shot (animations.css)
  thinking: 1400, // a touch over one aurora cycle so it doesn't snap mid-pulse
  sleeping: 2400, // one full breath cycle
  dizzy: 1300, // one toboggan spin — a brief surprised reaction
  hit: 800, // matches the fish one-shot; SPR-10's bump rides on top
};

/** Default emote duration when a caller asks for one not in the table. */
export const DEFAULT_EMOTE_DURATION_MS = 1000;

export function emoteDurationMs(kind: EmoteKind): number {
  return EMOTE_DURATION_MS[kind] ?? DEFAULT_EMOTE_DURATION_MS;
}

interface EmoteViewProps {
  kind: EmoteKind;
  size: number;
  /**
   * When reduced motion is active each emote collapses to a STILL variant:
   * the same mark rendered without its animating wrapper, so the operator
   * sees Werner change pose (a quiet acknowledgment) but nothing moves. The
   * marks' own keyframes are also reduced-motion-guarded in animations.css —
   * this prop is the JS half so we never even mount the animating chrome.
   */
  reduced: boolean;
}

/**
 * Render the mark for an emote. One-shot marks key off `kind` so React
 * remounts them per fire (the fish/celebration animation only restarts on
 * remount — see WernerCaughtAFish's docblock).
 */
export function EmoteView({ kind, size, reduced }: EmoteViewProps): ReactNode {
  if (reduced) {
    // Still acknowledgment: the canonical mark in the nearest matching mood,
    // no animating wrapper. `curious`/`thinking` → thinking pose; `happy`/
    // `hit` → celebrate pose; `sleeping` → empty/sleeping pose.
    const mood =
      kind === "happy" || kind === "hit"
        ? "celebrate"
        : kind === "sleeping"
          ? "empty"
          : kind === "dizzy"
            ? "idle"
            : "thinking";
    return <Werner mood={mood} size={size} label={`Werner ${kind}`} />;
  }

  switch (kind) {
    case "curious":
    case "thinking":
      return <WernerThinking size={size} label={`Werner ${kind}`} />;
    case "happy":
    case "hit":
      return <WernerCaughtAFish size={size} label={`Werner ${kind}`} />;
    case "sleeping":
      return <WernerSleeping size={size} label="Werner sleeping" />;
    case "dizzy":
      return <WernerTobogganSpinner size={size} label="Werner dizzy" />;
    default:
      return null;
  }
}
