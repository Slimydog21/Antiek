/**
 * agents/StatusDot.tsx — SPR-10 M3: ONE primitive for every agent status
 * surface (tab glyph, picker row, strip badge). Colour + word, never colour
 * alone (tokens rule); every state also differs by SHAPE where the word is
 * hidden, so working vs done survives monochrome, reduced motion and the
 * night theme where they share a hex:
 *
 *   blocked  ● solid              × 
 *   working  ◐ hollow ring        ◐  (pulse / spin, motion-reduce: none)
 *   done     ● solid + halo       ✓
 *   idle     ○ hollow             ○
 *   unknown  · 4 px               ·
 *
 * Tokens: the --state-* family only (design/tokens.css:440-444; every fill
 * measures >= 4.5:1 on page/card/inset in both themes, tokens.contrast
 * .test.ts). The sprint page's sun/success/text-2 are NOT used: --sun is a
 * fill below 3:1 on day paper (tokens.contrast.test.ts:300-302) and equals
 * the night success. On an island ground the dot wears a 1 px ring in
 * --fixed-paper (#FFF in both themes: 14.6:1 on --fixed-ink, 19.2:1 on
 * --void, measured), which fixes the BOUNDARY, not the fill.
 */
import type { AgentStatus } from "./agentStatus";

export type StatusDotVariant = "dot" | "symbol";
export type StatusDotWord = "visible" | "sr";
export type StatusDotGround = "paper" | "island";

export interface StatusDotProps {
  status: AgentStatus;
  variant?: StatusDotVariant;
  word?: StatusDotWord;
  ground?: StatusDotGround;
  /** Joins the accessible name: "idle, stopped". */
  reason?: string;
  className?: string;
}

/** The one place the island boundary token is named (pinned by the contrast test). */
export const ISLAND_RING_TOKEN = "--fixed-paper";

export const STATUS_WORD: Readonly<Record<AgentStatus, string>> = Object.freeze({
  blocked: "blocked",
  working: "working",
  done: "done",
  idle: "idle",
  unknown: "unknown",
});

export const STATUS_SYMBOL: Readonly<Record<AgentStatus, string>> = Object.freeze({
  blocked: "×",
  working: "◐",
  done: "✓",
  idle: "○",
  unknown: "·",
});

const DOT_BASE = "inline-block shrink-0 rounded-full box-border";

/** Shape + colour per state for the dot variant. */
const DOT_CLASS: Readonly<Record<AgentStatus, string>> = Object.freeze({
  blocked: "w-2 h-2 bg-[var(--state-blocked)]",
  working: "w-2 h-2 border-2 border-[var(--state-working)] bg-transparent animate-pulse motion-reduce:animate-none",
  done: "w-2 h-2 bg-[var(--state-done)] ring-2 ring-[var(--state-done)]",
  idle: "w-2 h-2 border-2 border-[var(--state-stopped)] bg-transparent",
  unknown: "w-1 h-1 bg-[var(--state-muted)]",
});

const SYMBOL_CLASS: Readonly<Record<AgentStatus, string>> = Object.freeze({
  blocked: "text-[var(--state-blocked)]",
  working: "text-[var(--state-working)] inline-block animate-spin motion-reduce:animate-none",
  done: "text-[var(--state-done)]",
  idle: "text-[var(--state-stopped)]",
  unknown: "text-[var(--state-muted)]",
});

export function StatusDot({ status, variant = "dot", word = "sr", ground = "paper", reason, className }: StatusDotProps) {
  const label = reason ? `${STATUS_WORD[status]}, ${reason}` : STATUS_WORD[status];
  const ring = ground === "island" ? ` ring-1 ring-[var(${ISLAND_RING_TOKEN})]` : "";
  const glyphClass = variant === "dot"
    ? `${DOT_BASE} ${DOT_CLASS[status]}${ring}`
    : `font-mono text-xs leading-none ${SYMBOL_CLASS[status]}${ring ? ` rounded-full${ring}` : ""}`;
  return (
    <span role="img" aria-label={label} data-status={status} className={`inline-flex items-center${className ? ` ${className}` : ""}`}>
      <span aria-hidden="true" className={glyphClass}>{variant === "symbol" ? STATUS_SYMBOL[status] : null}</span>
      <span aria-hidden="true" className={word === "sr" ? "sr-only" : "ml-1 text-xs"}>{STATUS_WORD[status]}</span>
    </span>
  );
}

export default StatusDot;
