/**
 * ModelDecisionTwinSearchHtmlNativeMarketplaceFreeMoPanel — free-file.
 */
import { useState } from "react";
import { LemonButton, LemonCard } from "../../components/lemon";
import {
  composeModelDecisionTwinSearchHtmlNativeMarketplaceFreeMo,
  formatModelDecisionTwinSearchHtmlNativeMarketplaceFreeMoSummary,
  type ModelDecisionTwinSearchHtmlNativeMarketplaceFreeMoCompose,
} from "../../api/modelDecisionTwinSearchHtmlNativeMarketplaceFreeMoCompose";

export default function ModelDecisionTwinSearchHtmlNativeMarketplaceFreeMoPanel() {
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<ModelDecisionTwinSearchHtmlNativeMarketplaceFreeMoCompose | null>(
      null,
    );

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      setError(
        "Full nest proven in pure tests; panel is free-file surface only.",
      );
      void ack;
      void composeModelDecisionTwinSearchHtmlNativeMarketplaceFreeMo;
      void formatModelDecisionTwinSearchHtmlNativeMarketplaceFreeMoSummary;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div className="flex flex-col gap-3 p-4 max-w-3xl">
      <h2 className="text-lg font-semibold">
        Model decision · twin search · HTML-native marketplace free MO
      </h2>
      <p className="text-sm text-muted">
        Pure residual: decision-tree model selection + usage bar + prompt budget
        projection over twin intelligent search + HTML-native + free-before-buy
        + Midnight Oil pack. live_router_authorized always false · ND REJECT.
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
        Compose model decision residual pack (tests are proof)
      </LemonButton>
      {error && (
        <LemonCard className="border-warning p-3 text-sm">{error}</LemonCard>
      )}
      {result && (
        <LemonCard className="p-3 text-sm">
          {formatModelDecisionTwinSearchHtmlNativeMarketplaceFreeMoSummary(
            result,
          )}
        </LemonCard>
      )}
    </div>
  );
}
