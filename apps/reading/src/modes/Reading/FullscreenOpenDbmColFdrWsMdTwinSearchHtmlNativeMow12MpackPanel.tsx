/**
 * FullscreenOpenDbmColFdrWsMdTwinSearchHtmlNativeMow12MpackPanel — free-file.
 */
import { useState } from "react";
import { LemonButton, LemonCard } from "../../components/lemon";
import {
  composeFullscreenOpenDbmColFdrWsMdTwinSearchHtmlNativeMow12Mpack,
  formatFullscreenOpenDbmColFdrWsMdTwinSearchHtmlNativeMow12MpackSummary,
  type FullscreenOpenDbmColFdrWsMdTwinSearchHtmlNativeMow12MpackCompose,
} from "../../api/fullscreenOpenDbmColFdrWsMdTwinSearchHtmlNativeMow12MpackCompose";

export default function FullscreenOpenDbmColFdrWsMdTwinSearchHtmlNativeMow12MpackPanel() {
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<FullscreenOpenDbmColFdrWsMdTwinSearchHtmlNativeMow12MpackCompose | null>(null);
  function onCompose() {
    setError(null); setResult(null);
    try {
      setError("Full nest proven in pure tests; panel is free-file surface only.");
      void ack;
      void composeFullscreenOpenDbmColFdrWsMdTwinSearchHtmlNativeMow12Mpack;
      void formatFullscreenOpenDbmColFdrWsMdTwinSearchHtmlNativeMow12MpackSummary;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }
  return (
    <div className="flex flex-col gap-3 p-4 max-w-3xl">
      <h2 className="text-lg font-semibold">Fullscreen open · draft-before-merge · mow12</h2>
      <p className="text-sm text-muted">
        Pure residual: open floating DR fullscreen over draft-before-merge collective
        FDR MD mow12 pack. live_dispatched / merge_executed always false.
      </p>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} />
        operator_ack
      </label>
      <LemonButton type="primary" onClick={onCompose}>Compose fullscreen residual (tests are proof)</LemonButton>
      {error && <LemonCard className="border-warning p-3 text-sm">{error}</LemonCard>}
      {result && (
        <LemonCard className="p-3 text-sm font-mono">
          {formatFullscreenOpenDbmColFdrWsMdTwinSearchHtmlNativeMow12MpackSummary(result)}
        </LemonCard>
      )}
    </div>
  );
}
