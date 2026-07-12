/**
 * AntiekBenchRecommendMoUnattendedFullscreenDraftPanel — free-file.
 * Antiek-bench recommend over MO unattended fullscreen draft residual.
 */
import { useState } from "react";
import { LemonButton, LemonCard } from "../../components/lemon";
import {
  composeAntiekBenchRecommendMoUnattendedFullscreenDraft,
  formatAntiekBenchRecommendMoUnattendedFullscreenDraftSummary,
  type AntiekBenchRecommendMoUnattendedFullscreenDraftCompose,
} from "../../api/antiekBenchRecommendMoUnattendedFullscreenDraftCompose";

export default function AntiekBenchRecommendMoUnattendedFullscreenDraftPanel() {
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<AntiekBenchRecommendMoUnattendedFullscreenDraftCompose | null>(
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
      void composeAntiekBenchRecommendMoUnattendedFullscreenDraft;
      void formatAntiekBenchRecommendMoUnattendedFullscreenDraftSummary;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div className="flex flex-col gap-3 p-4 max-w-3xl">
      <h2 className="text-lg font-semibold">
        Antiek-bench recommend · MO unattended · fullscreen draft
      </h2>
      <p className="text-sm text-muted">
        Pure residual: weekly usage → task→model recommendation into decision
        tree over Midnight Oil unattended + fullscreen draft multi-select pack.
        live_router_authorized=false · suite_rewritten=false · ND REJECT.
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
        Compose Antiek-bench recommend residual pack (tests are proof)
      </LemonButton>
      {error && (
        <LemonCard className="border-warning p-3 text-sm">{error}</LemonCard>
      )}
      {result && (
        <LemonCard className="p-3 text-sm">
          {formatAntiekBenchRecommendMoUnattendedFullscreenDraftSummary(
            result,
          )}
        </LemonCard>
      )}
    </div>
  );
}
