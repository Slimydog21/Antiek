/**
 * Real product call sites that map shell signals → Werner product experiences.
 *
 * These are the SHIPPED emitters for `idle` and `fail` (deep_research_* and
 * highlight are owned by FloatMenu / DeepResearchWorkspace). Unit tests drive
 * these functions directly — they are the product path, not test doubles.
 */

import { emitWernerExperience } from "./reactionBus";

/**
 * Edge-trigger: when the pointer transitions into idle, Werner sleeps.
 * Callers pass previous + current idle flags from the live follow read.
 * Returns true when an experience was emitted (for tests).
 */
export function notifyPointerIdleEdge(
  wasIdle: boolean,
  isIdle: boolean,
): boolean {
  if (!wasIdle && isIdle) {
    emitWernerExperience({ experience: "idle" });
    return true;
  }
  return false;
}

/**
 * Generic shell failure path — toast.err, unhandled product failures, etc.
 * Maps onto the `fail` product experience (dizzy).
 */
export function notifyShellFailure(_reason?: string): boolean {
  emitWernerExperience({ experience: "fail" });
  return true;
}
