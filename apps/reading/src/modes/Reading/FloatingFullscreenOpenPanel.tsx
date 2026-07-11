/**
 * FloatingFullscreenOpenPanel — highlight/float → open fullscreen.
 *
 * Free-file. live_dispatched/merge/pack always false.
 */

import { useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../../components/lemon";
import {
  composeFloatingFullscreenOpen,
  formatFloatingFullscreenOpenSummary,
  type FloatingFullscreenOpenCompose,
} from "../../api/floatingFullscreenOpenCompose";

export interface FloatingFullscreenOpenPanelProps {
  composeFn?: typeof composeFloatingFullscreenOpen;
}

export default function FloatingFullscreenOpenPanel({
  composeFn = composeFloatingFullscreenOpen,
}: FloatingFullscreenOpenPanelProps) {
  const [highlight, setHighlight] = useState(
    "Key claim from the reading surface",
  );
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<FloatingFullscreenOpenCompose | null>(null);

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      setResult(
        composeFn({
          session_id: "sess-demo",
          parent_asset_id: "asset-demo",
          highlight: highlight.trim() || "highlight",
          prompt: "Deep research this highlight",
          gated: false,
          operator_ack: ack,
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div data-testid="floating-fullscreen-open-panel">
      <LemonCard
        title="Reading · float → open fullscreen"
        className="floating-fullscreen-open-panel"
      >
        <p className="text-sm opacity-80" data-testid="ffo-blurb">
          Spawn a floating deep research from a highlight and open it
          fullscreen. Pure — never dispatches or merges parent.
        </p>
        <div className="flex flex-col gap-2 mt-3">
          <label className="text-sm flex flex-col gap-1">
            <span>Highlight</span>
            <LemonInput
              value={highlight}
              onChange={(e) => setHighlight(e.target.value)}
              data-testid="ffo-highlight"
            />
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={ack}
              onChange={(e) => setAck(e.target.checked)}
              data-testid="ffo-ack"
            />
            <span>operator_ack</span>
          </label>
          <LemonButton
            type="primary"
            onClick={onCompose}
            data-testid="ffo-compose"
          >
            Open fullscreen
          </LemonButton>
        </div>
        {error && (
          <p className="text-sm text-danger mt-2" data-testid="ffo-error">
            {error}
          </p>
        )}
        {result && (
          <div className="mt-3 text-sm" data-testid="ffo-result">
            <p data-testid="ffo-summary">
              {formatFloatingFullscreenOpenSummary(result)}
            </p>
            <ul className="list-disc pl-5 mt-1 opacity-80">
              <li>fullscreen_ready={String(result.fullscreen_ready)}</li>
              <li>view_mode={result.instance.view_mode}</li>
              <li>live_dispatched={String(result.live_dispatched)}</li>
              <li>merge_executed={String(result.merge_executed)}</li>
            </ul>
          </div>
        )}
      </LemonCard>
    </div>
  );
}
