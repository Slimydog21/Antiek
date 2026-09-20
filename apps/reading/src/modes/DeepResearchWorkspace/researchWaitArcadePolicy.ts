export const RESEARCH_WAIT_ARCADE_OFFER_AFTER_MS = 8_000;

export type ResearchWaitArcadeMode = "hidden" | "waiting" | "offer" | "playing";

export interface ResearchWaitArcadePolicyInput {
  featureEnabled: boolean;
  hasAuthoritativeSnapshot: boolean;
  researchCount: number;
  allTerminal: boolean;
  reducedMotion: boolean;
  offerReady: boolean;
  optedIn: boolean;
}

/**
 * Render policy only. Research lifecycle authority remains with
 * useResearchSession's durable snapshot; arcade state can never keep a host
 * alive after that snapshot becomes terminal.
 */
export function deriveResearchWaitArcadeMode(
  input: ResearchWaitArcadePolicyInput,
): ResearchWaitArcadeMode {
  if (
    !input.featureEnabled ||
    !input.hasAuthoritativeSnapshot ||
    input.researchCount === 0 ||
    input.allTerminal ||
    input.reducedMotion
  ) {
    return "hidden";
  }
  if (input.optedIn) return "playing";
  if (input.offerReady) return "offer";
  return "waiting";
}
