/**
 * ChaseTwinAnalysisLoopPanel — chase → twin → analysis pure loop UI.
 *
 * Free-file. live_dispatched, twin_written, analysis_written always false.
 */

import { useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../../components/lemon";
import {
  composeChaseTwinAnalysisLoop,
  formatChaseTwinAnalysisLoopSummary,
  type ChaseTwinAnalysisLoopCompose,
} from "../../api/chaseTwinAnalysisLoopCompose";

export interface ChaseTwinAnalysisLoopPanelProps {
  composeFn?: typeof composeChaseTwinAnalysisLoop;
}

export default function ChaseTwinAnalysisLoopPanel({
  composeFn = composeChaseTwinAnalysisLoop,
}: ChaseTwinAnalysisLoopPanelProps) {
  const [sessionId, setSessionId] = useState("sess-1");
  const [parent, setParent] = useState("paper-1");
  const [q1, setQ1] = useState("What is the core claim?");
  const [q2, setQ2] = useState("What evidence is missing?");
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<ChaseTwinAnalysisLoopCompose | null>(null);

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      const p = parent.trim() || "paper-1";
      setResult(
        composeFn({
          session_id: sessionId.trim(),
          parent_asset_id: p,
          questions: [
            { question_id: "q1", body: q1.trim(), priority: 2 },
            { question_id: "q2", body: q2.trim(), priority: 1 },
          ],
          chase_mode: "swarm_fanout",
          would_exceed: false,
          source_families: ["arxiv", "substack"],
          operator_ack: ack,
          analysis_kind: "draft_analysis",
          analysis_excerpt: "operator draft collective analysis",
          completed_slots: [
            {
              slot_id: "chase_1_q1",
              question_id: "q1",
              parent_asset_id: p,
              status: "completed",
              findings: ["claim scaffold from chase 1"],
              body: q1.trim(),
            },
            {
              slot_id: "chase_2_q2",
              question_id: "q2",
              parent_asset_id: p,
              status: "completed",
              findings: ["gap scaffold from chase 2"],
              body: q2.trim(),
            },
          ],
          mark_for_prompt_context: true,
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div data-testid="chase-twin-analysis-loop-panel">
      <LemonCard
        title="Research · chase → twin → analysis loop"
        className="chase-twin-analysis-loop-panel"
      >
        <p className="text-sm opacity-80" data-testid="ctal-blurb">
          Interrogation chase plan, twin note feed, and collective analysis
          intent in one pure loop. Never dispatches or writes assets.
        </p>
        <div className="flex flex-col gap-2 mt-3">
          <label className="text-sm flex flex-col gap-1">
            <span>Session</span>
            <LemonInput
              value={sessionId}
              onChange={(e) => setSessionId(e.target.value)}
              data-testid="ctal-session"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Parent asset</span>
            <LemonInput
              value={parent}
              onChange={(e) => setParent(e.target.value)}
              data-testid="ctal-parent"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Question 1</span>
            <LemonInput
              value={q1}
              onChange={(e) => setQ1(e.target.value)}
              data-testid="ctal-q1"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Question 2</span>
            <LemonInput
              value={q2}
              onChange={(e) => setQ2(e.target.value)}
              data-testid="ctal-q2"
            />
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={ack}
              onChange={(e) => setAck(e.target.checked)}
              data-testid="ctal-ack"
            />
            <span>operator_ack</span>
          </label>
          <LemonButton
            variant="primary"
            onClick={onCompose}
            data-testid="ctal-compose"
          >
            Compose chase→twin→analysis loop
          </LemonButton>
          {error ? (
            <p className="text-sm text-danger" data-testid="ctal-error">
              {error}
            </p>
          ) : null}
          {result ? (
            <div
              className="text-sm flex flex-col gap-1 mt-2"
              data-testid="ctal-result"
            >
              <div data-testid="ctal-ready">
                loop_ready={String(result.loop_ready)}
              </div>
              <div data-testid="ctal-live">
                live_dispatched={String(result.live_dispatched)}
              </div>
              <div data-testid="ctal-twin">
                twin_written={String(result.twin_written)}
              </div>
              <div data-testid="ctal-analysis">
                analysis_written={String(result.analysis_written)}
              </div>
              <div data-testid="ctal-summary">
                {formatChaseTwinAnalysisLoopSummary(result)}
              </div>
            </div>
          ) : null}
        </div>
      </LemonCard>
    </div>
  );
}
