/**
 * RecursiveTwinPresentationWeeklySourceAttachWriteTwinFullscreenDraftPanel — free-file.
 */
import { useState } from "react";
import { LemonButton, LemonCard } from "../../components/lemon";
import {
  composeRecursiveTwinPresentationWeeklySourceAttachWriteTwinFullscreenDraft,
  formatRecursiveTwinPresentationWeeklySourceAttachWriteTwinFullscreenDraftSummary,
  type RecursiveTwinPresentationWeeklySourceAttachWriteTwinFullscreenDraftCompose,
} from "../../api/recursiveTwinPresentationWeeklySourceAttachWriteTwinFullscreenDraftCompose";

export default function RecursiveTwinPresentationWeeklySourceAttachWriteTwinFullscreenDraftPanel() {
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<RecursiveTwinPresentationWeeklySourceAttachWriteTwinFullscreenDraftCompose | null>(null);

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      setError("Full nest proven in pure tests; panel is free-file surface only.");
      void ack;
      void composeRecursiveTwinPresentationWeeklySourceAttachWriteTwinFullscreenDraft;
      void formatRecursiveTwinPresentationWeeklySourceAttachWriteTwinFullscreenDraftSummary;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div className="flex flex-col gap-3 p-4 max-w-3xl">
      <h2 className="text-lg font-semibold">
        Recursive twin presentation · weekly · source-attach write twin
      </h2>
      <p className="text-sm text-muted">
        Pure residual: recursive twin presentation over Antiek-bench weekly +
        source-attach write twin fullscreen draft pack. twin_written false · ND REJECT.
      </p>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} />
        operator_ack
      </label>
      <LemonButton type="primary" onClick={onCompose}>
        Compose twin presentation residual (tests are proof)
      </LemonButton>
      {error && <LemonCard className="border-warning p-3 text-sm">{error}</LemonCard>}
      {result && (
        <LemonCard className="p-3 text-sm">
          {formatRecursiveTwinPresentationWeeklySourceAttachWriteTwinFullscreenDraftSummary(result)}
        </LemonCard>
      )}
    </div>
  );
}
