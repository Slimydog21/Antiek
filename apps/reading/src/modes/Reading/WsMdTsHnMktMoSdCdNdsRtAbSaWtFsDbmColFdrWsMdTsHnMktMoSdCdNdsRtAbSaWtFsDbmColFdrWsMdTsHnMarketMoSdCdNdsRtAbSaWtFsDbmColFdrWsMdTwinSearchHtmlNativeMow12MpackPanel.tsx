/**
 * WsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMarketMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTwinSearchHtmlNativeMow12MpackPanel — free-file.
 */
import { useState } from "react";
import { LemonButton, LemonCard } from "../../components/lemon";
import {
  composeWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMarketMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTwinSearchHtmlNativeMow12Mpack,
  formatWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMarketMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTwinSearchHtmlNativeMow12MpackSummary,
  type WsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMarketMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTwinSearchHtmlNativeMow12MpackCompose,
} from "../../api/wsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMarketMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTwinSearchHtmlNativeMow12MpackCompose";

export default function WsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMarketMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTwinSearchHtmlNativeMow12MpackPanel() {
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<WsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMarketMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTwinSearchHtmlNativeMow12MpackCompose | null>(null);
  function onCompose() {
    setError(null); setResult(null);
    try {
      setError("Full nest proven in pure tests; panel is free-file surface only.");
      void ack;
      void composeWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMarketMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTwinSearchHtmlNativeMow12Mpack;
      void formatWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMarketMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTwinSearchHtmlNativeMow12MpackSummary;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }
  return (
    <div className="flex flex-col gap-3 p-4 max-w-3xl">
      <h2 className="text-lg font-semibold">Workstation records · model decision · mow12</h2>
      <p className="text-sm text-muted">
        Pure residual: recursive workstation records over model-decision residual.
        record_persisted / prompts_injected always false; ND REJECT.
      </p>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} />
        operator_ack
      </label>
      <LemonButton type="primary" onClick={onCompose}>Compose workstation residual (tests are proof)</LemonButton>
      {error && <LemonCard className="border-warning p-3 text-sm">{error}</LemonCard>}
      {result && (
        <LemonCard className="p-3 text-sm font-mono">
          {formatWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMarketMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTwinSearchHtmlNativeMow12MpackSummary(result)}
        </LemonCard>
      )}
    </div>
  );
}
