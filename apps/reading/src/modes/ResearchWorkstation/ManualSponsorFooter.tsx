/**
 * Flag-gated manual sponsor footer for MASTER.md / research synthesis.
 *
 * Placement: below thesis / appendix / reuse footnote — never interstitial,
 * never beside the reading column. Reuses Reading `AdBorder` (bottom rail) +
 * house fallback. Fill policy = BiddingPolicy.MANUAL_SPONSOR (static only).
 *
 * docs/decisions/applovin-website-mvp-attribution-ledger-2026-09-17.md §3.2
 */
import AdBorder from "../Reading/AdBorder";
import { BIDDING_POLICY_MANUAL_SPONSOR, resolveManualSponsorFill } from "./manualSponsorFill";
import { manualSponsorFooterEnabled } from "./manualSponsorFlags";

export interface ManualSponsorFooterProps {
  /** Synthesis id when known; used only for stable slot identity. */
  synthesisId?: string | null;
  /** Test / Storybook override — production reads the Vite flag. */
  enabled?: boolean;
}

export default function ManualSponsorFooter({
  synthesisId = null,
  enabled = manualSponsorFooterEnabled,
}: ManualSponsorFooterProps) {
  if (!enabled) return null;

  const slotId = `slot:synthesis:${synthesisId ?? "anon"}:footer`;
  const fill = resolveManualSponsorFill();

  return (
    <div
      className="max-w-3xl mx-auto px-6 pb-8"
      data-testid="manual-sponsor-footer"
      data-bidding-policy={BIDDING_POLICY_MANUAL_SPONSOR}
    >
      <AdBorder slotId={slotId} position="bottom" fill={fill} />
    </div>
  );
}
