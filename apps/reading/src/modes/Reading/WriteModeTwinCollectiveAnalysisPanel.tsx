/**
 * WriteModeTwinCollectiveAnalysisPanel — twin draft + collective analysis.
 *
 * Free-file. draft_written/analysis_written/merge always false.
 */

import { useState } from "react";
import { LemonButton, LemonCard } from "../../components/lemon";
import {
  composeWriteModeTwinCollectiveAnalysis,
  formatWriteModeTwinCollectiveAnalysisSummary,
  type WriteModeTwinCollectiveAnalysisCompose,
} from "../../api/writeModeTwinCollectiveAnalysisCompose";

export interface WriteModeTwinCollectiveAnalysisPanelProps {
  composeFn?: typeof composeWriteModeTwinCollectiveAnalysis;
}

export default function WriteModeTwinCollectiveAnalysisPanel({
  composeFn = composeWriteModeTwinCollectiveAnalysis,
}: WriteModeTwinCollectiveAnalysisPanelProps) {
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<WriteModeTwinCollectiveAnalysisCompose | null>(null);

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      setResult(
        composeFn({
          session_id: "sess-demo",
          draft_id: "draft-demo",
          parent_asset_id: "asset-demo",
          twin_slices: [
            {
              parent_asset_id: "asset-demo",
              insights: ["twin insight for write draft"],
              questions: ["What remains open?"],
            },
            {
              parent_asset_id: "asset-other",
              insights: ["related twin insight"],
              questions: [],
            },
          ],
          base_draft_html: "<p>Draft opening</p>",
          chase_slots: [
            {
              slot_id: "s1",
              question_id: "q1",
              parent_asset_id: "asset-demo",
              status: "completed",
              findings: ["chase finding A"],
              body: "Evidence for claim?",
            },
            {
              slot_id: "s2",
              question_id: "q2",
              parent_asset_id: "asset-demo",
              status: "completed",
              findings: ["chase finding B"],
              body: "Counter-evidence?",
            },
          ],
          analysis_kind: "draft_analysis",
          operator_ack: ack,
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div data-testid="write-mode-twin-collective-analysis-panel">
      <LemonCard
        title="Write · twin draft + collective analysis"
        className="write-mode-twin-collective-analysis-panel"
      >
        <p className="text-sm opacity-80" data-testid="wtca-blurb">
          Fold twin notes into a provisional write draft and merge completed
          chases into analysis intent. Pure — never writes assets.
        </p>
        <div className="flex flex-col gap-2 mt-3">
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={ack}
              onChange={(e) => setAck(e.target.checked)}
              data-testid="wtca-ack"
            />
            <span>operator_ack</span>
          </label>
          <LemonButton
            type="primary"
            onClick={onCompose}
            data-testid="wtca-compose"
          >
            Compose write + analysis pack
          </LemonButton>
        </div>
        {error && (
          <p className="text-sm text-danger mt-2" data-testid="wtca-error">
            {error}
          </p>
        )}
        {result && (
          <div className="mt-3 text-sm" data-testid="wtca-result">
            <p data-testid="wtca-summary">
              {formatWriteModeTwinCollectiveAnalysisSummary(result)}
            </p>
            <ul className="list-disc pl-5 mt-1 opacity-80">
              <li>pack_ready={String(result.pack_ready)}</li>
              <li>draft_written={String(result.draft_written)}</li>
              <li>analysis_written={String(result.analysis_written)}</li>
              <li>merge_executed={String(result.merge_executed)}</li>
            </ul>
          </div>
        )}
      </LemonCard>
    </div>
  );
}
