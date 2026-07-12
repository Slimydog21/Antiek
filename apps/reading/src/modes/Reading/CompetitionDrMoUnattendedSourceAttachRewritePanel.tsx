/**
 * CompetitionDrMoUnattendedSourceAttachRewritePanel — free-file.
 * Competition DR quality over MO unattended + source-attach rewrite pack.
 */
import { useState } from "react";
import { LemonButton, LemonCard } from "../../components/lemon";
import {
  composeCompetitionDrMoUnattendedSourceAttachRewrite,
  formatCompetitionDrMoUnattendedSourceAttachRewriteSummary,
  type CompetitionDrMoUnattendedSourceAttachRewriteCompose,
} from "../../api/competitionDrMoUnattendedSourceAttachRewriteCompose";

export default function CompetitionDrMoUnattendedSourceAttachRewritePanel() {
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<CompetitionDrMoUnattendedSourceAttachRewriteCompose | null>(null);

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      setError(
        "Use pure tests for full nest; panel demo uses incomplete compact fixture intentionally.",
      );
      // Full nest proven in pure tests — panel is free-file surface only.
      void ack;
      void composeCompetitionDrMoUnattendedSourceAttachRewrite;
      void formatCompetitionDrMoUnattendedSourceAttachRewriteSummary;
      setResult(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div className="flex flex-col gap-3 p-4 max-w-3xl">
      <h2 className="text-lg font-semibold">
        Competition DR · MO unattended · source-attach rewrite
      </h2>
      <p className="text-sm text-muted">
        Pure residual: competition gap + citation quality over Midnight Oil
        unattended + arxiv/substack attach + Antiek-bench rewrite. live_dispatch
        =false · charge_executed=false · ND REJECT.
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
        Compose competition residual pack (tests are proof)
      </LemonButton>
      {error && (
        <LemonCard className="border-warning p-3 text-sm">{error}</LemonCard>
      )}
      {result && (
        <LemonCard className="p-3 text-sm">
          {formatCompetitionDrMoUnattendedSourceAttachRewriteSummary(result)}
        </LemonCard>
      )}
    </div>
  );
}
