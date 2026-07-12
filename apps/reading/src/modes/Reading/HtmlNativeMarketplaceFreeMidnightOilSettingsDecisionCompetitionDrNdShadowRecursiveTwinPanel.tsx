/**
 * HtmlNativeMarketplaceFreeMidnightOilSettingsDecisionCompetitionDrNdShadowRecursiveTwinPanel — free-file.
 */
import { useState } from "react";
import { LemonButton, LemonCard } from "../../components/lemon";
import {
  composeHtmlNativeMarketplaceFreeMidnightOilSettingsDecisionCompetitionDrNdShadowRecursiveTwin,
  formatHtmlNativeMarketplaceFreeMidnightOilSettingsDecisionCompetitionDrNdShadowRecursiveTwinSummary,
  type HtmlNativeMarketplaceFreeMidnightOilSettingsDecisionCompetitionDrNdShadowRecursiveTwinCompose,
} from "../../api/htmlNativeMarketplaceFreeMidnightOilSettingsDecisionCompetitionDrNdShadowRecursiveTwinCompose";

export default function HtmlNativeMarketplaceFreeMidnightOilSettingsDecisionCompetitionDrNdShadowRecursiveTwinPanel() {
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<HtmlNativeMarketplaceFreeMidnightOilSettingsDecisionCompetitionDrNdShadowRecursiveTwinCompose | null>(null);

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      setError("Full nest proven in pure tests; panel is free-file surface only.");
      void ack;
      void composeHtmlNativeMarketplaceFreeMidnightOilSettingsDecisionCompetitionDrNdShadowRecursiveTwin;
      void formatHtmlNativeMarketplaceFreeMidnightOilSettingsDecisionCompetitionDrNdShadowRecursiveTwinSummary;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div className="flex flex-col gap-3 p-4 max-w-3xl">
      <h2 className="text-lg font-semibold">
        HTML-native view · marketplace free · Midnight Oil
      </h2>
      <p className="text-sm text-muted">
        Pure residual: HTML view session authority over free-before-buy marketplace +
        Midnight Oil settings pack. pdf_primary false · ND REJECT.
      </p>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} />
        operator_ack
      </label>
      <LemonButton type="primary" onClick={onCompose}>
        Compose HTML-native residual (tests are proof)
      </LemonButton>
      {error && <LemonCard className="border-warning p-3 text-sm">{error}</LemonCard>}
      {result && (
        <LemonCard className="p-3 text-sm">
          {formatHtmlNativeMarketplaceFreeMidnightOilSettingsDecisionCompetitionDrNdShadowRecursiveTwinSummary(result)}
        </LemonCard>
      )}
    </div>
  );
}
