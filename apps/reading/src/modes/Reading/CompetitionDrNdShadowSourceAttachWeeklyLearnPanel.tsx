/**
 * CompetitionDrNdShadowSourceAttachWeeklyLearnPanel — free-file.
 * Competition DR quality over ND shadow source-attach weekly learn pack.
 */
import { useState } from "react";
import { LemonButton, LemonCard } from "../../components/lemon";
import {
  composeCompetitionDrNdShadowSourceAttachWeeklyLearn,
  formatCompetitionDrNdShadowSourceAttachWeeklyLearnSummary,
  type CompetitionDrNdShadowSourceAttachWeeklyLearnCompose,
} from "../../api/competitionDrNdShadowSourceAttachWeeklyLearnCompose";

export default function CompetitionDrNdShadowSourceAttachWeeklyLearnPanel() {
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<CompetitionDrNdShadowSourceAttachWeeklyLearnCompose | null>(null);

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      setError(
        "Full nest proven in pure tests; panel is free-file surface only.",
      );
      void ack;
      void composeCompetitionDrNdShadowSourceAttachWeeklyLearn;
      void formatCompetitionDrNdShadowSourceAttachWeeklyLearnSummary;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div className="flex flex-col gap-3 p-4 max-w-3xl">
      <h2 className="text-lg font-semibold">
        Competition DR · ND shadow REJECT · source-attach weekly learn
      </h2>
      <p className="text-sm text-muted">
        Pure residual: competition gap awareness + citation pack + quality gate
        over NotDiamond shadow REJECT + arxiv/substack attach + Antiek-bench
        weekly learn + twin presentation pack. Never live-dispatches · ND REJECT.
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
          {formatCompetitionDrNdShadowSourceAttachWeeklyLearnSummary(result)}
        </LemonCard>
      )}
    </div>
  );
}
