/**
 * DraftMergePanel — provisional parent+twins HTML draft before final merge.
 *
 * Consumes POST /twins/draft-merge (PR #800). Does not mutate the parent asset.
 * Cross-parent rejections surface as 409 honesty copy.
 *
 * Free-file mount: Reading/SpawnMergePanel ownership stays with rrv-712.
 */

import { useMemo, useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../lemon";
import {
  formatProvisional,
  formatTwinCount,
  isCrossParentRejection,
  postDraftMerge,
  type DraftMergeResult,
} from "../../api/draftMerge";

export interface DraftMergePanelProps {
  draftFn?: typeof postDraftMerge;
  initialParentId?: string;
  initialParentHtml?: string;
  initialTwinIds?: string;
  initialTitle?: string;
}

function parseTwinIds(raw: string): string[] {
  return raw
    .split(/[\s,]+/)
    .map((s) => s.trim())
    .filter(Boolean);
}

export default function DraftMergePanel({
  draftFn = postDraftMerge,
  initialParentId = "",
  initialParentHtml = "",
  initialTwinIds = "",
  initialTitle = "Draft merge",
}: DraftMergePanelProps) {
  const [parentId, setParentId] = useState(initialParentId);
  const [parentHtml, setParentHtml] = useState(initialParentHtml);
  const [twinIdsRaw, setTwinIdsRaw] = useState(initialTwinIds);
  const [title, setTitle] = useState(initialTitle);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [crossParent, setCrossParent] = useState(false);
  const [result, setResult] = useState<DraftMergeResult | null>(null);

  const twinIds = useMemo(() => parseTwinIds(twinIdsRaw), [twinIdsRaw]);

  async function onBuild() {
    setBusy(true);
    setError(null);
    setCrossParent(false);
    try {
      const body = await draftFn({
        parent_asset_id: parentId,
        parent_html: parentHtml,
        twin_ids: twinIds,
        title,
      });
      setResult(body);
    } catch (e) {
      setResult(null);
      setCrossParent(isCrossParentRejection(e));
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div data-testid="draft-merge-panel">
      <LemonCard title="Provisional draft merge" className="draft-merge-panel">
        <p className="text-sm opacity-80" data-testid="draft-merge-blurb">
          Combine a parent asset snapshot with selected twin notes into a
          provisional HTML draft for review. This does not merge into the
          parent until you explicitly finalize later.
        </p>

        <div className="flex flex-col gap-3 mt-3">
          <label className="text-sm flex flex-col gap-1">
            <span>Parent asset id</span>
            <LemonInput
              value={parentId}
              onChange={(e) => setParentId(e.target.value)}
              placeholder="asset-…"
              data-testid="draft-merge-parent-id"
              aria-label="Parent asset id"
            />
          </label>

          <label className="text-sm flex flex-col gap-1">
            <span>Parent HTML snapshot (escaped by server)</span>
            <textarea
              className="min-h-[80px] w-full rounded border border-border bg-bg-light px-2 py-1 font-mono text-xs"
              value={parentHtml}
              onChange={(e) => setParentHtml(e.target.value)}
              placeholder="<p>…</p>"
              data-testid="draft-merge-parent-html"
              aria-label="Parent HTML snapshot"
            />
          </label>

          <label className="text-sm flex flex-col gap-1">
            <span>Twin ids (comma or space separated)</span>
            <LemonInput
              value={twinIdsRaw}
              onChange={(e) => setTwinIdsRaw(e.target.value)}
              placeholder="twin-a, twin-b"
              data-testid="draft-merge-twin-ids"
              aria-label="Twin ids"
            />
          </label>

          <label className="text-sm flex flex-col gap-1">
            <span>Draft title</span>
            <LemonInput
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              data-testid="draft-merge-title"
              aria-label="Draft title"
            />
          </label>

          <LemonButton
            variant="primary"
            disabled={busy}
            onClick={() => void onBuild()}
            data-testid="draft-merge-build"
          >
            {busy ? "Building…" : "Build provisional draft"}
          </LemonButton>

          {error ? (
            <div
              className="text-sm text-danger"
              data-testid="draft-merge-error"
              data-cross-parent={crossParent ? "true" : "false"}
            >
              {crossParent
                ? `Cross-parent draft merge rejected: ${error}`
                : error}
            </div>
          ) : null}

          {result ? (
            <div data-testid="draft-merge-result" className="flex flex-col gap-2">
              <div data-testid="draft-merge-provisional">
                {formatProvisional(result.provisional)}
              </div>
              <div data-testid="draft-merge-draft-id">
                Draft id: {result.draft_id}
              </div>
              <div data-testid="draft-merge-parent">
                Parent: {result.parent_asset_id}
              </div>
              <div data-testid="draft-merge-twins">
                {formatTwinCount(result.twin_ids)} ({result.twin_ids.join(", ")})
              </div>
              <div data-testid="draft-merge-counts">
                Insights: {result.insight_count}; questions:{" "}
                {result.question_count}
              </div>
              <pre
                className="max-h-48 overflow-auto rounded border border-border bg-bg-light p-2 text-xs"
                data-testid="draft-merge-html"
              >
                {result.html}
              </pre>
            </div>
          ) : null}
        </div>
      </LemonCard>
    </div>
  );
}
