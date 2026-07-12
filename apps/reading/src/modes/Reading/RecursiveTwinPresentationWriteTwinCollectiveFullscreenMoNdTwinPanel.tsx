/**
 * RecursiveTwinPresentationWriteTwinCollectiveFullscreenMoNdTwinPanel — free-file.
 * Recursive twin presentation over write twin collective fullscreen MO ND twin.
 */
import { useState } from "react";
import { LemonButton, LemonCard } from "../../components/lemon";
import {
  composeRecursiveTwinPresentationWriteTwinCollectiveFullscreenMoNdTwin,
  formatRecursiveTwinPresentationWriteTwinCollectiveFullscreenMoNdTwinSummary,
  type RecursiveTwinPresentationWriteTwinCollectiveFullscreenMoNdTwinCompose,
} from "../../api/recursiveTwinPresentationWriteTwinCollectiveFullscreenMoNdTwinCompose";

export default function RecursiveTwinPresentationWriteTwinCollectiveFullscreenMoNdTwinPanel() {
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<RecursiveTwinPresentationWriteTwinCollectiveFullscreenMoNdTwinCompose | null>(
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
      void composeRecursiveTwinPresentationWriteTwinCollectiveFullscreenMoNdTwin;
      void formatRecursiveTwinPresentationWriteTwinCollectiveFullscreenMoNdTwinSummary;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div className="flex flex-col gap-3 p-4 max-w-3xl">
      <h2 className="text-lg font-semibold">
        Recursive twin presentation · write collective · fullscreen MO ND twin
      </h2>
      <p className="text-sm text-muted">
        Pure residual: present twin insights/questions as side-panel / overlay /
        fullscreen while write twin collective + fullscreen + Midnight Oil
        unattended + draft multiselect ND twin remain pure. twin_written and
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
        Compose twin presentation residual pack (tests are proof)
      </LemonButton>
      {error && (
        <LemonCard className="border-warning p-3 text-sm">{error}</LemonCard>
      )}
      {result && (
        <LemonCard className="p-3 text-sm">
          {formatRecursiveTwinPresentationWriteTwinCollectiveFullscreenMoNdTwinSummary(
            result,
          )}
        </LemonCard>
      )}
    </div>
  );
}
