/**
 * FloatingDrWorkstationRecordModelDecisionPanel — free-file.
 */
import { useState } from "react";
import { LemonButton, LemonCard } from "../../components/lemon";
import {
  composeFloatingDrWorkstationRecordModelDecision,
  formatFloatingDrWorkstationRecordModelDecisionSummary,
  type FloatingDrWorkstationRecordModelDecisionCompose,
} from "../../api/floatingDrWorkstationRecordModelDecisionCompose";

export default function FloatingDrWorkstationRecordModelDecisionPanel() {
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<FloatingDrWorkstationRecordModelDecisionCompose | null>(null);

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      setError(
        "Full nest proven in pure tests; panel is free-file surface only.",
      );
      void ack;
      void composeFloatingDrWorkstationRecordModelDecision;
      void formatFloatingDrWorkstationRecordModelDecisionSummary;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div className="flex flex-col gap-3 p-4 max-w-3xl">
      <h2 className="text-lg font-semibold">
        Floating DR · workstation records · model decision
      </h2>
      <p className="text-sm text-muted">
        Pure residual: highlight → floating/fullscreen deep research launch over
        workstation recursive records + model decision + twin search pack.
        live_dispatched and merge_executed always false · ND REJECT.
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
        Compose floating DR residual pack (tests are proof)
      </LemonButton>
      {error && (
        <LemonCard className="border-warning p-3 text-sm">{error}</LemonCard>
      )}
      {result && (
        <LemonCard className="p-3 text-sm">
          {formatFloatingDrWorkstationRecordModelDecisionSummary(result)}
        </LemonCard>
      )}
    </div>
  );
}
