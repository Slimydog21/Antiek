/**
 * WERNER-ICE feature flags (SPR-13) + arcade host gate (SPR-16).
 *
 * Default on in dev so operators see bait + cursor policy while iterating.
 * Set VITE_WERNER_ICE_FISHING=0 in production until SPR-16 sign-off.
 *
 * `wernerArcade` gates mini-games + the wait-state LoadingGameHost. Default
 * on in dev; set VITE_WERNER_ARCADE=0 to force the plain loader path.
 */
export const wernerIceFishingCursor =
  import.meta.env.VITE_WERNER_ICE_FISHING !== "0";

export const wernerArcade = import.meta.env.VITE_WERNER_ARCADE !== "0";