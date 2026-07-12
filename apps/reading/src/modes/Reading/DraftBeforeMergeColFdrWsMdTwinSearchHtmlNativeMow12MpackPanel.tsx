/**
 * DraftBeforeMergeColFdrWsMdTwinSearchHtmlNativeMow12MpackPanel — free-file.
 */
import { useState } from "react";
import { LemonButton, LemonCard } from "../../components/lemon";
import {
  composeDraftBeforeMergeColFdrWsMdTwinSearchHtmlNativeMow12Mpack,
  formatDraftBeforeMergeColFdrWsMdTwinSearchHtmlNativeMow12MpackSummary,
  type DraftBeforeMergeColFdrWsMdTwinSearchHtmlNativeMow12MpackCompose,
} from "../../api/draftBeforeMergeColFdrWsMdTwinSearchHtmlNativeMow12MpackCompose";

export default function DraftBeforeMergeColFdrWsMdTwinSearchHtmlNativeMow12MpackPanel() {
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<DraftBeforeMergeColFdrWsMdTwinSearchHtmlNativeMow12MpackCompose | null>(null);
  function onCompose() {
    setError(null); setResult(null);
    try {
      setError("Full nest proven in pure tests; panel is free-file surface only.");
      void ack;
      void composeDraftBeforeMergeColFdrWsMdTwinSearchHtmlNativeMow12Mpack;
      void formatDraftBeforeMergeColFdrWsMdTwinSearchHtmlNativeMow12MpackSummary;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }
  return (
    <div className="flex flex-col gap-3 p-4 max-w-3xl">
      <h2 className="text-lg font-semibold">Draft-before-merge · collective · floating DR mow12</h2>
      <p className="text-sm text-muted">
        Pure residual: provisional combined draft gate over collective multiselect +
        floating DR MD mow12. draft_written / merge_executed always false.
      </p>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} />
        operator_ack
      </label>
      <LemonButton type="primary" onClick={onCompose}>Compose draft-before-merge residual (tests are proof)</LemonButton>
      {error && <LemonCard className="border-warning p-3 text-sm">{error}</LemonCard>}
      {result && (
        <LemonCard className="p-3 text-sm font-mono">
          {formatDraftBeforeMergeColFdrWsMdTwinSearchHtmlNativeMow12MpackSummary(result)}
        </LemonCard>
      )}
    </div>
  );
}
