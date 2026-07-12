/**
 * CollectiveMultiselectFloatingDrWorkstationRecordPanel — free-file.
 */
import { useState } from "react";
import { LemonButton, LemonCard } from "../../components/lemon";
import {
  composeCollectiveMultiselectFloatingDrWorkstationRecord,
  formatCollectiveMultiselectFloatingDrWorkstationRecordSummary,
  type CollectiveMultiselectFloatingDrWorkstationRecordCompose,
} from "../../api/collectiveMultiselectFloatingDrWorkstationRecordCompose";

export default function CollectiveMultiselectFloatingDrWorkstationRecordPanel() {
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<CollectiveMultiselectFloatingDrWorkstationRecordCompose | null>(
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
      void composeCollectiveMultiselectFloatingDrWorkstationRecord;
      void formatCollectiveMultiselectFloatingDrWorkstationRecordSummary;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div className="flex flex-col gap-3 p-4 max-w-3xl">
      <h2 className="text-lg font-semibold">
        Collective multiselect · floating DR · workstation records
      </h2>
      <p className="text-sm text-muted">
        Pure residual: multi-select floating DR instances as one cohesive unit
        over highlight launch + workstation records + model decision pack.
        live_dispatched and pack_dispatched always false · ND REJECT.
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
        Compose collective multiselect residual pack (tests are proof)
      </LemonButton>
      {error && (
        <LemonCard className="border-warning p-3 text-sm">{error}</LemonCard>
      )}
      {result && (
        <LemonCard className="p-3 text-sm">
          {formatCollectiveMultiselectFloatingDrWorkstationRecordSummary(
            result,
          )}
        </LemonCard>
      )}
    </div>
  );
}
