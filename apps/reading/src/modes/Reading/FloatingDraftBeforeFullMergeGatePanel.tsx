/**
 * FloatingDraftBeforeFullMergeGatePanel — draft combined doc before full merge.
 *
 * Free-file. draft_written/merge_executed/live_dispatched always false.
 */

import { useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../../components/lemon";
import {
  composeFloatingDraftBeforeFullMergeGate,
  formatFloatingDraftBeforeFullMergeGateSummary,
  type FloatingDraftBeforeFullMergeGateCompose,
  type MergeStage,
} from "../../api/floatingDraftBeforeFullMergeGateCompose";

export interface FloatingDraftBeforeFullMergeGatePanelProps {
  composeFn?: typeof composeFloatingDraftBeforeFullMergeGate;
}

export default function FloatingDraftBeforeFullMergeGatePanel({
  composeFn = composeFloatingDraftBeforeFullMergeGate,
}: FloatingDraftBeforeFullMergeGatePanelProps) {
  const [excerpt, setExcerpt] = useState("Parent HTML excerpt");
  const [finding, setFinding] = useState("Floating research finding");
  const [stage, setStage] = useState<MergeStage>("draft_only");
  const [ack, setAck] = useState(true);
  const [fullAck, setFullAck] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<FloatingDraftBeforeFullMergeGateCompose | null>(null);

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      setResult(
        composeFn({
          session_id: "sess-demo",
          parent_asset_id: "asset-demo",
          parent_excerpt: excerpt.trim() || null,
          sources: [
            {
              instance_id: "float-demo",
              parent_asset_id: "asset-demo",
              status: "completed",
              highlight: "highlight from float",
              findings: finding.trim() ? [finding.trim()] : undefined,
            },
          ],
          stage,
          operator_ack: ack,
          full_merge_ack:
            stage === "promote_full_merge" ? fullAck : undefined,
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div data-testid="floating-draft-before-full-merge-gate-panel">
      <LemonCard
        title="Reading · draft before full merge"
        className="floating-draft-before-full-merge-gate-panel"
      >
        <p className="text-sm opacity-80" data-testid="fdbfm-blurb">
          Create a provisional combined draft from floating research before
          promoting to full parent merge. Pure — never writes or merges.
        </p>
        <div className="flex flex-col gap-2 mt-3">
          <label className="text-sm flex flex-col gap-1">
            <span>Parent excerpt</span>
            <LemonInput
              value={excerpt}
              onChange={(e) => setExcerpt(e.target.value)}
              data-testid="fdbfm-excerpt"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Finding</span>
            <LemonInput
              value={finding}
              onChange={(e) => setFinding(e.target.value)}
              data-testid="fdbfm-finding"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Stage</span>
            <select
              value={stage}
              onChange={(e) => setStage(e.target.value as MergeStage)}
              data-testid="fdbfm-stage"
              className="border border-border rounded px-2 py-1 text-sm"
            >
              <option value="draft_only">draft_only</option>
              <option value="promote_full_merge">promote_full_merge</option>
            </select>
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={ack}
              onChange={(e) => setAck(e.target.checked)}
              data-testid="fdbfm-ack"
            />
            <span>operator_ack (draft)</span>
          </label>
          {stage === "promote_full_merge" && (
            <label className="text-sm flex items-center gap-2">
              <input
                type="checkbox"
                checked={fullAck}
                onChange={(e) => setFullAck(e.target.checked)}
                data-testid="fdbfm-full-ack"
              />
              <span>full_merge_ack (separate)</span>
            </label>
          )}
          <LemonButton
            type="primary"
            onClick={onCompose}
            data-testid="fdbfm-compose"
          >
            Compose draft/merge gate
          </LemonButton>
        </div>
        {error && (
          <p className="text-sm text-danger mt-2" data-testid="fdbfm-error">
            {error}
          </p>
        )}
        {result && (
          <div className="mt-3 text-sm" data-testid="fdbfm-result">
            <p data-testid="fdbfm-summary">
              {formatFloatingDraftBeforeFullMergeGateSummary(result)}
            </p>
            <ul className="list-disc pl-5 mt-1 opacity-80">
              <li>gate_ready={String(result.gate_ready)}</li>
              <li>
                full_merge_intent_ready=
                {String(result.full_merge_intent_ready)}
              </li>
              <li>draft_written={String(result.draft_written)}</li>
              <li>merge_executed={String(result.merge_executed)}</li>
              <li>sections={result.draft.section_count}</li>
            </ul>
          </div>
        )}
      </LemonCard>
    </div>
  );
}
