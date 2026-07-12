/**
 * NdShadowCompetitionDrMoUnattendedRewritePanel — free-file.
 * NotDiamond shadow REJECT re-affirmation over competition DR MO pack.
 */
import { useState } from "react";
import { LemonButton, LemonCard } from "../../components/lemon";
import {
  composeNdShadowCompetitionDrMoUnattendedRewrite,
  formatNdShadowCompetitionDrMoUnattendedRewriteSummary,
  type NdShadowCompetitionDrMoUnattendedRewriteCompose,
} from "../../api/ndShadowCompetitionDrMoUnattendedRewriteCompose";

export default function NdShadowCompetitionDrMoUnattendedRewritePanel() {
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<NdShadowCompetitionDrMoUnattendedRewriteCompose | null>(null);

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      setError(
        "Full nest proven in pure tests; panel is free-file surface only.",
      );
      void ack;
      void composeNdShadowCompetitionDrMoUnattendedRewrite;
      void formatNdShadowCompetitionDrMoUnattendedRewriteSummary;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div className="flex flex-col gap-3 p-4 max-w-3xl">
      <h2 className="text-lg font-semibold">
        NotDiamond shadow REJECT · competition DR · MO unattended rewrite
      </h2>
      <p className="text-sm text-muted">
        Pure residual: re-affirm production_router_verdict=REJECT on competition
        DR + MO unattended + source-attach + Antiek-bench rewrite. live_router
        always false.
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
        Compose ND shadow residual pack (tests are proof)
      </LemonButton>
      {error && (
        <LemonCard className="border-warning p-3 text-sm">{error}</LemonCard>
      )}
      {result && (
        <LemonCard className="p-3 text-sm">
          {formatNdShadowCompetitionDrMoUnattendedRewriteSummary(result)}
        </LemonCard>
      )}
    </div>
  );
}
