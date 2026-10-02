import type { ReactNode } from "react";

import BrainMascot from "../brand/BrainMascot";
import { BrainSleeping, BrainThinking } from "../brand/mascot/animated";
import {
  MascotCurious,
  MascotDizzy,
  MascotHappy,
  MascotHit,
} from "../brand/mascot/reactions";

/**
 * Brain emote vocabulary (SPR-05).
 *
 * The emotes do not create a fifth Brain mood or a second mascot. Semantic
 * reaction compositions reuse one of the four canonical raster moods and add
 * small token-native HTML/SVG chrome around it.
 *
 * Emote → existing mark map (rigor #5 — the reuse ledger a maintainer reads
 * to know what is reused vs. new):
 *
 *   curious   → MascotCurious       (evidence-card head tilt)
 *   happy     → MascotHappy         (archival verification stamp)
 *   thinking  → BrainThinking      (same mark, named for the AI-working read)
 *   sleeping  → BrainSleeping      (the breathing + zZz idle pose)
 *   dizzy     → MascotDizzy         (one paperclip orbit)
 *   hit       → MascotHit           (brass-tab squash and rebound)
 *
 * The SVGs are decorative props only; canonical Brain remains the identity.
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
 * How long each emote plays before MascotStage returns to its ambient state.
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
  if (reduced && kind === "thinking") {
    return <BrainMascot mood="thinking" size={size} label="Antiek thinking" />;
  }

  if (reduced && kind === "sleeping") {
    return (
      <BrainSleeping
        size={size}
        label="Antiek sleeping"
        reduced
      />
    );
  }

  switch (kind) {
    case "curious":
      return <MascotCurious size={size} reduced={reduced} />;
    case "thinking":
      return <BrainThinking size={size} label={`Antiek ${kind}`} />;
    case "happy":
      return <MascotHappy size={size} reduced={reduced} />;
    case "hit":
      return <MascotHit size={size} reduced={reduced} />;
    case "sleeping":
      return <BrainSleeping size={size} label="Antiek sleeping" />;
    case "dizzy":
      return <MascotDizzy size={size} reduced={reduced} />;
    default:
      return null;
  }
}
