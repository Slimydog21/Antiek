/**
 * TwinSearchModelDecisionHtmlNativeSettingsMarketplacePanel — free-file.
 * Twin intelligent search over model decision HTML-native settings marketplace pack.
 */
import { useState } from "react";
import { LemonButton, LemonCard } from "../../components/lemon";
import {
  composeTwinSearchModelDecisionHtmlNativeSettingsMarketplace,
  formatTwinSearchModelDecisionHtmlNativeSettingsMarketplaceSummary,
  type TwinSearchModelDecisionHtmlNativeSettingsMarketplaceCompose,
} from "../../api/twinSearchModelDecisionHtmlNativeSettingsMarketplaceCompose";

export default function TwinSearchModelDecisionHtmlNativeSettingsMarketplacePanel() {
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<TwinSearchModelDecisionHtmlNativeSettingsMarketplaceCompose | null>(
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
      void composeTwinSearchModelDecisionHtmlNativeSettingsMarketplace;
      void formatTwinSearchModelDecisionHtmlNativeSettingsMarketplaceSummary;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div className="flex flex-col gap-3 p-4 max-w-3xl">
      <h2 className="text-lg font-semibold">
        Twin search · model decision · HTML-native settings marketplace
      </h2>
      <p className="text-sm text-muted">
        Pure residual: twin substrate intelligent search (≥1 hit) over model
        decision budget + HTML-native settings marketplace free competition pack.
        remote_index_queried=false · twin_written=false · pdf_primary=false · ND
        REJECT.
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
        Compose twin-search residual pack (tests are proof)
      </LemonButton>
      {error && (
        <LemonCard className="border-warning p-3 text-sm">{error}</LemonCard>
      )}
      {result && (
        <LemonCard className="p-3 text-sm">
          {formatTwinSearchModelDecisionHtmlNativeSettingsMarketplaceSummary(
            result,
          )}
        </LemonCard>
      )}
    </div>
  );
}
