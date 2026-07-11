/**
 * TwinChaseAnalysisFeedPanel — feed chase findings into twin note-taker.
 *
 * Free-file. twin_written, record_persisted, prompts_injected,
 * live_dispatch_authorized always false.
 */

import { useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../../components/lemon";
import {
  composeTwinChaseAnalysisFeed,
  formatTwinChaseAnalysisFeedSummary,
  type TwinChaseAnalysisFeedCompose,
} from "../../api/twinChaseAnalysisFeedCompose";

export interface TwinChaseAnalysisFeedPanelProps {
  composeFn?: typeof composeTwinChaseAnalysisFeed;
}

export default function TwinChaseAnalysisFeedPanel({
  composeFn = composeTwinChaseAnalysisFeed,
}: TwinChaseAnalysisFeedPanelProps) {
  const [sessionId, setSessionId] = useState("sess-1");
  const [parent, setParent] = useState("paper-1");
  const [insight, setInsight] = useState("scaling holds under noise");
  const [question, setQuestion] = useState("What is the failure mode?");
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<TwinChaseAnalysisFeedCompose | null>(null);

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      setResult(
        composeFn({
          session_id: sessionId.trim(),
          parent_asset_id: parent.trim(),
          findings: [
            {
              source_id: "chase_1",
              body: insight.trim(),
              kind: "insight",
            },
            {
              source_id: "chase_2",
              body: question.trim(),
              kind: "question",
            },
          ],
          analysis_excerpt: "operator draft collective analysis",
          mark_for_prompt_context: true,
          operator_ack: ack,
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div data-testid="twin-chase-analysis-feed-panel">
      <LemonCard
        title="Research · chase/analysis → twin feed"
        className="twin-chase-analysis-feed-panel"
      >
        <p className="text-sm opacity-80" data-testid="tcaf-blurb">
          Feed completed chase findings into the recursive twin note-taker
          scaffold. Pure — twin_written stays false.
        </p>
        <div className="flex flex-col gap-2 mt-3">
          <label className="text-sm flex flex-col gap-1">
            <span>Session</span>
            <LemonInput
              value={sessionId}
              onChange={(e) => setSessionId(e.target.value)}
              data-testid="tcaf-session"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Parent asset</span>
            <LemonInput
              value={parent}
              onChange={(e) => setParent(e.target.value)}
              data-testid="tcaf-parent"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Insight (chase 1)</span>
            <LemonInput
              value={insight}
              onChange={(e) => setInsight(e.target.value)}
              data-testid="tcaf-insight"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Question (chase 2)</span>
            <LemonInput
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              data-testid="tcaf-question"
            />
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={ack}
              onChange={(e) => setAck(e.target.checked)}
              data-testid="tcaf-ack"
            />
            <span>operator_ack</span>
          </label>
          <LemonButton
            variant="primary"
            onClick={onCompose}
            data-testid="tcaf-compose"
          >
            Compose twin chase feed
          </LemonButton>
          {error ? (
            <p className="text-sm text-danger" data-testid="tcaf-error">
              {error}
            </p>
          ) : null}
          {result ? (
            <div
              className="text-sm flex flex-col gap-1 mt-2"
              data-testid="tcaf-result"
            >
              <div data-testid="tcaf-ready">
                feed_ready={String(result.feed_ready)}
              </div>
              <div data-testid="tcaf-twin">
                twin_written={String(result.twin_written)}
              </div>
              <div data-testid="tcaf-record">
                record_persisted={String(result.record_persisted)}
              </div>
              <div data-testid="tcaf-prompts">
                prompts_injected={String(result.prompts_injected)}
              </div>
              <div data-testid="tcaf-live">
                live_dispatch_authorized=
                {String(result.live_dispatch_authorized)}
              </div>
              <div data-testid="tcaf-summary">
                {formatTwinChaseAnalysisFeedSummary(result)}
              </div>
            </div>
          ) : null}
        </div>
      </LemonCard>
    </div>
  );
}
