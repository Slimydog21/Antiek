/**
 * HighlightFloatingTwinBridgePanel - one highlight → floating DR + twin.
 *
 * Free-file under Reading/. Pure compose; no live dispatch / twin write.
 */

import { useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../../components/lemon";
import {
  bridgeHighlightToFloatingAndTwin,
  formatBridgeSummary,
  type HighlightFloatingTwinBridgeResult,
} from "../../api/highlightFloatingTwinBridge";

export interface HighlightFloatingTwinBridgePanelProps {
  gated: boolean;
  initialParentAssetId?: string;
  initialHighlight?: string;
  bridgeFn?: typeof bridgeHighlightToFloatingAndTwin;
}

export default function HighlightFloatingTwinBridgePanel({
  gated,
  initialParentAssetId = "",
  initialHighlight = "",
  bridgeFn = bridgeHighlightToFloatingAndTwin,
}: HighlightFloatingTwinBridgePanelProps) {
  const [parent, setParent] = useState(initialParentAssetId);
  const [highlight, setHighlight] = useState(initialHighlight);
  const [prompt, setPrompt] = useState("");
  const [insightsRaw, setInsightsRaw] = useState("");
  const [questionsRaw, setQuestionsRaw] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<HighlightFloatingTwinBridgeResult | null>(null);

  function onBridge() {
    setError(null);
    setResult(null);
    try {
      if (typeof gated !== "boolean") {
        throw new Error(
          "gated must be an explicit boolean from highlight provenance (fail closed)",
        );
      }
      const insights = insightsRaw
        .split(/\r?\n/)
        .map((s) => s.trim())
        .filter(Boolean);
      const questions = questionsRaw
        .split(/\r?\n/)
        .map((s) => s.trim())
        .filter(Boolean);
      setResult(
        bridgeFn({
          parent_asset_id: parent.trim(),
          highlight: highlight.trim(),
          gated,
          prompt: prompt.trim() || undefined,
          insights,
          questions,
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div data-testid="highlight-floating-twin-bridge-panel">
      <LemonCard
        title="Highlight → floating research + twin"
        className="highlight-floating-twin-bridge-panel"
      >
        <p className="text-sm opacity-80" data-testid="hftb-blurb">
          From one highlight, propose a floating deep research instance and a
          recursive twin bind together. Pure compose —
          live_dispatched and twin_created stay false.
        </p>
        <div className="flex flex-col gap-3 mt-3">
          <label className="text-sm flex flex-col gap-1">
            <span>Parent asset id</span>
            <LemonInput
              value={parent}
              onChange={(e) => setParent(e.target.value)}
              data-testid="hftb-parent"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Highlight</span>
            <LemonInput
              value={highlight}
              onChange={(e) => setHighlight(e.target.value)}
              data-testid="hftb-highlight"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Deep research prompt (optional)</span>
            <LemonInput
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              data-testid="hftb-prompt"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Insights (one per line, optional)</span>
            <textarea
              value={insightsRaw}
              onChange={(e) => setInsightsRaw(e.target.value)}
              data-testid="hftb-insights"
              className="border border-border rounded px-2 py-1 text-sm min-h-[3rem]"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Questions (one per line, optional)</span>
            <textarea
              value={questionsRaw}
              onChange={(e) => setQuestionsRaw(e.target.value)}
              data-testid="hftb-questions"
              className="border border-border rounded px-2 py-1 text-sm min-h-[3rem]"
            />
          </label>
          <LemonButton
            variant="primary"
            onClick={onBridge}
            data-testid="hftb-run"
          >
            Bridge highlight
          </LemonButton>
          {error ? (
            <div className="text-sm text-danger" data-testid="hftb-error">
              {error}
            </div>
          ) : null}
          {result ? (
            <div data-testid="hftb-result" className="text-sm flex flex-col gap-1">
              <div data-testid="hftb-summary">{formatBridgeSummary(result)}</div>
              <div data-testid="hftb-live">
                live_dispatched={String(result.live_dispatched)}
              </div>
              <div data-testid="hftb-twin-created">
                twin_created={String(result.twin_created)}
              </div>
            </div>
          ) : null}
        </div>
      </LemonCard>
    </div>
  );
}
