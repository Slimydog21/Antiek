/**
 * WriteModeTwinDraftMergePanel — twin substrate → write draft.
 *
 * Free-file. draft_written, merge_executed, store_mutated always false.
 */

import { useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../../components/lemon";
import {
  composeWriteModeTwinDraftMerge,
  formatWriteModeTwinDraftMergeSummary,
  type WriteModeTwinDraftMergeCompose,
} from "../../api/writeModeTwinDraftMergeCompose";

export interface WriteModeTwinDraftMergePanelProps {
  composeFn?: typeof composeWriteModeTwinDraftMerge;
}

export default function WriteModeTwinDraftMergePanel({
  composeFn = composeWriteModeTwinDraftMerge,
}: WriteModeTwinDraftMergePanelProps) {
  const [draftId, setDraftId] = useState("draft-1");
  const [base, setBase] = useState("<p>Opening argument</p>");
  const [insight, setInsight] = useState("claim holds under noise");
  const [question, setQuestion] = useState("sample size?");
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<WriteModeTwinDraftMergeCompose | null>(null);

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      setResult(
        composeFn({
          draft_id: draftId.trim(),
          base_draft_html: base.trim() || null,
          operator_ack: ack,
          slices: [
            {
              parent_asset_id: "asset-a",
              insights: insight.trim() ? [insight.trim()] : [],
              questions: question.trim() ? [question.trim()] : [],
            },
            {
              parent_asset_id: "asset-b",
              insights: ["routing is non-linear"],
              questions: [],
            },
          ],
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div data-testid="write-mode-twin-draft-merge-panel">
      <LemonCard
        title="Write mode · twin draft merge"
        className="write-mode-twin-draft-merge-panel"
      >
        <p className="text-sm opacity-80" data-testid="wmtdm-blurb">
          Merge twin insights/questions into a provisional HTML write draft.
          Pure — draft_written, merge_executed, store_mutated stay false.
        </p>
        <div className="flex flex-col gap-2 mt-3">
          <label className="text-sm flex flex-col gap-1">
            <span>Draft id</span>
            <LemonInput
              value={draftId}
              onChange={(e) => setDraftId(e.target.value)}
              data-testid="wmtdm-draft"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Base draft HTML</span>
            <textarea
              value={base}
              onChange={(e) => setBase(e.target.value)}
              data-testid="wmtdm-base"
              className="border border-border rounded px-2 py-1 text-sm min-h-[3rem]"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Twin insight</span>
            <LemonInput
              value={insight}
              onChange={(e) => setInsight(e.target.value)}
              data-testid="wmtdm-insight"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Twin question</span>
            <LemonInput
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              data-testid="wmtdm-question"
            />
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={ack}
              onChange={(e) => setAck(e.target.checked)}
              data-testid="wmtdm-ack"
            />
            <span>operator_ack</span>
          </label>
          <LemonButton
            variant="primary"
            onClick={onCompose}
            data-testid="wmtdm-compose"
          >
            Compose twin write draft
          </LemonButton>
          {error ? (
            <p className="text-sm text-danger" data-testid="wmtdm-error">
              {error}
            </p>
          ) : null}
          {result ? (
            <div
              className="text-sm flex flex-col gap-1 mt-2"
              data-testid="wmtdm-result"
            >
              <div data-testid="wmtdm-ready">
                draft_ready={String(result.draft_ready)}
              </div>
              <div data-testid="wmtdm-written">
                draft_written={String(result.draft_written)}
              </div>
              <div data-testid="wmtdm-merged">
                merge_executed={String(result.merge_executed)}
              </div>
              <div data-testid="wmtdm-store">
                store_mutated={String(result.store_mutated)}
              </div>
              <div data-testid="wmtdm-summary">
                {formatWriteModeTwinDraftMergeSummary(result)}
              </div>
            </div>
          ) : null}
        </div>
      </LemonCard>
    </div>
  );
}
