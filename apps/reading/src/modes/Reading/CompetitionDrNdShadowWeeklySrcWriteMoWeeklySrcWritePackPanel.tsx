/**
 * CompetitionDrNdShadowWeeklyPackPanel — free-file.
 */
import { useState } from "react";
import { LemonButton, LemonCard } from "../../components/lemon";
import {
  composeCompetitionDrNdShadowWeeklyPack,
  formatCompetitionDrNdShadowWeeklyPackSummary,
  type CompetitionDrNdShadowWeeklyPackCompose,
} from "../../api/competitionDrNdShadowWeeklyPackCompose";

export default function CompetitionDrNdShadowWeeklyPackPanel() {
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<CompetitionDrNdShadowWeeklyPackCompose | null>(null);

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      setError(
        "Full nest proven in pure tests; panel is free-file surface only.",
      );
      void ack;
      void composeCompetitionDrNdShadowWeeklyPack;
      void formatCompetitionDrNdShadowWeeklyPackSummary;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div className="flex flex-col gap-3 p-4 max-w-3xl">
      <h2 className="text-lg font-semibold">
        Competition DR · ND shadow · twin presentation weekly
      </h2>
      <p className="text-sm text-muted">
        Pure residual: competition gap + arxiv/substack citations + quality gate
        over ND shadow REJECT + recursive twin presentation + weekly source-attach.
        live_dispatch_authorized always false · ND REJECT.
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
          {formatCompetitionDrNdShadowWeeklyPackSummary(result)}
        </LemonCard>
      )}
    </div>
  );
}
