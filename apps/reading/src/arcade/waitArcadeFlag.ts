/**
 * The research wait arcade is an experimental product surface, not a default.
 * Explicit opt-in keeps the ordinary Deep Research monitor byte-for-byte
 * authoritative until the operator enables the experience.
 */
export const wernerResearchWaitArcadeEnabled =
  import.meta.env.VITE_WERNER_RESEARCH_WAIT_ARCADE === "1";
