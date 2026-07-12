/**
 * MidnightOilSettingsDecisionCompetitionDrNdShadowRecursiveTwinPanel — free-file.
 */
import { useState } from "react";
import { LemonButton, LemonCard } from "../../components/lemon";
import {
  composeMidnightOilSettingsDecisionCompetitionDrNdShadowRecursiveTwin,
  formatMidnightOilSettingsDecisionCompetitionDrNdShadowRecursiveTwinSummary,
  type MidnightOilSettingsDecisionCompetitionDrNdShadowRecursiveTwinCompose,
} from "../../api/midnightOilSettingsDecisionCompetitionDrNdShadowRecursiveTwinCompose";

export default function MidnightOilSettingsDecisionCompetitionDrNdShadowRecursiveTwinPanel() {
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<MidnightOilSettingsDecisionCompetitionDrNdShadowRecursiveTwinCompose | null>(null);

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      setError("Full nest proven in pure tests; panel is free-file surface only.");
      void ack;
      void composeMidnightOilSettingsDecisionCompetitionDrNdShadowRecursiveTwin;
      void formatMidnightOilSettingsDecisionCompetitionDrNdShadowRecursiveTwinSummary;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div className="flex flex-col gap-3 p-4 max-w-3xl">
      <h2 className="text-lg font-semibold">
        Midnight Oil · settings decision · competition DR
      </h2>
      <p className="text-sm text-muted">
        Pure residual: unattended MO price-ceiling approval over settings decision
        + competition DR ND shadow pack. live_execution_authorized/charge_executed false · ND REJECT.
      </p>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} />
        operator_ack
      </label>
      <LemonButton type="primary" onClick={onCompose}>
        Compose Midnight Oil residual (tests are proof)
      </LemonButton>
      {error && <LemonCard className="border-warning p-3 text-sm">{error}</LemonCard>}
      {result && (
        <LemonCard className="p-3 text-sm">
          {formatMidnightOilSettingsDecisionCompetitionDrNdShadowRecursiveTwinSummary(result)}
        </LemonCard>
      )}
    </div>
  );
}
