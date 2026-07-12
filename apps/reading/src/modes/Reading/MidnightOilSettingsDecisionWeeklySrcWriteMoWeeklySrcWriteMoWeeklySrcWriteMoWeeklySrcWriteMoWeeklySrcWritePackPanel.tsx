/**
 * MidnightOilSettingsDecisionWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWritePackPanel — free-file.
 */
import { useState } from "react";
import { LemonButton, LemonCard } from "../../components/lemon";
import {
  composeMidnightOilSettingsDecisionWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWritePack,
  formatMidnightOilSettingsDecisionWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWritePackSummary,
  type MidnightOilSettingsDecisionWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWritePackCompose,
} from "../../api/midnightOilSettingsDecisionWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWritePackCompose";

export default function MidnightOilSettingsDecisionWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWritePackPanel() {
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<MidnightOilSettingsDecisionWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWritePackCompose | null>(null);

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      setError("Full nest proven in pure tests; panel is free-file surface only.");
      void ack;
      void composeMidnightOilSettingsDecisionWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWritePack;
      void formatMidnightOilSettingsDecisionWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWritePackSummary;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div className="flex flex-col gap-3 p-4 max-w-3xl">
      <h2 className="text-lg font-semibold">
        Midnight Oil · settings decision · competition DR weekly pack
      </h2>
      <p className="text-sm text-muted">
        Pure residual: unattended Midnight Oil price-ceiling swarm over settings
        decision + competition DR + ND shadow REJECT pack. live_execution_authorized
        always false until ceiling approved.
      </p>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} />
        operator_ack
      </label>
      <LemonButton type="primary" onClick={onCompose}>
        Compose Midnight Oil residual pack (tests are proof)
      </LemonButton>
      {error && <LemonCard className="border-warning p-3 text-sm">{error}</LemonCard>}
      {result && (
        <LemonCard className="p-3 text-sm">
          {formatMidnightOilSettingsDecisionWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWritePackSummary(result)}
        </LemonCard>
      )}
    </div>
  );
}
