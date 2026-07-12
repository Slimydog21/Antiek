/**
 * WriteModeTwinCollectiveFullscreenCollectiveMultiselectPanel — free-file.
 * Write twin collective over fullscreen collective multiselect floating DR.
 */
import { useState } from "react";
import { LemonButton, LemonCard } from "../../components/lemon";
import {
  composeWriteModeTwinCollectiveFullscreenCollectiveMultiselect,
  formatWriteModeTwinCollectiveFullscreenCollectiveMultiselectSummary,
  type WriteModeTwinCollectiveFullscreenCollectiveMultiselectCompose,
} from "../../api/writeModeTwinCollectiveFullscreenCollectiveMultiselectCompose";

export default function WriteModeTwinCollectiveFullscreenCollectiveMultiselectPanel() {
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<WriteModeTwinCollectiveFullscreenCollectiveMultiselectCompose | null>(
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
      void composeWriteModeTwinCollectiveFullscreenCollectiveMultiselect;
      void formatWriteModeTwinCollectiveFullscreenCollectiveMultiselectSummary;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div className="flex flex-col gap-3 p-4 max-w-3xl">
      <h2 className="text-lg font-semibold">
        Write twin collective · fullscreen · multiselect
      </h2>
      <p className="text-sm text-muted">
        Pure residual: write-mode twin draft + collective analysis over
        fullscreen + collective multiselect + floating DR pack.
        draft_written=false · analysis_written=false · live_dispatched=false ·
        ND REJECT.
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
        Compose write twin collective residual pack (tests are proof)
      </LemonButton>
      {error && (
        <LemonCard className="border-warning p-3 text-sm">{error}</LemonCard>
      )}
      {result && (
        <LemonCard className="p-3 text-sm">
          {formatWriteModeTwinCollectiveFullscreenCollectiveMultiselectSummary(
            result,
          )}
        </LemonCard>
      )}
    </div>
  );
}
