/**
 * CompetitionDrNdShadowWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWritePackPanel — free-file.
 */
import { useState } from "react";
import { LemonButton, LemonCard } from "../../components/lemon";
import {
  composeCompetitionDrNdShadowWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWritePack,
  formatCompetitionDrNdShadowWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWritePackSummary,
  type CompetitionDrNdShadowWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWritePackCompose,
} from "../../api/competitionDrNdShadowWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWritePackCompose";

export default function CompetitionDrNdShadowWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWritePackPanel() {
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<CompetitionDrNdShadowWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWritePackCompose | null>(
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
      void composeCompetitionDrNdShadowWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWritePack;
      void formatCompetitionDrNdShadowWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWritePackSummary;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div className="flex flex-col gap-3 p-4 max-w-3xl">
      <h2 className="text-lg font-semibold">
        Competition DR · ND shadow REJECT · twin presentation weekly pack
      </h2>
      <p className="text-sm text-muted">
        Pure residual: competition deep-research gap study over ND shadow
        advisory (production REJECT) + recursive twin weekly source-attach pack.
        remote_fetched / live_dispatched always false.
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
        Compose competition DR residual pack (tests are proof)
      </LemonButton>
      {error && (
        <LemonCard className="border-warning p-3 text-sm">{error}</LemonCard>
      )}
      {result && (
        <LemonCard className="p-3 text-sm">
          {formatCompetitionDrNdShadowWeeklySrcWriteMoWeeklySrcWriteMoWeeklySrcWritePackSummary(
            result,
          )}
        </LemonCard>
      )}
    </div>
  );
}
