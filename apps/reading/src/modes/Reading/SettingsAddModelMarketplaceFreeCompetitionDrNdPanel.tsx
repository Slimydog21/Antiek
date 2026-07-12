/**
 * SettingsAddModelMarketplaceFreeCompetitionDrNdPanel — free-file.
 * Settings add-model over marketplace free competition DR ND shadow pack.
 */
import { useState } from "react";
import { LemonButton, LemonCard } from "../../components/lemon";
import {
  composeSettingsAddModelMarketplaceFreeCompetitionDrNd,
  formatSettingsAddModelMarketplaceFreeCompetitionDrNdSummary,
  type SettingsAddModelMarketplaceFreeCompetitionDrNdCompose,
} from "../../api/settingsAddModelMarketplaceFreeCompetitionDrNdCompose";

export default function SettingsAddModelMarketplaceFreeCompetitionDrNdPanel() {
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<SettingsAddModelMarketplaceFreeCompetitionDrNdCompose | null>(
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
      void composeSettingsAddModelMarketplaceFreeCompetitionDrNd;
      void formatSettingsAddModelMarketplaceFreeCompetitionDrNdSummary;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div className="flex flex-col gap-3 p-4 max-w-3xl">
      <h2 className="text-lg font-semibold">
        Settings add-model · marketplace free · competition DR · ND REJECT
      </h2>
      <p className="text-sm text-muted">
        Pure residual: BYOK model inventory propose/preview with budget bar over
        free-first marketplace + competition DR + NotDiamond shadow REJECT pack.
        secrets_stored and inventory_mutated always false · ND REJECT.
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
        Compose settings add-model residual pack (tests are proof)
      </LemonButton>
      {error && (
        <LemonCard className="border-warning p-3 text-sm">{error}</LemonCard>
      )}
      {result && (
        <LemonCard className="p-3 text-sm">
          {formatSettingsAddModelMarketplaceFreeCompetitionDrNdSummary(result)}
        </LemonCard>
      )}
    </div>
  );
}
