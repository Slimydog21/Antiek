/**
 * MarketplaceFreeMidnightOilSettingsDecisionCompetitionDrNdShadowRecursiveTwinPanel — free-file.
 */
import { useState } from "react";
import { LemonButton, LemonCard } from "../../components/lemon";
import {
  composeMarketplaceFreeMidnightOilSettingsDecisionCompetitionDrNdShadowRecursiveTwin,
  formatMarketplaceFreeMidnightOilSettingsDecisionCompetitionDrNdShadowRecursiveTwinSummary,
  type MarketplaceFreeMidnightOilSettingsDecisionCompetitionDrNdShadowRecursiveTwinCompose,
} from "../../api/marketplaceFreeMidnightOilSettingsDecisionCompetitionDrNdShadowRecursiveTwinCompose";

export default function MarketplaceFreeMidnightOilSettingsDecisionCompetitionDrNdShadowRecursiveTwinPanel() {
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<MarketplaceFreeMidnightOilSettingsDecisionCompetitionDrNdShadowRecursiveTwinCompose | null>(null);

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      setError("Full nest proven in pure tests; panel is free-file surface only.");
      void ack;
      void composeMarketplaceFreeMidnightOilSettingsDecisionCompetitionDrNdShadowRecursiveTwin;
      void formatMarketplaceFreeMidnightOilSettingsDecisionCompetitionDrNdShadowRecursiveTwinSummary;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div className="flex flex-col gap-3 p-4 max-w-3xl">
      <h2 className="text-lg font-semibold">
        Marketplace free-before-buy · Midnight Oil · settings
      </h2>
      <p className="text-sm text-muted">
        Pure residual: free HTML digital book before purchase over Midnight Oil +
        settings decision pack. purchase_executed/hosted false · ND REJECT.
      </p>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} />
        operator_ack
      </label>
      <LemonButton type="primary" onClick={onCompose}>
        Compose marketplace free residual (tests are proof)
      </LemonButton>
      {error && <LemonCard className="border-warning p-3 text-sm">{error}</LemonCard>}
      {result && (
        <LemonCard className="p-3 text-sm">
          {formatMarketplaceFreeMidnightOilSettingsDecisionCompetitionDrNdShadowRecursiveTwinSummary(result)}
        </LemonCard>
      )}
    </div>
  );
}
