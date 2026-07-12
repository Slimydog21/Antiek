/**
 * TwinSearchHtmlNativeMarketplaceFreeSettingsPanel — free-file.
 * Twin intelligent search over HTML-native marketplace free settings ND pack.
 */
import { useState } from "react";
import { LemonButton, LemonCard } from "../../components/lemon";
import {
  composeTwinSearchHtmlNativeMarketplaceFreeSettings,
  formatTwinSearchHtmlNativeMarketplaceFreeSettingsSummary,
  type TwinSearchHtmlNativeMarketplaceFreeSettingsCompose,
} from "../../api/twinSearchHtmlNativeMarketplaceFreeSettingsCompose";

export default function TwinSearchHtmlNativeMarketplaceFreeSettingsPanel() {
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<TwinSearchHtmlNativeMarketplaceFreeSettingsCompose | null>(null);

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      setError(
        "Full nest proven in pure tests; panel is free-file surface only.",
      );
      void ack;
      void composeTwinSearchHtmlNativeMarketplaceFreeSettings;
      void formatTwinSearchHtmlNativeMarketplaceFreeSettingsSummary;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div className="flex flex-col gap-3 p-4 max-w-3xl">
      <h2 className="text-lg font-semibold">
        Twin search · HTML-native · marketplace free settings
      </h2>
      <p className="text-sm text-muted">
        Pure residual: twin substrate intelligent search (≥1 hit) over
        HTML-native view + free-before-buy + BYOK settings + ND REJECT pack.
        remote_index_queried=false · twin_written=false · pdf_primary=false.
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
          {formatTwinSearchHtmlNativeMarketplaceFreeSettingsSummary(result)}
        </LemonCard>
      )}
    </div>
  );
}
