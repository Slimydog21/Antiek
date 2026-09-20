/**
 * Resolve the MASTER.md footer fill for the website MVP stub.
 *
 * Mirrors substrate `BiddingPolicy.MANUAL_SPONSOR` ("manual_sponsor") from
 * `substrate/ad_inventory/ad_bidding.py`. Creative is static / operator-sold
 * HTML projection only — never network demand, never ledger truth.
 *
 * When sponsor env is incomplete → house fill (honest placeholder). Ledger
 * stays $0 / disbursable=False; this module does not touch rights or escrow.
 */
import type { AdFillView } from "../Reading/AdBorder";

/** Wire value of `BiddingPolicy.MANUAL_SPONSOR` (Python enum). */
export const BIDDING_POLICY_MANUAL_SPONSOR = "manual_sponsor" as const;

export type ManualSponsorCreative = {
  advertiserName: string;
  creativeUrl: string;
  landingUrl: string;
};

/**
 * Optional operator-sold creative via Vite env (dogfood / Pages).
 * All three must be non-empty; otherwise house fallback.
 */
export function readManualSponsorCreativeFromEnv(
  env: ImportMetaEnv = import.meta.env,
): ManualSponsorCreative | null {
  const advertiserName = env.VITE_MANUAL_SPONSOR_NAME?.trim() ?? "";
  const landingUrl = env.VITE_MANUAL_SPONSOR_LANDING_URL?.trim() ?? "";
  const creativeUrl =
    env.VITE_MANUAL_SPONSOR_CREATIVE_URL?.trim() || "/mark-32.png";
  if (!advertiserName || !landingUrl) return null;
  return { advertiserName, creativeUrl, landingUrl };
}

export function resolveManualSponsorFill(
  creative: ManualSponsorCreative | null = readManualSponsorCreativeFromEnv(),
): AdFillView {
  if (creative) {
    return {
      kind: "ad",
      ad: {
        advertiserName: creative.advertiserName,
        creativeUrl: creative.creativeUrl,
        landingUrl: creative.landingUrl,
      },
    };
  }
  return { kind: "house", house: null };
}
