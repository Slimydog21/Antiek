/**
 * SourceAttachWriteTwinFsDraftPackPanel — free-file.
 * HTML-native arxiv/substack attach over write twin fullscreen draft MO weekly pack.
 */
import { useState } from "react";
import { LemonButton, LemonCard } from "../../components/lemon";
import {
  composeSourceAttachWriteTwinFsDraftPack,
  formatSourceAttachWriteTwinFsDraftPackSummary,
  type SourceAttachWriteTwinFsDraftPackCompose,
} from "../../api/sourceAttachWriteTwinFsDraftPackCompose";

export default function SourceAttachWriteTwinFsDraftPackPanel() {
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<SourceAttachWriteTwinFsDraftPackCompose | null>(null);

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      setError(
        "Full nest proven in pure tests; panel is free-file surface only.",
      );
      void ack;
      void composeSourceAttachWriteTwinFsDraftPack;
      void formatSourceAttachWriteTwinFsDraftPackSummary;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div className="flex flex-col gap-3 p-4 max-w-3xl">
      <h2 className="text-lg font-semibold">
        Source attach · write twin collective · fullscreen
      </h2>
      <p className="text-sm text-muted">
        Pure residual: HTML-native arxiv/substack source attach over write twin
        collective + fullscreen pack. remote_fetched=false · pdf_primary=false ·
        draft_written=false · ND REJECT.
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
        Compose source-attach residual pack (tests are proof)
      </LemonButton>
      {error && (
        <LemonCard className="border-warning p-3 text-sm">{error}</LemonCard>
      )}
      {result && (
        <LemonCard className="p-3 text-sm">
          {formatSourceAttachWriteTwinFsDraftPackSummary(result)}
        </LemonCard>
      )}
    </div>
  );
}
