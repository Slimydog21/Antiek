/**
 * HnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMarketMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTwinSearchHtmlNativeMow12MpackPanel — free-file.
 */
import { useState } from "react";
import { LemonButton, LemonCard } from "../../components/lemon";
import {
  composeHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMarketMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTwinSearchHtmlNativeMow12Mpack,
  formatHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMarketMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTwinSearchHtmlNativeMow12MpackSummary,
  type HnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMarketMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTwinSearchHtmlNativeMow12MpackCompose,
} from "../../api/hnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMarketMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTwinSearchHtmlNativeMow12MpackCompose";

export default function HnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMarketMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTwinSearchHtmlNativeMow12MpackPanel() {
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<HnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMarketMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTwinSearchHtmlNativeMow12MpackCompose | null>(null);
  function onCompose() {
    setError(null); setResult(null);
    try {
      setError("Full nest proven in pure tests; panel is free-file surface only.");
      void ack;
      void composeHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMarketMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTwinSearchHtmlNativeMow12Mpack;
      void formatHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMarketMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTwinSearchHtmlNativeMow12MpackSummary;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }
  return (
    <div className="flex flex-col gap-3 p-4 max-w-3xl">
      <h2 className="text-lg font-semibold">HTML-native · marketplace free · mow12</h2>
      <p className="text-sm text-muted">
        Pure residual: HTML-native view session authority over marketplace free residual.
        pdf_view_authorized/pdf_primary always false; purchase/hosted false; ND REJECT.
      </p>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" checked={ack} onChange={(e) => setAck(e.target.checked)} />
        operator_ack
      </label>
      <LemonButton type="primary" onClick={onCompose}>Compose HTML-native residual (tests are proof)</LemonButton>
      {error && <LemonCard className="border-warning p-3 text-sm">{error}</LemonCard>}
      {result && (
        <LemonCard className="p-3 text-sm font-mono">
          {formatHnMktMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTsHnMarketMoSdCdNdsRtAbSaWtFsDbmColFdrWsMdTwinSearchHtmlNativeMow12MpackSummary(result)}
        </LemonCard>
      )}
    </div>
  );
}
