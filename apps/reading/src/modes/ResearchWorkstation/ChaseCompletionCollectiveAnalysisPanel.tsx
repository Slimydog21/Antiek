/**
 * ChaseCompletionCollectiveAnalysisPanel — pure post-chase analysis intent.
 *
 * Free-file. analysis_written, live_dispatched, pack_dispatched always false.
 */

import { useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../../components/lemon";
import {
  composeChaseCompletionCollectiveAnalysis,
  formatChaseCompletionCollectiveAnalysisSummary,
  type ChaseCompletionCollectiveAnalysisCompose,
} from "../../api/chaseCompletionCollectiveAnalysisCompose";
import type { AnalysisMergeKind } from "../../api/collectiveDeepResearchMerge";

export interface ChaseCompletionCollectiveAnalysisPanelProps {
  composeFn?: typeof composeChaseCompletionCollectiveAnalysis;
}

export default function ChaseCompletionCollectiveAnalysisPanel({
  composeFn = composeChaseCompletionCollectiveAnalysis,
}: ChaseCompletionCollectiveAnalysisPanelProps) {
  const [sessionId, setSessionId] = useState("sess-1");
  const [parent, setParent] = useState("paper-1");
  const [kind, setKind] = useState<AnalysisMergeKind>("draft_analysis");
  const [ack, setAck] = useState(true);
  const [f1, setF1] = useState("claim A supported");
  const [f2, setF2] = useState("gap: missing ablation");
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<ChaseCompletionCollectiveAnalysisCompose | null>(null);

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      setResult(
        composeFn({
          session_id: sessionId.trim(),
          parent_asset_id: parent.trim(),
          kind,
          operator_ack: ack,
          slots: [
            {
              slot_id: "chase_1_q1",
              question_id: "q1",
              parent_asset_id: parent.trim() || "paper-1",
              status: "completed",
              findings: f1.trim() ? [f1.trim()] : null,
            },
            {
              slot_id: "chase_2_q2",
              question_id: "q2",
              parent_asset_id: parent.trim() || "paper-1",
              status: "completed",
              findings: f2.trim() ? [f2.trim()] : null,
            },
          ],
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div data-testid="chase-completion-collective-analysis-panel">
      <LemonCard
        title="Research · chase completion → collective analysis"
        className="chase-completion-collective-analysis-panel"
      >
        <p className="text-sm opacity-80" data-testid="ccca-blurb">
          After subagent chases complete, compose a written analysis draft or
          full intent. Pure — analysis_written stays false.
        </p>
        <div className="flex flex-col gap-2 mt-3">
          <label className="text-sm flex flex-col gap-1">
            <span>Session</span>
            <LemonInput
              value={sessionId}
              onChange={(e) => setSessionId(e.target.value)}
              data-testid="ccca-session"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Parent asset</span>
            <LemonInput
              value={parent}
              onChange={(e) => setParent(e.target.value)}
              data-testid="ccca-parent"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Finding (slot 1)</span>
            <LemonInput
              value={f1}
              onChange={(e) => setF1(e.target.value)}
              data-testid="ccca-f1"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Finding (slot 2)</span>
            <LemonInput
              value={f2}
              onChange={(e) => setF2(e.target.value)}
              data-testid="ccca-f2"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Analysis kind</span>
            <select
              value={kind}
              onChange={(e) => setKind(e.target.value as AnalysisMergeKind)}
              data-testid="ccca-kind"
              className="border border-border rounded px-2 py-1 text-sm"
            >
              <option value="draft_analysis">draft_analysis</option>
              <option value="full_analysis">full_analysis</option>
            </select>
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={ack}
              onChange={(e) => setAck(e.target.checked)}
              data-testid="ccca-ack"
            />
            <span>operator_ack</span>
          </label>
          <LemonButton
            variant="primary"
            onClick={onCompose}
            data-testid="ccca-compose"
          >
            Compose collective analysis intent
          </LemonButton>
          {error ? (
            <p className="text-sm text-danger" data-testid="ccca-error">
              {error}
            </p>
          ) : null}
          {result ? (
            <div
              className="text-sm flex flex-col gap-1 mt-2"
              data-testid="ccca-result"
            >
              <div data-testid="ccca-ready">
                analysis_ready={String(result.analysis_ready)}
              </div>
              <div data-testid="ccca-written">
                analysis_written={String(result.analysis_written)}
              </div>
              <div data-testid="ccca-live">
                live_dispatched={String(result.live_dispatched)}
              </div>
              <div data-testid="ccca-pack">
                pack_dispatched={String(result.pack_dispatched)}
              </div>
              <div data-testid="ccca-summary">
                {formatChaseCompletionCollectiveAnalysisSummary(result)}
              </div>
            </div>
          ) : null}
        </div>
      </LemonCard>
    </div>
  );
}
