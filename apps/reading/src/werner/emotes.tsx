import type { ReactNode } from "react";

import Werner from "../brand/Werner";
import { WernerSleeping, WernerThinking } from "../brand/werner/animated";
import {
  WernerCurious,
  WernerDizzy,
  WernerHappy,
  WernerHit,
} from "../brand/werner/reactions";

/**
 * Werner emote vocabulary (SPR-05).
 *
 * The emotes do not create a fifth Werner mood or a second mascot. Semantic
 * reaction compositions reuse one of the four canonical raster moods and add
 * small token-native HTML/SVG chrome around it.
 *
 * Emote → existing mark map (rigor #5 — the reuse ledger a maintainer reads
 * to know what is reused vs. new):
 *
 *   curious   → WernerCurious       (evidence-card head tilt)
 *   happy     → WernerHappy         (archival verification stamp)
 *   thinking  → WernerThinking      (same mark, named for the AI-working read)
 *   sleeping  → WernerSleeping      (the breathing + zZz idle pose)
 *   dizzy     → WernerDizzy         (one paperclip orbit)
 *   hit       → WernerHit           (brass-tab squash and rebound)
 *
 * The SVGs are decorative props only; canonical Werner remains the identity.
 */

export type EmoteKind =
  "curious" | "happy" | "thinking" | "sleeping" | "dizzy" | "hit";

export const EMOTE_KINDS: readonly EmoteKind[] = [
  "curious",
  "happy",
  "thinking",
  "sleeping",
  "dizzy",
  "hit",
];

/**
 * How long each emote plays before WernerStage returns to its ambient state.
 * Curious, happy, dizzy, and hit pin their CSS custom duration to these exact
 * values. Thinking/sleeping retain their readable existing holds.
 */
export const EMOTE_DURATION_MS: Record<EmoteKind, number> = {
  curious: 1200, // evidence-card arrival and head tilt
  happy: 800, // verification stamp and quiet proud lift
  thinking: 1400, // a touch over one aurora cycle so it doesn't snap mid-pulse
  sleeping: 2400, // one full breath cycle
  dizzy: 1300, // one paperclip orbit
  hit: 800, // brass-tab squash and rebound
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
   * Reduced motion keeps a meaningful still. Thinking/sleeping render their
   * canonical static mark; semantic reactions retain their explanatory prop
   * while CSS disables every keyframe.
   */
  reduced: boolean;
}

/**
 * Render the mark for an emote. The stage's keyed reaction view remounts each
 * one-shot composition per semantic event.
 */
export function EmoteView({ kind, size, reduced }: EmoteViewProps): ReactNode {
  if (reduced && (kind === "thinking" || kind === "sleeping")) {
    // Thinking/sleeping retain their existing canonical stills. The four
    // semantic reactions own meaningful static chrome in their reduced path.
    const mood = kind === "sleeping" ? "empty" : "thinking";
    return <Werner mood={mood} size={size} label={`Werner ${kind}`} />;
  }

  switch (kind) {
    case "curious":
      return <WernerCurious size={size} reduced={reduced} />;
    case "thinking":
      return <WernerThinking size={size} label={`Werner ${kind}`} />;
    case "happy":
      return <WernerHappy size={size} reduced={reduced} />;
    case "hit":
      return <WernerHit size={size} reduced={reduced} />;
    case "sleeping":
      return <WernerSleeping size={size} label="Werner sleeping" />;
    case "dizzy":
      return <WernerDizzy size={size} reduced={reduced} />;
    default:
      return null;
  }
}
