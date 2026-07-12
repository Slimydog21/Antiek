/**
 * MoUnattendedDraftBeforeMergeFloatingMultiselectNdTwinPanel — free-file.
 * Midnight Oil unattended over draft-before-merge floating multiselect ND twin.
 */
import { useState } from "react";
import { LemonButton, LemonCard } from "../../components/lemon";
import {
  composeMoUnattendedDraftBeforeMergeFloatingMultiselectNdTwin,
  formatMoUnattendedDraftBeforeMergeFloatingMultiselectNdTwinSummary,
  type MoUnattendedDraftBeforeMergeFloatingMultiselectNdTwinCompose,
} from "../../api/moUnattendedDraftBeforeMergeFloatingMultiselectNdTwinCompose";

export default function MoUnattendedDraftBeforeMergeFloatingMultiselectNdTwinPanel() {
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<MoUnattendedDraftBeforeMergeFloatingMultiselectNdTwinCompose | null>(
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
      void composeMoUnattendedDraftBeforeMergeFloatingMultiselectNdTwin;
      void formatMoUnattendedDraftBeforeMergeFloatingMultiselectNdTwinSummary;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div className="flex flex-col gap-3 p-4 max-w-3xl">
      <h2 className="text-lg font-semibold">
        Midnight Oil unattended · draft-before-merge · multiselect ND twin
      </h2>
      <p className="text-sm text-muted">
        Pure residual: set time + goals + price ceiling for unattended deep
        research while draft-before-merge + floating multi-select + model
        decision ND twin pack remain pure. live_execution_authorized always
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
        Compose midnight oil residual pack (tests are proof)
      </LemonButton>
      {error && (
        <LemonCard className="border-warning p-3 text-sm">{error}</LemonCard>
      )}
      {result && (
        <LemonCard className="p-3 text-sm">
          {formatMoUnattendedDraftBeforeMergeFloatingMultiselectNdTwinSummary(
            result,
          )}
        </LemonCard>
      )}
    </div>
  );
}
