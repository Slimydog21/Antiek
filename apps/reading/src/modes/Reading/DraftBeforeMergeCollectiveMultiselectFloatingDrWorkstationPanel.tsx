/**
 * DraftBeforeMergeCollectiveMultiselectFloatingDrWorkstationPanel — free-file.
 * Draft-before-merge gate over collective multiselect floating DR workstation residual.
 */
import { useState } from "react";
import { LemonButton, LemonCard } from "../../components/lemon";
import {
  composeDraftBeforeMergeCollectiveMultiselectFloatingDrWorkstation,
  formatDraftBeforeMergeCollectiveMultiselectFloatingDrWorkstationSummary,
  type DraftBeforeMergeCollectiveMultiselectFloatingDrWorkstationCompose,
} from "../../api/draftBeforeMergeCollectiveMultiselectFloatingDrWorkstationCompose";

export default function DraftBeforeMergeCollectiveMultiselectFloatingDrWorkstationPanel() {
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<DraftBeforeMergeCollectiveMultiselectFloatingDrWorkstationCompose | null>(
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
      void composeDraftBeforeMergeCollectiveMultiselectFloatingDrWorkstation;
      void formatDraftBeforeMergeCollectiveMultiselectFloatingDrWorkstationSummary;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div className="flex flex-col gap-3 p-4 max-w-3xl">
      <h2 className="text-lg font-semibold">
        Draft-before-merge · collective multiselect · floating DR workstation
      </h2>
      <p className="text-sm text-muted">
        Pure residual: provisional combined draft before full parent merge over
        collective multiselect cohesive unit + highlight floating DR +
        workstation records. draft_written/merge_executed false · ND REJECT.
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
          {formatDraftBeforeMergeCollectiveMultiselectFloatingDrWorkstationSummary(
            result,
          )}
        </LemonCard>
      )}
    </div>
  );
}
