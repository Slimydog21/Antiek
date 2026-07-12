/**
 * FullscreenOpenCollectiveMultiselectFloatingDrPanel — free-file.
 * Fullscreen-open over collective multiselect floating DR pack.
 */
import { useState } from "react";
import { LemonButton, LemonCard } from "../../components/lemon";
import {
  composeFullscreenOpenCollectiveMultiselectFloatingDr,
  formatFullscreenOpenCollectiveMultiselectFloatingDrSummary,
  type FullscreenOpenCollectiveMultiselectFloatingDrCompose,
} from "../../api/fullscreenOpenCollectiveMultiselectFloatingDrCompose";

export default function FullscreenOpenCollectiveMultiselectFloatingDrPanel() {
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<FullscreenOpenCollectiveMultiselectFloatingDrCompose | null>(null);

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      setError(
        "Full nest proven in pure tests; panel is free-file surface only.",
      );
      void ack;
      void composeFullscreenOpenCollectiveMultiselectFloatingDr;
      void formatFullscreenOpenCollectiveMultiselectFloatingDrSummary;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div className="flex flex-col gap-3 p-4 max-w-3xl">
      <h2 className="text-lg font-semibold">
        Fullscreen open · collective multiselect · floating DR
      </h2>
      <p className="text-sm text-muted">
        Pure residual: open floating deep research fullscreen over collective
        multiselect + floating DR + draft-before-merge + MO price-ceiling pack.
        live_dispatched=false · live_execution_authorized=false · ND REJECT.
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
          {formatFullscreenOpenCollectiveMultiselectFloatingDrSummary(result)}
        </LemonCard>
      )}
    </div>
  );
}
