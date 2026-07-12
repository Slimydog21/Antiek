/**
 * DraftBeforeMergeMoPriceCeilingRecursiveTwinPanel — free-file.
 * Draft-before-merge over MO price-ceiling recursive twin pack.
 */
import { useState } from "react";
import { LemonButton, LemonCard } from "../../components/lemon";
import {
  composeDraftBeforeMergeMoPriceCeilingRecursiveTwin,
  formatDraftBeforeMergeMoPriceCeilingRecursiveTwinSummary,
  type DraftBeforeMergeMoPriceCeilingRecursiveTwinCompose,
} from "../../api/draftBeforeMergeMoPriceCeilingRecursiveTwinCompose";

export default function DraftBeforeMergeMoPriceCeilingRecursiveTwinPanel() {
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<DraftBeforeMergeMoPriceCeilingRecursiveTwinCompose | null>(null);

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      setError(
        "Full nest proven in pure tests; panel is free-file surface only.",
      );
      void ack;
      void composeDraftBeforeMergeMoPriceCeilingRecursiveTwin;
      void formatDraftBeforeMergeMoPriceCeilingRecursiveTwinSummary;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div className="flex flex-col gap-3 p-4 max-w-3xl">
      <h2 className="text-lg font-semibold">
        Draft-before-merge · MO price ceiling · recursive twin
      </h2>
      <p className="text-sm text-muted">
        Pure residual: provisional combined draft gate before full parent merge
        over Midnight Oil price-ceiling + recursive twin note-taker pack.
        draft_written=false · merge_executed=false · live_execution_authorized=false
        · ND REJECT.
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
        Compose draft-before-merge residual pack (tests are proof)
      </LemonButton>
      {error && (
        <LemonCard className="border-warning p-3 text-sm">{error}</LemonCard>
      )}
      {result && (
        <LemonCard className="p-3 text-sm">
          {formatDraftBeforeMergeMoPriceCeilingRecursiveTwinSummary(result)}
        </LemonCard>
      )}
    </div>
  );
}
