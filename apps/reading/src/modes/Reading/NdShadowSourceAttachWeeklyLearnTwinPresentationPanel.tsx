/**
 * NdShadowSourceAttachWeeklyLearnTwinPresentationPanel — free-file.
 * NotDiamond shadow REJECT over source-attach weekly learn twin presentation.
 */
import { useState } from "react";
import { LemonButton, LemonCard } from "../../components/lemon";
import {
  composeNdShadowSourceAttachWeeklyLearnTwinPresentation,
  formatNdShadowSourceAttachWeeklyLearnTwinPresentationSummary,
  type NdShadowSourceAttachWeeklyLearnTwinPresentationCompose,
} from "../../api/ndShadowSourceAttachWeeklyLearnTwinPresentationCompose";

export default function NdShadowSourceAttachWeeklyLearnTwinPresentationPanel() {
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<NdShadowSourceAttachWeeklyLearnTwinPresentationCompose | null>(
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
      void composeNdShadowSourceAttachWeeklyLearnTwinPresentation;
      void formatNdShadowSourceAttachWeeklyLearnTwinPresentationSummary;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div className="flex flex-col gap-3 p-4 max-w-3xl">
      <h2 className="text-lg font-semibold">
        NotDiamond shadow REJECT · source-attach · weekly learn
      </h2>
      <p className="text-sm text-muted">
        Pure residual: re-affirm NotDiamond production_router_verdict=REJECT as
        shadow/advisory only over arxiv/substack attach + Antiek-bench weekly
        learn + recursive twin presentation write collective pack.
        live_router_authorized always false · never auto-routes.
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
          {formatNdShadowSourceAttachWeeklyLearnTwinPresentationSummary(result)}
        </LemonCard>
      )}
    </div>
  );
}
