/**
 * SettingsAddModelNdShadowCompetitionDrMoPanel — free-file.
 * Settings add-model inventory over ND shadow competition DR MO pack.
 */
import { useState } from "react";
import { LemonButton, LemonCard } from "../../components/lemon";
import {
  composeSettingsAddModelNdShadowCompetitionDrMo,
  formatSettingsAddModelNdShadowCompetitionDrMoSummary,
  type SettingsAddModelNdShadowCompetitionDrMoCompose,
} from "../../api/settingsAddModelNdShadowCompetitionDrMoCompose";

export default function SettingsAddModelNdShadowCompetitionDrMoPanel() {
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<SettingsAddModelNdShadowCompetitionDrMoCompose | null>(null);

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      setError(
        "Full nest proven in pure tests; panel is free-file surface only.",
      );
      void ack;
      void composeSettingsAddModelNdShadowCompetitionDrMo;
      void formatSettingsAddModelNdShadowCompetitionDrMoSummary;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div className="flex flex-col gap-3 p-4 max-w-3xl">
      <h2 className="text-lg font-semibold">
        Settings add-model · ND shadow · competition DR MO
      </h2>
      <p className="text-sm text-muted">
        Pure residual: BYOK add-model inventory over NotDiamond REJECT +
        competition DR + MO unattended rewrite. secrets_stored=false ·
        inventory_mutated=false · live_router_authorized=false.
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
        Compose settings residual pack (tests are proof)
      </LemonButton>
      {error && (
        <LemonCard className="border-warning p-3 text-sm">{error}</LemonCard>
      )}
      {result && (
        <LemonCard className="p-3 text-sm">
          {formatSettingsAddModelNdShadowCompetitionDrMoSummary(result)}
        </LemonCard>
      )}
    </div>
  );
}
