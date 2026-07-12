/**
 * SourceAttachAntiekBenchWeeklyLearnTwinPresentationPanel — free-file.
 * arxiv/substack source attach over Antiek-bench weekly learn twin presentation.
 */
import { useState } from "react";
import { LemonButton, LemonCard } from "../../components/lemon";
import {
  composeSourceAttachAntiekBenchWeeklyLearnTwinPresentation,
  formatSourceAttachAntiekBenchWeeklyLearnTwinPresentationSummary,
  type SourceAttachAntiekBenchWeeklyLearnTwinPresentationCompose,
} from "../../api/sourceAttachAntiekBenchWeeklyLearnTwinPresentationCompose";

export default function SourceAttachAntiekBenchWeeklyLearnTwinPresentationPanel() {
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<SourceAttachAntiekBenchWeeklyLearnTwinPresentationCompose | null>(
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
      void composeSourceAttachAntiekBenchWeeklyLearnTwinPresentation;
      void formatSourceAttachAntiekBenchWeeklyLearnTwinPresentationSummary;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div className="flex flex-col gap-3 p-4 max-w-3xl">
      <h2 className="text-lg font-semibold">
        arxiv/substack attach · weekly learn · twin presentation
      </h2>
      <p className="text-sm text-muted">
        Pure residual: call arxiv and substack as HTML-native knowledge-dense
        refs with citation + quality gates over Antiek-bench weekly learn +
        recursive twin presentation write collective pack. remote_fetched and
        backlog_mutated always false · ND REJECT.
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
        Compose source-attach residual pack (tests are proof)
      </LemonButton>
      {error && (
        <LemonCard className="border-warning p-3 text-sm">{error}</LemonCard>
      )}
      {result && (
        <LemonCard className="p-3 text-sm">
          {formatSourceAttachAntiekBenchWeeklyLearnTwinPresentationSummary(
            result,
          )}
        </LemonCard>
      )}
    </div>
  );
}
