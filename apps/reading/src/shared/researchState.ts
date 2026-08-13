/**
 * researchState.ts — the ONE research-state vocabulary (herdr transfer, P0-1).
 *
 * Before this module, Antiek had TWO drifting status encodings: the
 * five-value `plainStatus` vocabulary in MyResearch.tsx and the four-case
 * `StatusDot` in InvestigationSidebar.tsx. herdr's design lesson (src/detect/
 * mod.rs, one `(state, seen) -> icon+colour` mapping consumed by every
 * surface) is that drift is a bug: a state added in one surface silently
 * mismatches every other. This module is the single registry; surfaces
 * consume it and never define their own encoding.
 *
 * Vocabulary (SPR-02 narration words, kept verbatim so the monitor never
 * shows a raw backend status):
 *   working         — in_progress
 *   blocked         — failed (needs the operator: "needs attention")
 *   done            — completed
 *   stopped         — stopped/cancelled/halted
 *   unavailable     — not_found (a referenced id with no row)
 *
 * `unseen` is a presentation axis, not a state: a completed research you
 * have not opened reads "done" with the unread flag (herdr's
 * `done = Idle ∧ ¬seen`). Pure module: no React, no storage.
 */
import type { InvestigationSummary } from "../lib/api";

export type ResearchState =
  | "working"
  | "blocked"
  | "done"
  | "stopped"
  | "unavailable";

/** LemonTag colour + semantic token per state. Tokens live in
 *  design/tokens.css|ts (`--state-*` family) so state colour is a design
 *  token, never a raw hex in a component. */
export interface ResearchStateStyle {
  state: ResearchState;
  /** Plain-language label (SPR-02 narration vocabulary). */
  label: "working" | "needs attention" | "done" | "stopped" | "unavailable";
  /** LemonTag colour (back-compat with the pre-registry encodings). */
  colour: "sun" | "aurora" | "muted" | "danger";
  /** Semantic token name, minus the `--` prefix. */
  token:
    | "state-working"
    | "state-blocked"
    | "state-done"
    | "state-stopped"
    | "state-muted";
  /** Whether this research is still consuming concurrency (a "running" one). */
  running: boolean;
}

export function researchStateFor(
  status: InvestigationSummary["status"],
): ResearchState {
  switch (status) {
    case "in_progress":
      return "working";
    case "completed":
      return "done";
    case "failed":
      // A failed research needs the operator's eyes — the "stuck one"
      // herdr's traffic-lighting exists to surface.
      return "blocked";
    case "stopped":
      return "stopped";
    case "not_found":
      return "unavailable";
    default:
      return assertNever(status);
  }
}

function assertNever(x: never): never {
  throw new Error(`unhandled investigation status: ${String(x)}`);
}

export function researchStateStyle(
  status: InvestigationSummary["status"],
): ResearchStateStyle {
  const state = researchStateFor(status);
  switch (state) {
    case "working":
      return { state, label: "working", colour: "sun", token: "state-working", running: true };
    case "blocked":
      return { state, label: "needs attention", colour: "danger", token: "state-blocked", running: false };
    case "done":
      return { state, label: "done", colour: "aurora", token: "state-done", running: false };
    case "stopped":
      return { state, label: "stopped", colour: "muted", token: "state-stopped", running: false };
    case "unavailable":
      return { state, label: "unavailable", colour: "muted", token: "state-muted", running: false };
    default:
      return assertNever(state);
  }
}

/** Tailwind classes for the canonical state dot (one dot, every surface).
 *  Colours resolve through the `--state-*` token family (design/tokens.css),
 *  so the dot can never drift from the brand palette; Tailwind arbitrary
 *  values make the var reference a real class. Unseen-done renders with a
 *  halo (ring) so the unread axis survives even at dot resolution. Working
 *  keeps the ambient pulse the sidebar shipped. */
export function researchStateDotClass(
  state: ResearchState,
  unseen: boolean,
): string {
  switch (state) {
    case "working":
      return "bg-[var(--state-working)] animate-pulse";
    case "blocked":
      return "bg-[var(--state-blocked)]";
    case "done":
      return unseen
        ? "bg-[var(--state-done)] ring-2 ring-[var(--state-done)]/50"
        : "bg-[var(--state-done)]";
    case "stopped":
      return "bg-[var(--state-stopped)]";
    case "unavailable":
      return "bg-[var(--state-muted)]/50";
    default:
      return assertNever(state);
  }
}

/** Human label for a state (for tooltips/badges outside summary context). */
export function researchStateLabel(state: ResearchState): string {
  switch (state) {
    case "blocked":
      return "needs attention";
    default:
      return state;
  }
}

/** Unread semantics: a completed research the operator has not opened since
 *  it finished. `lastSeenAtIso` is the persisted timestamp (workspace/seen.ts);
 *  null means "never seen" — but only completed work is unread (herdr: done =
 *  Idle ∧ ¬seen). Failed research is already "blocked" and does not need the
 *  unread axis too. */
export function isUnseen(
  summary: Pick<InvestigationSummary, "status" | "completed_at">,
  lastSeenAtIso: string | null,
): boolean {
  if (summary.status !== "completed") return false;
  const finished = summary.completed_at;
  if (!finished) return false;
  if (!lastSeenAtIso) return true;
  return new Date(finished).getTime() > new Date(lastSeenAtIso).getTime();
}
