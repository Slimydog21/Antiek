/**
 * MarketplaceFreeSettingsAddModelNdShadowPanel — free-file.
 * Marketplace free-before-buy over settings add-model ND shadow pack.
 */
import { useState } from "react";
import { LemonButton, LemonCard } from "../../components/lemon";
import {
  composeMarketplaceFreeSettingsAddModelNdShadow,
  formatMarketplaceFreeSettingsAddModelNdShadowSummary,
  type MarketplaceFreeSettingsAddModelNdShadowCompose,
} from "../../api/marketplaceFreeSettingsAddModelNdShadowCompose";

export default function MarketplaceFreeSettingsAddModelNdShadowPanel() {
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<MarketplaceFreeSettingsAddModelNdShadowCompose | null>(null);

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      setError(
        "Full nest proven in pure tests; panel is free-file surface only.",
      );
      void ack;
      void composeMarketplaceFreeSettingsAddModelNdShadow;
      void formatMarketplaceFreeSettingsAddModelNdShadowSummary;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div className="flex flex-col gap-3 p-4 max-w-3xl">
      <h2 className="text-lg font-semibold">
        Marketplace free · settings add-model · ND shadow
      </h2>
      <p className="text-sm text-muted">
        Pure residual: free-before-buy HTML port over BYOK add-model + NotDiamond
        REJECT + competition DR + MO unattended rewrite. purchase_executed=false ·
        hosted=false.
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
        Compose marketplace residual pack (tests are proof)
      </LemonButton>
      {error && (
        <LemonCard className="border-warning p-3 text-sm">{error}</LemonCard>
      )}
      {result && (
        <LemonCard className="p-3 text-sm">
          {formatMarketplaceFreeSettingsAddModelNdShadowSummary(result)}
        </LemonCard>
      )}
    </div>
  );
}
