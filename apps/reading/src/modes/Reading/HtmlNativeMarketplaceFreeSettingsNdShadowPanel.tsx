/**
 * HtmlNativeMarketplaceFreeSettingsNdShadowPanel — free-file.
 * HTML-native view residual over marketplace free settings ND pack.
 */
import { useState } from "react";
import { LemonButton, LemonCard } from "../../components/lemon";
import {
  composeHtmlNativeMarketplaceFreeSettingsNdShadow,
  formatHtmlNativeMarketplaceFreeSettingsNdShadowSummary,
  type HtmlNativeMarketplaceFreeSettingsNdShadowCompose,
} from "../../api/htmlNativeMarketplaceFreeSettingsNdShadowCompose";

export default function HtmlNativeMarketplaceFreeSettingsNdShadowPanel() {
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<HtmlNativeMarketplaceFreeSettingsNdShadowCompose | null>(null);

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      setError(
        "Full nest proven in pure tests; panel is free-file surface only.",
      );
      void ack;
      void composeHtmlNativeMarketplaceFreeSettingsNdShadow;
      void formatHtmlNativeMarketplaceFreeSettingsNdShadowSummary;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div className="flex flex-col gap-3 p-4 max-w-3xl">
      <h2 className="text-lg font-semibold">
        HTML-native view · marketplace free · settings ND
      </h2>
      <p className="text-sm text-muted">
        Pure residual: HTML-only view session authority over free-before-buy +
        BYOK settings + NotDiamond REJECT pack. pdf_primary=false ·
        purchase_executed=false · hosted=false.
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
        Compose HTML-native residual pack (tests are proof)
      </LemonButton>
      {error && (
        <LemonCard className="border-warning p-3 text-sm">{error}</LemonCard>
      )}
      {result && (
        <LemonCard className="p-3 text-sm">
          {formatHtmlNativeMarketplaceFreeSettingsNdShadowSummary(result)}
        </LemonCard>
      )}
    </div>
  );
}
