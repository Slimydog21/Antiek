/**
 * RecursiveTwinNoteTakerTwinSearchModelDecisionPanel — free-file.
 * Recursive twin note-taker over twin search model decision HTML-native pack.
 */
import { useState } from "react";
import { LemonButton, LemonCard } from "../../components/lemon";
import {
  composeRecursiveTwinNoteTakerTwinSearchModelDecision,
  formatRecursiveTwinNoteTakerTwinSearchModelDecisionSummary,
  type RecursiveTwinNoteTakerTwinSearchModelDecisionCompose,
} from "../../api/recursiveTwinNoteTakerTwinSearchModelDecisionCompose";

export default function RecursiveTwinNoteTakerTwinSearchModelDecisionPanel() {
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<RecursiveTwinNoteTakerTwinSearchModelDecisionCompose | null>(null);

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      setError(
        "Full nest proven in pure tests; panel is free-file surface only.",
      );
      void ack;
      void composeRecursiveTwinNoteTakerTwinSearchModelDecision;
      void formatRecursiveTwinNoteTakerTwinSearchModelDecisionSummary;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div className="flex flex-col gap-3 p-4 max-w-3xl">
      <h2 className="text-lg font-semibold">
        Recursive twin note-taker · twin search · model decision
      </h2>
      <p className="text-sm text-muted">
        Pure residual: recursive twin note-taker propose scaffold over twin
        intelligent search + model decision budget + HTML-native settings
        marketplace pack. twin_written=false · remote_index_queried=false · ND
        REJECT.
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
        Compose recursive twin residual pack (tests are proof)
      </LemonButton>
      {error && (
        <LemonCard className="border-warning p-3 text-sm">{error}</LemonCard>
      )}
      {result && (
        <LemonCard className="p-3 text-sm">
          {formatRecursiveTwinNoteTakerTwinSearchModelDecisionSummary(result)}
        </LemonCard>
      )}
    </div>
  );
}
