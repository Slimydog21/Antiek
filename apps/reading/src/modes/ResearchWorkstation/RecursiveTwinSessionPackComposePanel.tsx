/**
 * RecursiveTwinSessionPackComposePanel - session twin substrate pack.
 *
 * Free-file. Never mutates twin store; twin_store_mutated always false.
 */

import { useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../../components/lemon";
import {
  composeRecursiveTwinSessionPack,
  formatRecursiveTwinSessionPackSummary,
  type RecursiveTwinSessionPack,
} from "../../api/recursiveTwinSessionPackCompose";

export interface RecursiveTwinSessionPackComposePanelProps {
  composeFn?: typeof composeRecursiveTwinSessionPack;
}

export default function RecursiveTwinSessionPackComposePanel({
  composeFn = composeRecursiveTwinSessionPack,
}: RecursiveTwinSessionPackComposePanelProps) {
  const [sessionId, setSessionId] = useState("sess-1");
  const [assetId, setAssetId] = useState("asset-1");
  const [insightsRaw, setInsightsRaw] = useState("scaling holds under noise");
  const [questionsRaw, setQuestionsRaw] = useState("what about multimodal?");
  const [bound, setBound] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<RecursiveTwinSessionPack | null>(null);

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      const insights = insightsRaw
        .split(/\r?\n/)
        .map((s) => s.trim())
        .filter(Boolean);
      const questions = questionsRaw
        .split(/\r?\n/)
        .map((s) => s.trim())
        .filter(Boolean);
      setResult(
        composeFn({
          session_id: sessionId,
          members: [
            {
              asset_id: assetId,
              twin_bound: bound,
              insights,
              questions,
            },
          ],
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div data-testid="recursive-twin-session-pack-compose-panel">
      <LemonCard
        title="Recursive twin session pack"
        className="recursive-twin-session-pack-compose-panel"
      >
        <p className="text-sm opacity-80" data-testid="rtsp-blurb">
          Pack twin insights and questions for a session so they can be merged,
          referenced, and searched. Pure intent — twin_store_mutated stays
          false.
        </p>
        <div className="flex flex-col gap-3 mt-3">
          <label className="text-sm flex flex-col gap-1">
            <span>Session id</span>
            <LemonInput
              value={sessionId}
              onChange={(e) => setSessionId(e.target.value)}
              data-testid="rtsp-session"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Asset id</span>
            <LemonInput
              value={assetId}
              onChange={(e) => setAssetId(e.target.value)}
              data-testid="rtsp-asset"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Insights (one per line)</span>
            <textarea
              value={insightsRaw}
              onChange={(e) => setInsightsRaw(e.target.value)}
              data-testid="rtsp-insights"
              className="border border-border rounded px-2 py-1 text-sm min-h-[3rem]"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Questions (one per line)</span>
            <textarea
              value={questionsRaw}
              onChange={(e) => setQuestionsRaw(e.target.value)}
              data-testid="rtsp-questions"
              className="border border-border rounded px-2 py-1 text-sm min-h-[3rem]"
            />
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={bound}
              onChange={(e) => setBound(e.target.checked)}
              data-testid="rtsp-bound"
            />
            twin_bound
          </label>
          <LemonButton
            variant="primary"
            onClick={onCompose}
            data-testid="rtsp-compose"
          >
            Compose twin pack
          </LemonButton>
          {error ? (
            <div className="text-sm text-danger" data-testid="rtsp-error">
              {error}
            </div>
          ) : null}
          {result ? (
            <div
              data-testid="rtsp-result"
              className="text-sm flex flex-col gap-1"
            >
              <div data-testid="rtsp-summary">
                {formatRecursiveTwinSessionPackSummary(result)}
              </div>
              <div data-testid="rtsp-ready">
                pack_ready={String(result.pack_ready)}
              </div>
              <div data-testid="rtsp-mutated">
                twin_store_mutated={String(result.twin_store_mutated)}
              </div>
            </div>
          ) : null}
        </div>
      </LemonCard>
    </div>
  );
}
