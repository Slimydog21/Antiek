/**
 * Website-first ads MVP — manual sponsor footer gate
 * (docs/decisions/applovin-website-mvp-attribution-ledger-2026-09-17.md).
 *
 * Default OFF. Set VITE_MANUAL_SPONSOR_FOOTER=1 on Mini dogfood (or Pages)
 * to mount the MASTER.md / synthesis footer slot. Creative + ledger come
 * from POST /api/ad/fills (server ANTIEK_MANUAL_SPONSOR_* env). No live
 * AppLovin / MAX / network tags.
 */
export const manualSponsorFooterEnabled =
  import.meta.env.VITE_MANUAL_SPONSOR_FOOTER === "1";
