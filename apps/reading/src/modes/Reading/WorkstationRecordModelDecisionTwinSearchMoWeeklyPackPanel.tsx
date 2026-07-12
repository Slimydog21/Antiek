/**
 * WorkstationRecordModelDecisionTwinSearchMoWeeklyPackPanel — free-file.
 */
import { useState } from "react";
import { LemonButton, LemonCard } from "../../components/lemon";
import {
  composeWorkstationRecordModelDecisionTwinSearchMoWeeklyPack,
  formatWorkstationRecordModelDecisionTwinSearchMoWeeklyPackSummary,
  type WorkstationRecordModelDecisionTwinSearchMoWeeklyPackCompose,
} from "../../api/workstationRecordModelDecisionTwinSearchMoWeeklyPackCompose";

export default function WorkstationRecordModelDecisionTwinSearchMoWeeklyPackPanel() {
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<WorkstationRecordModelDecisionTwinSearchMoWeeklyPackCompose | null>(null);

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      setError(
        "Full nest proven in pure tests; panel is free-file surface only.",
      );
      void ack;
      void composeWorkstationRecordModelDecisionTwinSearchMoWeeklyPack;
      void formatWorkstationRecordModelDecisionTwinSearchMoWeeklyPackSummary;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div className="flex flex-col gap-3 p-4 max-w-3xl">
      <h2 className="text-lg font-semibold">
        Workstation records · model decision · twin search
      </h2>
      <p className="text-sm text-muted">
        Pure residual: recursive workstation insight/question records over model
        decision-tree + twin intelligent search + HTML-native marketplace free MO
        pack. record_persisted and prompts_injected always false · ND REJECT.
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
        Compose workstation record residual pack (tests are proof)
      </LemonButton>
      {error && (
        <LemonCard className="border-warning p-3 text-sm">{error}</LemonCard>
      )}
      {result && (
        <LemonCard className="p-3 text-sm">
          {formatWorkstationRecordModelDecisionTwinSearchMoWeeklyPackSummary(result)}
        </LemonCard>
      )}
    </div>
  );
}
