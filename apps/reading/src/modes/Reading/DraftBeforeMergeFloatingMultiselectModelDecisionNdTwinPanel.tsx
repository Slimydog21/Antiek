/**
 * DraftBeforeMergeFloatingMultiselectModelDecisionNdTwinPanel — free-file.
 * Draft-before-full-merge gate over floating multi-select model decision ND twin.
 */
import { useState } from "react";
import { LemonButton, LemonCard } from "../../components/lemon";
import {
  composeDraftBeforeMergeFloatingMultiselectModelDecisionNdTwin,
  formatDraftBeforeMergeFloatingMultiselectModelDecisionNdTwinSummary,
  type DraftBeforeMergeFloatingMultiselectModelDecisionNdTwinCompose,
} from "../../api/draftBeforeMergeFloatingMultiselectModelDecisionNdTwinCompose";

export default function DraftBeforeMergeFloatingMultiselectModelDecisionNdTwinPanel() {
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<DraftBeforeMergeFloatingMultiselectModelDecisionNdTwinCompose | null>(
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
      void composeDraftBeforeMergeFloatingMultiselectModelDecisionNdTwin;
      void formatDraftBeforeMergeFloatingMultiselectModelDecisionNdTwinSummary;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div className="flex flex-col gap-3 p-4 max-w-3xl">
      <h2 className="text-lg font-semibold">
        Draft-before-merge · floating multi-select · model decision ND twin
      </h2>
      <p className="text-sm text-muted">
        Pure residual: provisional combined draft from floating sources before
        full parent merge, over multi-select cohesive unit + model decision
        budget + twin-search HTML-native ND twin pack. draft_written and
        merge_executed always false · ND REJECT.
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
          {formatDraftBeforeMergeFloatingMultiselectModelDecisionNdTwinSummary(
            result,
          )}
        </LemonCard>
      )}
    </div>
  );
}
