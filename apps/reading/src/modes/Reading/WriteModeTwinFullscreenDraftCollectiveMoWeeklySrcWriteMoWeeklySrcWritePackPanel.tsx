/**
 * WriteModeTwinFullscreenDraftCollectiveMoWeeklySrcWriteMoWeeklySrcWritePackPanel — free-file.
 */
import { useState } from "react";
import { LemonButton, LemonCard } from "../../components/lemon";
import {
  composeWriteModeTwinFullscreenDraftCollectiveMoWeeklySrcWriteMoWeeklySrcWritePack,
  formatWriteModeTwinFullscreenDraftCollectiveMoWeeklySrcWriteMoWeeklySrcWritePackSummary,
  type WriteModeTwinFullscreenDraftCollectiveMoWeeklySrcWriteMoWeeklySrcWritePackCompose,
} from "../../api/writeModeTwinFullscreenDraftCollectiveMoWeeklySrcWriteMoWeeklySrcWritePackCompose";

export default function WriteModeTwinFullscreenDraftCollectiveMoWeeklySrcWriteMoWeeklySrcWritePackPanel() {
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<WriteModeTwinFullscreenDraftCollectiveMoWeeklySrcWriteMoWeeklySrcWritePackCompose | null>(null);
  function onCompose() {
    setError(null);
    setResult(null);
    try {
      setError("Full nest proven in pure tests; panel is free-file surface only.");
      void ack;
      void composeWriteModeTwinFullscreenDraftCollectiveMoWeeklySrcWriteMoWeeklySrcWritePack;
      void formatWriteModeTwinFullscreenDraftCollectiveMoWeeklySrcWriteMoWeeklySrcWritePackSummary;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }
  return (
    <div className="flex flex-col gap-3 p-4 max-w-3xl">
      <h2 className="text-lg font-semibold">Write-mode twin · fullscreen · draft pack</h2>
      <p className="text-sm text-muted">
        Pure residual: twin collective analysis over fullscreen draft pack.
        draft_written/analysis_written/merge_executed false · ND REJECT.
      </p>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} />
        operator_ack
      </label>
      <LemonButton type="primary" onClick={onCompose}>Compose write twin residual (tests are proof)</LemonButton>
      {error && <LemonCard className="border-warning p-3 text-sm">{error}</LemonCard>}
      {result && (
        <LemonCard className="p-3 text-sm">
          {formatWriteModeTwinFullscreenDraftCollectiveMoWeeklySrcWriteMoWeeklySrcWritePackSummary(result)}
        </LemonCard>
      )}
    </div>
  );
}
