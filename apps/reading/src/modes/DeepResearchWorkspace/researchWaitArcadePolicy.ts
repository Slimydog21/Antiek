export const RESEARCH_WAIT_ARCADE_OFFER_AFTER_MS = 8_000;

export type ResearchWaitArcadeMode = "hidden" | "waiting" | "offer" | "playing";

export interface ResearchWaitArcadePolicyInput {
  featureEnabled: boolean;
  hasAuthoritativeSnapshot: boolean;
  researchCount: number;
  allTerminal: boolean;
  offerReady: boolean;
  optedIn: boolean;
}

/**
 * Render policy only. Research lifecycle authority remains with
 * useResearchSession's durable snapshot; arcade state can never keep a host
 * alive after that snapshot becomes terminal.
 *
 * Reduced motion is deliberately NOT a hide condition: the engine ships a
 * tested static-frame, step-on-input play path (loop.ts), so reduced-motion
 * sessions follow the same waiting → offer → playing flow with reduced
 * cartridges. Function is never lost.
 */
export function deriveResearchWaitArcadeMode(
  input: ResearchWaitArcadePolicyInput,
): ResearchWaitArcadeMode {
  if (
    !input.featureEnabled ||
    !input.hasAuthoritativeSnapshot ||
    input.researchCount === 0 ||
    input.allTerminal
  ) {
    return "hidden";
  }
  if (input.optedIn) return "playing";
  if (input.offerReady) return "offer";
  return "waiting";
}
