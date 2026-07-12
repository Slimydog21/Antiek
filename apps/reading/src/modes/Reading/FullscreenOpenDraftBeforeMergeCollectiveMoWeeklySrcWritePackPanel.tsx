/**
 * FullscreenOpenDraftBeforeMergeCollectiveMoWeeklySrcWritePackPanel — free-file.
 * Fullscreen-open over draft-before-merge collective multiselect residual.
 */
import { useState } from "react";
import { LemonButton, LemonCard } from "../../components/lemon";
import {
  composeFullscreenOpenDraftBeforeMergeCollectiveMoWeeklySrcWritePack,
  formatFullscreenOpenDraftBeforeMergeCollectiveMoWeeklySrcWritePackSummary,
  type FullscreenOpenDraftBeforeMergeCollectiveMoWeeklySrcWritePackCompose,
} from "../../api/fullscreenOpenDraftBeforeMergeCollectiveMultiselectCompose";

export default function FullscreenOpenDraftBeforeMergeCollectiveMoWeeklySrcWritePackPanel() {
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<FullscreenOpenDraftBeforeMergeCollectiveMoWeeklySrcWritePackCompose | null>(
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
      void composeFullscreenOpenDraftBeforeMergeCollectiveMoWeeklySrcWritePack;
      void formatFullscreenOpenDraftBeforeMergeCollectiveMoWeeklySrcWritePackSummary;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div className="flex flex-col gap-3 p-4 max-w-3xl">
      <h2 className="text-lg font-semibold">
        Fullscreen · draft-before-merge · collective multiselect
      </h2>
      <p className="text-sm text-muted">
        Pure residual: open floating deep research fullscreen over provisional
        draft-before-merge + collective multiselect + floating DR workstation
        pack. live_dispatched/merge_executed false · ND REJECT.
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
        Compose fullscreen residual pack (tests are proof)
      </LemonButton>
      {error && (
        <LemonCard className="border-warning p-3 text-sm">{error}</LemonCard>
      )}
      {result && (
        <LemonCard className="p-3 text-sm">
          {formatFullscreenOpenDraftBeforeMergeCollectiveMoWeeklySrcWritePackSummary(
            result,
          )}
        </LemonCard>
      )}
    </div>
  );
}
