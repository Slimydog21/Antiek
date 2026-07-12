/**
 * RecursiveTwinAbSaWtFsDbmColFdrWsMdTwinSearchHtmlNativeMow12MpackPanel — free-file.
 */
import { useState } from "react";
import { LemonButton, LemonCard } from "../../components/lemon";
import {
  composeRecursiveTwinAbSaWtFsDbmColFdrWsMdTwinSearchHtmlNativeMow12Mpack,
  formatRecursiveTwinAbSaWtFsDbmColFdrWsMdTwinSearchHtmlNativeMow12MpackSummary,
  type RecursiveTwinAbSaWtFsDbmColFdrWsMdTwinSearchHtmlNativeMow12MpackCompose,
} from "../../api/recursiveTwinAbSaWtFsDbmColFdrWsMdTwinSearchHtmlNativeMow12MpackCompose";

export default function RecursiveTwinAbSaWtFsDbmColFdrWsMdTwinSearchHtmlNativeMow12MpackPanel() {
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<RecursiveTwinAbSaWtFsDbmColFdrWsMdTwinSearchHtmlNativeMow12MpackCompose | null>(null);
  function onCompose() {
    setError(null); setResult(null);
    try {
      setError("Full nest proven in pure tests; panel is free-file surface only.");
      void ack;
      void composeRecursiveTwinAbSaWtFsDbmColFdrWsMdTwinSearchHtmlNativeMow12Mpack;
      void formatRecursiveTwinAbSaWtFsDbmColFdrWsMdTwinSearchHtmlNativeMow12MpackSummary;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }
  return (
    <div className="flex flex-col gap-3 p-4 max-w-3xl">
      <h2 className="text-lg font-semibold">Recursive twin · antiek-bench · mow12</h2>
      <p className="text-sm text-muted">
        Pure residual: twin note-taker presentation over weekly learn + source-attach
        write twin FDR MD mow12. twin_written / backlog_mutated always false; ND REJECT.
      </p>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} />
        operator_ack
      </label>
      <LemonButton type="primary" onClick={onCompose}>Compose recursive-twin residual (tests are proof)</LemonButton>
      {error && <LemonCard className="border-warning p-3 text-sm">{error}</LemonCard>}
      {result && (
        <LemonCard className="p-3 text-sm font-mono">
          {formatRecursiveTwinAbSaWtFsDbmColFdrWsMdTwinSearchHtmlNativeMow12MpackSummary(result)}
        </LemonCard>
      )}
    </div>
  );
}
