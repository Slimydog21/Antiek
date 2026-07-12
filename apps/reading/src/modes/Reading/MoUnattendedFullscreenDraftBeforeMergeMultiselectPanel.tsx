/**
 * MoUnattendedFullscreenDraftBeforeMergeMultiselectPanel — free-file.
 * Midnight Oil unattended over fullscreen draft multi-select residual.
 */
import { useState } from "react";
import { LemonButton, LemonCard } from "../../components/lemon";
import {
  composeMoUnattendedFullscreenDraftBeforeMergeMultiselect,
  formatMoUnattendedFullscreenDraftBeforeMergeMultiselectSummary,
  type MoUnattendedFullscreenDraftBeforeMergeMultiselectCompose,
} from "../../api/moUnattendedFullscreenDraftBeforeMergeMultiselectCompose";

export default function MoUnattendedFullscreenDraftBeforeMergeMultiselectPanel() {
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<MoUnattendedFullscreenDraftBeforeMergeMultiselectCompose | null>(
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
      void composeMoUnattendedFullscreenDraftBeforeMergeMultiselect;
      void formatMoUnattendedFullscreenDraftBeforeMergeMultiselectSummary;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div className="flex flex-col gap-3 p-4 max-w-3xl">
      <h2 className="text-lg font-semibold">
        Midnight Oil unattended · fullscreen · draft multi-select
      </h2>
      <p className="text-sm text-muted">
        Pure residual: time + goals + price ceiling for unattended deep research
        over fullscreen draft-before-merge multi-select model decision pack.
        live_execution_authorized=false · ND REJECT.
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
        Compose MO unattended residual pack (tests are proof)
      </LemonButton>
      {error && (
        <LemonCard className="border-warning p-3 text-sm">{error}</LemonCard>
      )}
      {result && (
        <LemonCard className="p-3 text-sm">
          {formatMoUnattendedFullscreenDraftBeforeMergeMultiselectSummary(
            result,
          )}
        </LemonCard>
      )}
    </div>
  );
}
