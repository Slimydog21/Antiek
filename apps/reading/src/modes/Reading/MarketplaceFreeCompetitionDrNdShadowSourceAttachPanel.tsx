/**
 * MarketplaceFreeCompetitionDrNdShadowSourceAttachPanel — free-file.
 * Marketplace free-before-buy over competition DR ND shadow source-attach pack.
 */
import { useState } from "react";
import { LemonButton, LemonCard } from "../../components/lemon";
import {
  composeMarketplaceFreeCompetitionDrNdShadowSourceAttach,
  formatMarketplaceFreeCompetitionDrNdShadowSourceAttachSummary,
  type MarketplaceFreeCompetitionDrNdShadowSourceAttachCompose,
} from "../../api/marketplaceFreeCompetitionDrNdShadowSourceAttachCompose";

export default function MarketplaceFreeCompetitionDrNdShadowSourceAttachPanel() {
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<MarketplaceFreeCompetitionDrNdShadowSourceAttachCompose | null>(
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
      void composeMarketplaceFreeCompetitionDrNdShadowSourceAttach;
      void formatMarketplaceFreeCompetitionDrNdShadowSourceAttachSummary;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div className="flex flex-col gap-3 p-4 max-w-3xl">
      <h2 className="text-lg font-semibold">
        Marketplace free-before-buy · competition DR · ND shadow
      </h2>
      <p className="text-sm text-muted">
        Pure residual: free-first digital book HTML port over competition DR
        quality + NotDiamond shadow REJECT + arxiv/substack attach + weekly
        learn + twin presentation pack. purchase_executed and hosted always
        false · ND REJECT.
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
        Compose marketplace free residual pack (tests are proof)
      </LemonButton>
      {error && (
        <LemonCard className="border-warning p-3 text-sm">{error}</LemonCard>
      )}
      {result && (
        <LemonCard className="p-3 text-sm">
          {formatMarketplaceFreeCompetitionDrNdShadowSourceAttachSummary(
            result,
          )}
        </LemonCard>
      )}
    </div>
  );
}
