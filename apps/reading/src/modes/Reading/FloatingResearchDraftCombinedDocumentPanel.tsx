/**
 * FloatingResearchDraftCombinedDocumentPanel - provisional combined draft.
 *
 * Free-file. draft_written and merge_executed always false.
 */

import { useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../../components/lemon";
import {
  composeFloatingResearchDraftCombinedDocument,
  formatFloatingDraftCombinedSummary,
  type ProvisionalCombinedDraft,
} from "../../api/floatingResearchDraftCombinedDocument";

export interface FloatingResearchDraftCombinedDocumentPanelProps {
  composeFn?: typeof composeFloatingResearchDraftCombinedDocument;
}

export default function FloatingResearchDraftCombinedDocumentPanel({
  composeFn = composeFloatingResearchDraftCombinedDocument,
}: FloatingResearchDraftCombinedDocumentPanelProps) {
  const [parent, setParent] = useState("asset-1");
  const [excerpt, setExcerpt] = useState("<p>Original parent body</p>");
  const [instanceId, setInstanceId] = useState("fdr_1");
  const [highlight, setHighlight] = useState("scaling laws");
  const [findingsRaw, setFindingsRaw] = useState("claim A holds under noise");
  const [ack, setAck] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ProvisionalCombinedDraft | null>(null);

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      const findings = findingsRaw
        .split(/\r?\n/)
        .map((s) => s.trim())
        .filter(Boolean);
      setResult(
        composeFn({
          parent_asset_id: parent.trim(),
          parent_excerpt: excerpt.trim() || null,
          operator_ack: ack,
          sources: [
            {
              instance_id: instanceId.trim(),
              parent_asset_id: parent.trim(),
              status: "completed",
              highlight: highlight.trim() || undefined,
              findings: findings.length ? findings : undefined,
            },
          ],
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div data-testid="floating-research-draft-combined-document-panel">
      <LemonCard
        title="Floating research → draft combined document"
        className="floating-research-draft-combined-document-panel"
      >
        <p className="text-sm opacity-80" data-testid="frdcd-blurb">
          Build a provisional combined draft (parent + floating research)
          before full merge. Pure scaffold — draft_written and merge_executed
          stay false.
        </p>
        <div className="flex flex-col gap-3 mt-3">
          <label className="text-sm flex flex-col gap-1">
            <span>Parent asset id</span>
            <LemonInput
              value={parent}
              onChange={(e) => setParent(e.target.value)}
              data-testid="frdcd-parent"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Parent excerpt (HTML/text)</span>
            <textarea
              value={excerpt}
              onChange={(e) => setExcerpt(e.target.value)}
              data-testid="frdcd-excerpt"
              className="border border-border rounded px-2 py-1 text-sm min-h-[3rem]"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Floating instance id</span>
            <LemonInput
              value={instanceId}
              onChange={(e) => setInstanceId(e.target.value)}
              data-testid="frdcd-instance"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Highlight</span>
            <LemonInput
              value={highlight}
              onChange={(e) => setHighlight(e.target.value)}
              data-testid="frdcd-highlight"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Findings (one per line)</span>
            <textarea
              value={findingsRaw}
              onChange={(e) => setFindingsRaw(e.target.value)}
              data-testid="frdcd-findings"
              className="border border-border rounded px-2 py-1 text-sm min-h-[3rem]"
            />
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={ack}
              onChange={(e) => setAck(e.target.checked)}
              data-testid="frdcd-ack"
            />
            operator_ack (preview ack only)
          </label>
          <LemonButton
            variant="primary"
            onClick={onCompose}
            data-testid="frdcd-compose"
          >
            Compose provisional draft
          </LemonButton>
          {error ? (
            <div className="text-sm text-danger" data-testid="frdcd-error">
              {error}
            </div>
          ) : null}
          {result ? (
            <div
              data-testid="frdcd-result"
              className="text-sm flex flex-col gap-1"
            >
              <div data-testid="frdcd-summary">
                {formatFloatingDraftCombinedSummary(result)}
              </div>
              <div data-testid="frdcd-written">
                draft_written={String(result.draft_written)}
              </div>
              <div data-testid="frdcd-merged">
                merge_executed={String(result.merge_executed)}
              </div>
              <div data-testid="frdcd-ready">
                draft_ready={String(result.draft_ready)}
              </div>
            </div>
          ) : null}
        </div>
      </LemonCard>
    </div>
  );
}
