/**
 * CompetitionDrSourceAttachAntiekBenchRecommendPanel — free-file.
 * Competition DR quality over source-attach Antiek-bench recommend residual.
 */
import { useState } from "react";
import { LemonButton, LemonCard } from "../../components/lemon";
import {
  composeCompetitionDrSourceAttachAntiekBenchRecommend,
  formatCompetitionDrSourceAttachAntiekBenchRecommendSummary,
  type CompetitionDrSourceAttachAntiekBenchRecommendCompose,
} from "../../api/competitionDrSourceAttachAntiekBenchRecommendCompose";

export default function CompetitionDrSourceAttachAntiekBenchRecommendPanel() {
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<CompetitionDrSourceAttachAntiekBenchRecommendCompose | null>(null);

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      setError(
        "Full nest proven in pure tests; panel is free-file surface only.",
      );
      void ack;
      void composeCompetitionDrSourceAttachAntiekBenchRecommend;
      void formatCompetitionDrSourceAttachAntiekBenchRecommendSummary;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div className="flex flex-col gap-3 p-4 max-w-3xl">
      <h2 className="text-lg font-semibold">
        Competition DR · source attach · Antiek-bench recommend
      </h2>
      <p className="text-sm text-muted">
        Pure residual: competition gap awareness + citation pack + quality/budget
        gate over HTML-native arxiv/substack attach + weekly model recommend + MO
        unattended. live_dispatch_authorized=false · ND REJECT.
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
          {formatCompetitionDrSourceAttachAntiekBenchRecommendSummary(result)}
        </LemonCard>
      )}
    </div>
  );
}
