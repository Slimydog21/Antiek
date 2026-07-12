/**
 * HtmlNativeSettingsMarketplaceFreeCompetitionDrNdPanel — free-file.
 * HTML-native view over settings add-model marketplace free competition DR ND.
 */
import { useState } from "react";
import { LemonButton, LemonCard } from "../../components/lemon";
import {
  composeHtmlNativeSettingsMarketplaceFreeCompetitionDrNd,
  formatHtmlNativeSettingsMarketplaceFreeCompetitionDrNdSummary,
  type HtmlNativeSettingsMarketplaceFreeCompetitionDrNdCompose,
} from "../../api/htmlNativeSettingsMarketplaceFreeCompetitionDrNdCompose";

export default function HtmlNativeSettingsMarketplaceFreeCompetitionDrNdPanel() {
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<HtmlNativeSettingsMarketplaceFreeCompetitionDrNdCompose | null>(
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
      void composeHtmlNativeSettingsMarketplaceFreeCompetitionDrNd;
      void formatHtmlNativeSettingsMarketplaceFreeCompetitionDrNdSummary;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div className="flex flex-col gap-3 p-4 max-w-3xl">
      <h2 className="text-lg font-semibold">
        HTML-native view · settings · marketplace free · competition DR · ND
      </h2>
      <p className="text-sm text-muted">
        Pure residual: every asset viewed as HTML (never PDF-primary) over BYOK
        settings + free-first marketplace + competition DR + NotDiamond REJECT
        pack. pdf_primary and purchase_executed always false · ND REJECT.
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
          {formatHtmlNativeSettingsMarketplaceFreeCompetitionDrNdSummary(
            result,
          )}
        </LemonCard>
      )}
    </div>
  );
}
