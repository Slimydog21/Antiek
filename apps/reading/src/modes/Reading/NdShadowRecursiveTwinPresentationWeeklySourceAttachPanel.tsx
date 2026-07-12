/**
 * NdShadowRecursiveTwinPresentationWeeklySourceAttachPanel — free-file.
 */
import { useState } from "react";
import { LemonButton, LemonCard } from "../../components/lemon";
import {
  composeNdShadowRecursiveTwinPresentationWeeklySourceAttach,
  formatNdShadowRecursiveTwinPresentationWeeklySourceAttachSummary,
  type NdShadowRecursiveTwinPresentationWeeklySourceAttachCompose,
} from "../../api/ndShadowRecursiveTwinPresentationWeeklySourceAttachCompose";

export default function NdShadowRecursiveTwinPresentationWeeklySourceAttachPanel() {
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<NdShadowRecursiveTwinPresentationWeeklySourceAttachCompose | null>(
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
      void composeNdShadowRecursiveTwinPresentationWeeklySourceAttach;
      void formatNdShadowRecursiveTwinPresentationWeeklySourceAttachSummary;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div className="flex flex-col gap-3 p-4 max-w-3xl">
      <h2 className="text-lg font-semibold">
        ND shadow REJECT · twin presentation · weekly source attach
      </h2>
      <p className="text-sm text-muted">
        Pure residual: NotDiamond shadow advisory re-affirms production REJECT
        over recursive twin presentation + Antiek-bench weekly source-attach
        write twin pack. live_router_authorized always false.
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
        Compose ND shadow residual pack (tests are proof)
      </LemonButton>
      {error && (
        <LemonCard className="border-warning p-3 text-sm">{error}</LemonCard>
      )}
      {result && (
        <LemonCard className="p-3 text-sm">
          {formatNdShadowRecursiveTwinPresentationWeeklySourceAttachSummary(
            result,
          )}
        </LemonCard>
      )}
    </div>
  );
}
