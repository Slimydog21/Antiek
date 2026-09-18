/**
 * Flag-gated manual sponsor footer for MASTER.md / research synthesis.
 *
 * Placement: below thesis / appendix / reuse footnote — never interstitial,
 * never beside the reading column. Reuses Reading `AdBorder` (bottom rail) +
 * house fallback. Fill policy = BiddingPolicy.MANUAL_SPONSOR (static only).
 *
 * Dual structure (decision §2): creative is UI projection; durable truth is
 * `POST /api/ad/fills` → `ad_fill_decisions` (revenue $0 / unpriced until
 * Rank 0.1 pricing + legal). Client never invents cents.
 *
 * docs/decisions/applovin-website-mvp-attribution-ledger-2026-09-17.md §3.2
 */
import { useEffect, useMemo, useState } from "react";

import { fetchFill, type SlotFill } from "../../components/ad/adFillClient";
import AdBorder, { type AdFillView } from "../Reading/AdBorder";
import { BIDDING_POLICY_MANUAL_SPONSOR } from "./manualSponsorFill";
import { manualSponsorFooterEnabled } from "./manualSponsorFlags";

export interface ManualSponsorFooterProps {
  /** Synthesis id when known; used for stable slot + window identity. */
  synthesisId?: string | null;
  /** Test / Storybook override — production reads the Vite flag. */
  enabled?: boolean;
  /** Test seam: override fill fetch. */
  fillFetcher?: typeof fetchFill;
}

function slotFillToView(fill: SlotFill | undefined): AdFillView {
  if (fill?.kind === "ad" && fill.ad) {
    return {
      kind: "ad",
      ad: {
        advertiserName: fill.ad.advertiser_display_name,
        creativeUrl: fill.ad.creative_url,
        landingUrl: fill.ad.landing_url,
      },
    };
  }
  const promo = fill?.house;
  if (promo?.promoted_document_id && promo.title) {
    return {
      kind: "house",
      house: {
        documentId: promo.promoted_document_id,
        title: promo.title,
        author: promo.author ?? null,
      },
    };
  }
  return { kind: "house", house: null };
}

export default function ManualSponsorFooter({
  synthesisId = null,
  enabled = manualSponsorFooterEnabled,
  fillFetcher = fetchFill,
}: ManualSponsorFooterProps) {
  const windowId = useMemo(
    () => `win:research:manual-sponsor:${synthesisId ?? "anon"}`,
    [synthesisId],
  );
  const [served, setServed] = useState(false);
  const [decisionId, setDecisionId] = useState<string | null>(null);
  const [fillView, setFillView] = useState<AdFillView>({ kind: "house", house: null });

  useEffect(() => {
    if (!enabled) return;
    const ac = new AbortController();
    void (async () => {
      const result = await fillFetcher({
        windowId,
        lens: "research",
        positions: ["bottom"],
        signal: ac.signal,
      });
      if (ac.signal.aborted) return;
      const bottom = result.fills.find((f) => f.position === "bottom") ?? result.fills[0];
      setServed(result.served);
      setDecisionId(bottom?.fill_decision_id ?? null);
      setFillView(slotFillToView(bottom));
    })();
    return () => ac.abort();
  }, [enabled, windowId, fillFetcher]);

  if (!enabled) return null;

  const slotId = `slot:synthesis:${synthesisId ?? "anon"}:footer`;

  return (
    <div
      className="max-w-3xl mx-auto px-6 pb-8"
      data-testid="manual-sponsor-footer"
      data-bidding-policy={BIDDING_POLICY_MANUAL_SPONSOR}
      data-fill-served={served ? "1" : "0"}
      data-fill-decision-id={decisionId ?? undefined}
    >
      <AdBorder slotId={slotId} position="bottom" fill={fillView} />
    </div>
  );
}
