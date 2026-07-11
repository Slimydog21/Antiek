/**
 * CollectiveDeepResearchMergePanel - draft/full analysis intent from instances.
 *
 * Free-file. Never writes analysis assets; analysis_written always false.
 */

import { useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../../components/lemon";
import {
  formatCollectiveAnalysisSummary,
  proposeCollectiveAnalysisMerge,
  type CollectiveAnalysisIntent,
} from "../../api/collectiveDeepResearchMerge";

export interface CollectiveDeepResearchMergePanelProps {
  mergeFn?: typeof proposeCollectiveAnalysisMerge;
}

export default function CollectiveDeepResearchMergePanel({
  mergeFn = proposeCollectiveAnalysisMerge,
}: CollectiveDeepResearchMergePanelProps) {
  const [parent, setParent] = useState("asset-1");
  const [idsRaw, setIdsRaw] = useState("fdr_1\nfdr_2");
  const [findingsRaw, setFindingsRaw] = useState("");
  const [ack, setAck] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<CollectiveAnalysisIntent | null>(null);

  function buildInstances() {
    const ids = idsRaw
      .split(/\r?\n/)
      .map((s) => s.trim())
      .filter(Boolean);
    const findings = findingsRaw
      .split(/\r?\n/)
      .map((s) => s.trim())
      .filter(Boolean);
    return ids.map((instance_id, i) => ({
      instance_id,
      parent_asset_id: parent.trim(),
      status: "completed" as const,
      findings: i === 0 ? findings : undefined,
    }));
  }

  function onDraft() {
    setError(null);
    setResult(null);
    try {
      setResult(
        mergeFn(buildInstances(), {
          kind: "draft_analysis",
          operator_ack: false,
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  function onFull() {
    setError(null);
    setResult(null);
    try {
      setResult(
        mergeFn(buildInstances(), {
          kind: "full_analysis",
          operator_ack: ack,
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div data-testid="collective-deep-research-merge-panel">
      <LemonCard
        title="Collective deep research → analysis"
        className="collective-deep-research-merge-panel"
      >
        <p className="text-sm opacity-80" data-testid="cdrm-blurb">
          Merge multiple completed deep-research instances into a written
          analysis intent. Pure client — analysis_written stays false.
        </p>
        <div className="flex flex-col gap-3 mt-3">
          <label className="text-sm flex flex-col gap-1">
            <span>Parent asset id</span>
            <LemonInput
              value={parent}
              onChange={(e) => setParent(e.target.value)}
              data-testid="cdrm-parent"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Instance ids (one per line)</span>
            <textarea
              value={idsRaw}
              onChange={(e) => setIdsRaw(e.target.value)}
              data-testid="cdrm-ids"
              className="border border-border rounded px-2 py-1 text-sm min-h-[4rem]"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Findings for first instance (optional, one per line)</span>
            <textarea
              value={findingsRaw}
              onChange={(e) => setFindingsRaw(e.target.value)}
              data-testid="cdrm-findings"
              className="border border-border rounded px-2 py-1 text-sm min-h-[4rem]"
            />
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={ack}
              onChange={(e) => setAck(e.target.checked)}
              data-testid="cdrm-ack"
            />
            operator_ack (required for full analysis)
          </label>
          <div className="flex gap-2">
            <LemonButton onClick={onDraft} data-testid="cdrm-draft">
              Draft analysis intent
            </LemonButton>
            <LemonButton
              variant="primary"
              onClick={onFull}
              data-testid="cdrm-full"
            >
              Full analysis intent
            </LemonButton>
          </div>
          {error ? (
            <div className="text-sm text-danger" data-testid="cdrm-error">
              {error}
            </div>
          ) : null}
          {result ? (
            <div data-testid="cdrm-result" className="text-sm flex flex-col gap-1">
              <div data-testid="cdrm-summary">
                {formatCollectiveAnalysisSummary(result)}
              </div>
              <div data-testid="cdrm-written">
                analysis_written={String(result.analysis_written)}
              </div>
            </div>
          ) : null}
        </div>
      </LemonCard>
    </div>
  );
}
