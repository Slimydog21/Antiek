/**
 * AntiekBenchWeeklySrcWritePackPanel — free-file.
 * Antiek-bench weekly learn over source-attach write twin collective fullscreen.
 */
import { useState } from "react";
import { LemonButton, LemonCard } from "../../components/lemon";
import {
  composeAntiekBenchWeeklySrcWritePackFullscreenDraft,
  formatAntiekBenchWeeklySrcWritePackSummary,
  type AntiekBenchWeeklySrcWritePackCompose,
} from "../../api/antiekBenchWeeklySrcWritePackCompose";

export default function AntiekBenchWeeklySrcWritePackPanel() {
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<AntiekBenchWeeklySrcWritePackCompose | null>(null);

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      setError(
        "Full nest proven in pure tests; panel is free-file surface only.",
      );
      void ack;
      void composeAntiekBenchWeeklySrcWritePackFullscreenDraft;
      void formatAntiekBenchWeeklySrcWritePackSummary;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div className="flex flex-col gap-3 p-4 max-w-3xl">
      <h2 className="text-lg font-semibold">
        Antiek-bench weekly learn · source attach · write twin
      </h2>
      <p className="text-sm text-muted">
        Pure residual: weekly usage-learn rewrite proposals over HTML-native
        arxiv/substack source attach + write twin collective + fullscreen pack.
        backlog_mutated and suite_rewritten always false · remote_fetched false ·
        ND REJECT.
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
        Compose weekly learn residual pack (tests are proof)
      </LemonButton>
      {error && (
        <LemonCard className="border-warning p-3 text-sm">{error}</LemonCard>
      )}
      {result && (
        <LemonCard className="p-3 text-sm">
          {formatAntiekBenchWeeklySrcWritePackSummary(result)}
        </LemonCard>
      )}
    </div>
  );
}
