/**
 * CollectiveMultiselectFloatingDrWorkstationMoWeeklySrcWriteMoWeeklySrcWritePackPanel — free-file.
 */
import { useState } from "react";
import { LemonButton, LemonCard } from "../../components/lemon";
import {
  composeCollectiveMultiselectFloatingDrWorkstationMoWeeklySrcWriteMoWeeklySrcWritePack,
  formatCollectiveMultiselectFloatingDrWorkstationMoWeeklySrcWriteMoWeeklySrcWritePackSummary,
  type CollectiveMultiselectFloatingDrWorkstationMoWeeklySrcWriteMoWeeklySrcWritePackCompose,
} from "../../api/collectiveMultiselectFloatingDrWorkstationMoWeeklySrcWriteMoWeeklySrcWritePackCompose";

export default function CollectiveMultiselectFloatingDrWorkstationMoWeeklySrcWriteMoWeeklySrcWritePackPanel() {
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<CollectiveMultiselectFloatingDrWorkstationMoWeeklySrcWriteMoWeeklySrcWritePackCompose | null>(null);
  function onCompose() {
    setError(null);
    setResult(null);
    try {
      setError("Full nest proven in pure tests; panel is free-file surface only.");
      void ack;
      void composeCollectiveMultiselectFloatingDrWorkstationMoWeeklySrcWriteMoWeeklySrcWritePack;
      void formatCollectiveMultiselectFloatingDrWorkstationMoWeeklySrcWriteMoWeeklySrcWritePackSummary;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }
  return (
    <div className="flex flex-col gap-3 p-4 max-w-3xl">
      <h2 className="text-lg font-semibold">Collective multiselect · floating DR · workstation pack</h2>
      <p className="text-sm text-muted">
        Pure residual: multiselect floating sub-agents as cohesive unit over floating DR pack.
        live_dispatched/pack_dispatched false · ND REJECT.
      </p>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} />
        operator_ack
      </label>
      <LemonButton type="primary" onClick={onCompose}>Compose collective residual (tests are proof)</LemonButton>
      {error && <LemonCard className="border-warning p-3 text-sm">{error}</LemonCard>}
      {result && (
        <LemonCard className="p-3 text-sm">
          {formatCollectiveMultiselectFloatingDrWorkstationMoWeeklySrcWriteMoWeeklySrcWritePackSummary(result)}
        </LemonCard>
      )}
    </div>
  );
}
