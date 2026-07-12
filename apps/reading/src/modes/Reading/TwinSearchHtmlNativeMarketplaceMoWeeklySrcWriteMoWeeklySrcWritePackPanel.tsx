/**
 * TwinSearchHtmlNativeMarketplaceMoWeeklySrcWriteMoWeeklySrcWritePackPanel — free-file.
 */
import { useState } from "react";
import { LemonButton, LemonCard } from "../../components/lemon";
import {
  composeTwinSearchHtmlNativeMarketplaceMoWeeklySrcWriteMoWeeklySrcWritePack,
  formatTwinSearchHtmlNativeMarketplaceMoWeeklySrcWriteMoWeeklySrcWritePackSummary,
  type TwinSearchHtmlNativeMarketplaceMoWeeklySrcWriteMoWeeklySrcWritePackCompose,
} from "../../api/twinSearchHtmlNativeMarketplaceMoWeeklySrcWriteMoWeeklySrcWritePackCompose";

export default function TwinSearchHtmlNativeMarketplaceMoWeeklySrcWriteMoWeeklySrcWritePackPanel() {
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<TwinSearchHtmlNativeMarketplaceMoWeeklySrcWriteMoWeeklySrcWritePackCompose | null>(null);
  function onCompose() {
    setError(null);
    setResult(null);
    try {
      setError("Full nest proven in pure tests; panel is free-file surface only.");
      void ack;
      void composeTwinSearchHtmlNativeMarketplaceMoWeeklySrcWriteMoWeeklySrcWritePack;
      void formatTwinSearchHtmlNativeMarketplaceMoWeeklySrcWriteMoWeeklySrcWritePackSummary;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }
  return (
    <div className="flex flex-col gap-3 p-4 max-w-3xl">
      <h2 className="text-lg font-semibold">Twin search · HTML-native · marketplace free weekly pack</h2>
      <p className="text-sm text-muted">
        Pure residual: intelligent twin substrate search over HTML-native marketplace pack.
        remote_index_queried/twin_written false · ND REJECT.
      </p>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} />
        operator_ack
      </label>
      <LemonButton type="primary" onClick={onCompose}>Compose twin search residual (tests are proof)</LemonButton>
      {error && <LemonCard className="border-warning p-3 text-sm">{error}</LemonCard>}
      {result && (
        <LemonCard className="p-3 text-sm">
          {formatTwinSearchHtmlNativeMarketplaceMoWeeklySrcWriteMoWeeklySrcWritePackSummary(result)}
        </LemonCard>
      )}
    </div>
  );
}
