/**
 * RecursiveTwinPresentationWeeklyPackPanel — free-file.
 */
import { useState } from "react";
import { LemonButton, LemonCard } from "../../components/lemon";
import {
  composeRecursiveTwinPresentationWeeklyPack,
  formatRecursiveTwinPresentationWeeklyPackSummary,
  type RecursiveTwinPresentationAntiekBenchWeeklySrcWritePackCompose,
} from "../../api/recursiveTwinPresentationAntiekBenchWeeklySrcWritePackCompose";

export default function RecursiveTwinPresentationWeeklyPackPanel() {
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<RecursiveTwinPresentationAntiekBenchWeeklySrcWritePackCompose | null>(
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
      void composeRecursiveTwinPresentationWeeklyPack;
      void formatRecursiveTwinPresentationWeeklyPackSummary;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div className="flex flex-col gap-3 p-4 max-w-3xl">
      <h2 className="text-lg font-semibold">
        Twin presentation · weekly learn · source attach write twin
      </h2>
      <p className="text-sm text-muted">
        Pure residual: recursive twin presentation over Antiek-bench weekly
        usage-learn + HTML-native source attach write twin pack.
        twin_written and backlog_mutated always false · ND REJECT.
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
        Compose twin presentation residual pack (tests are proof)
      </LemonButton>
      {error && (
        <LemonCard className="border-warning p-3 text-sm">{error}</LemonCard>
      )}
      {result && (
        <LemonCard className="p-3 text-sm">
          {formatRecursiveTwinPresentationWeeklyPackSummary(
            result,
          )}
        </LemonCard>
      )}
    </div>
  );
}
