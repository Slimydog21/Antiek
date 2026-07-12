/**
 * FullscreenMoUnattendedDraftMultiselectNdTwinPanel — free-file.
 * Fullscreen open over MO unattended draft multiselect ND twin.
 */
import { useState } from "react";
import { LemonButton, LemonCard } from "../../components/lemon";
import {
  composeFullscreenMoUnattendedDraftMultiselectNdTwin,
  formatFullscreenMoUnattendedDraftMultiselectNdTwinSummary,
  type FullscreenMoUnattendedDraftMultiselectNdTwinCompose,
} from "../../api/fullscreenMoUnattendedDraftMultiselectNdTwinCompose";

export default function FullscreenMoUnattendedDraftMultiselectNdTwinPanel() {
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<FullscreenMoUnattendedDraftMultiselectNdTwinCompose | null>(null);

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      setError(
        "Full nest proven in pure tests; panel is free-file surface only.",
      );
      void ack;
      void composeFullscreenMoUnattendedDraftMultiselectNdTwin;
      void formatFullscreenMoUnattendedDraftMultiselectNdTwinSummary;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div className="flex flex-col gap-3 p-4 max-w-3xl">
      <h2 className="text-lg font-semibold">
        Fullscreen open · MO unattended · draft multiselect ND twin
      </h2>
      <p className="text-sm text-muted">
        Pure residual: open floating deep research fullscreen while Midnight
        Oil unattended + draft-before-merge + multi-select + model decision ND
        twin remain pure. live_dispatched and live_execution_authorized always
        false · ND REJECT.
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
          {formatFullscreenMoUnattendedDraftMultiselectNdTwinSummary(result)}
        </LemonCard>
      )}
    </div>
  );
}
