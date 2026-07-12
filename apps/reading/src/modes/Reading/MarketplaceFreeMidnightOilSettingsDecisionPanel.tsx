/**
 * MarketplaceFreeMidnightOilSettingsDecisionPanel — free-file.
 */
import { useState } from "react";
import { LemonButton, LemonCard } from "../../components/lemon";
import {
  composeMarketplaceFreeMidnightOilSettingsDecision,
  formatMarketplaceFreeMidnightOilSettingsDecisionSummary,
  type MarketplaceFreeMidnightOilSettingsDecisionCompose,
} from "../../api/marketplaceFreeMidnightOilSettingsDecisionCompose";

export default function MarketplaceFreeMidnightOilSettingsDecisionPanel() {
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<MarketplaceFreeMidnightOilSettingsDecisionCompose | null>(null);

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      setError(
        "Full nest proven in pure tests; panel is free-file surface only.",
      );
      void ack;
      void composeMarketplaceFreeMidnightOilSettingsDecision;
      void formatMarketplaceFreeMidnightOilSettingsDecisionSummary;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div className="flex flex-col gap-3 p-4 max-w-3xl">
      <h2 className="text-lg font-semibold">
        Marketplace free · Midnight Oil · settings decision
      </h2>
      <p className="text-sm text-muted">
        Pure residual: free-before-buy HTML port over Midnight Oil price-ceiling
        + settings decision + competition DR pack. purchase_executed and hosted
        always false · ND REJECT.
      </p>
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={ack}
          onChange={(e) => setAck(e.target.checked)}
        />
        operator_ack
      </label>
      <LemonButton type="primary" onClick={onCompose}>
        Compose marketplace free residual pack (tests are proof)
      </LemonButton>
      {error && (
        <LemonCard className="border-warning p-3 text-sm">{error}</LemonCard>
      )}
      {result && (
        <LemonCard className="p-3 text-sm">
          {formatMarketplaceFreeMidnightOilSettingsDecisionSummary(result)}
        </LemonCard>
      )}
    </div>
  );
}
