/**
 * WERNER-ICE feature flags (SPR-13).
 *
 * Default on in dev so operators see bait + cursor policy while iterating.
 * Set VITE_WERNER_ICE_FISHING=0 in production until SPR-16 sign-off.
 */
export const wernerIceFishingCursor =
  import.meta.env.VITE_WERNER_ICE_FISHING !== "0";