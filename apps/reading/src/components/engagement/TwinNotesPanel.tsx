/**
 * TwinNotesPanel — recursive note-taker substrate CRUD UI.
 *
 * Consumes #785 twin routes: record / list-by-parent / merge.
 * Free-file: does not own Reading/index, App.tsx, or rrv-712.
 * No LLM dispatch — operator (or upstream note-taker) supplies insights/questions.
 */

import { useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../lemon";
import {
  formatTwinSummary,
  listTwinsForParent,
  mergeTwins,
  parseLines,
  parseListTwinsResult,
  parseTwinDocument,
  recordTwin,
  type ListTwinsResult,
  type TwinDocument,
} from "../../api/twinNotes";

export interface TwinNotesPanelProps {
  recordFn?: (
    req: Parameters<typeof recordTwin>[0],
  ) => Promise<TwinDocument | unknown>;
  listFn?: (parentAssetId: string) => Promise<ListTwinsResult | unknown>;
  mergeFn?: (
    req: Parameters<typeof mergeTwins>[0],
  ) => Promise<TwinDocument | unknown>;
  initialParentAssetId?: string;
}

export default function TwinNotesPanel({
  recordFn = recordTwin,
  listFn = listTwinsForParent,
  mergeFn = mergeTwins,
  initialParentAssetId = "",
}: TwinNotesPanelProps) {
  const [parentAssetId, setParentAssetId] = useState(initialParentAssetId);
  const [insightsRaw, setInsightsRaw] = useState("");
  const [questionsRaw, setQuestionsRaw] = useState("");
  const [sourceLabel, setSourceLabel] = useState("note-taker");
  const [mergeIdsRaw, setMergeIdsRaw] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastRecorded, setLastRecorded] = useState<TwinDocument | null>(null);
  const [list, setList] = useState<ListTwinsResult | null>(null);
  const [merged, setMerged] = useState<TwinDocument | null>(null);

  async function onRecord() {
    setBusy(true);
    setError(null);
    setLastRecorded(null);
    try {
      const raw = await recordFn({
        parent_asset_id: parentAssetId.trim(),
        insights: parseLines(insightsRaw),
        questions: parseLines(questionsRaw),
        source_label: sourceLabel,
      });
      setLastRecorded(parseTwinDocument(raw));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function onList() {
    setBusy(true);
    setError(null);
    setList(null);
    try {
      const raw = await listFn(parentAssetId.trim());
      setList(parseListTwinsResult(raw));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function onMerge() {
    setBusy(true);
    setError(null);
    setMerged(null);
    try {
      const twin_ids = mergeIdsRaw
        .split(/[\s,]+/)
        .map((s) => s.trim())
        .filter(Boolean);
      const raw = await mergeFn({
        twin_ids,
        parent_asset_id: parentAssetId.trim() || null,
        source_label: "merged",
      });
      setMerged(parseTwinDocument(raw));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div data-testid="twin-notes-panel">
      <LemonCard title="Twin notes (recursive note-taker)" className="twin-notes-panel">
        <p className="text-sm opacity-80" data-testid="twin-notes-blurb">
          Every information asset can hold a twin document of insights and
          questions. Record, list, and merge same-parent twins. Cross-parent
          merge is rejected. This panel does not dispatch models.
        </p>

        <div className="flex flex-col gap-3 mt-3">
          <label className="text-sm flex flex-col gap-1">
            <span>Parent asset id</span>
            <LemonInput
              value={parentAssetId}
              onChange={(e) => setParentAssetId(e.target.value)}
              placeholder="asset-…"
              data-testid="twin-notes-parent"
              aria-label="Parent asset id"
              disabled={busy}
            />
          </label>

          <label className="text-sm flex flex-col gap-1">
            <span>Insights (one per line)</span>
            <textarea
              className="min-h-[64px] w-full rounded border border-border bg-bg-light px-2 py-1 text-sm"
              value={insightsRaw}
              onChange={(e) => setInsightsRaw(e.target.value)}
              data-testid="twin-notes-insights"
              aria-label="Insights"
              disabled={busy}
            />
          </label>

          <label className="text-sm flex flex-col gap-1">
            <span>Questions (one per line)</span>
            <textarea
              className="min-h-[64px] w-full rounded border border-border bg-bg-light px-2 py-1 text-sm"
              value={questionsRaw}
              onChange={(e) => setQuestionsRaw(e.target.value)}
              data-testid="twin-notes-questions"
              aria-label="Questions"
              disabled={busy}
            />
          </label>

          <label className="text-sm flex flex-col gap-1">
            <span>Source label</span>
            <LemonInput
              value={sourceLabel}
              onChange={(e) => setSourceLabel(e.target.value)}
              data-testid="twin-notes-source"
              aria-label="Source label"
              disabled={busy}
            />
          </label>

          <div className="flex flex-wrap gap-2">
            <LemonButton
              variant="primary"
              disabled={busy}
              onClick={() => void onRecord()}
              data-testid="twin-notes-record"
            >
              {busy ? "Working…" : "Record twin"}
            </LemonButton>
            <LemonButton
              disabled={busy}
              onClick={() => void onList()}
              data-testid="twin-notes-list"
            >
              List by parent
            </LemonButton>
          </div>

          <label className="text-sm flex flex-col gap-1">
            <span>Merge twin ids (same parent only)</span>
            <LemonInput
              value={mergeIdsRaw}
              onChange={(e) => setMergeIdsRaw(e.target.value)}
              placeholder="twin-a, twin-b"
              data-testid="twin-notes-merge-ids"
              aria-label="Merge twin ids"
              disabled={busy}
            />
          </label>
          <LemonButton
            disabled={busy}
            onClick={() => void onMerge()}
            data-testid="twin-notes-merge"
          >
            Merge twins
          </LemonButton>

          {error ? (
            <div className="text-sm text-danger" data-testid="twin-notes-error">
              {error}
            </div>
          ) : null}

          {lastRecorded ? (
            <div data-testid="twin-notes-recorded" className="text-sm">
              Recorded: {formatTwinSummary(lastRecorded)}
            </div>
          ) : null}

          {list ? (
            <div data-testid="twin-notes-list-result" className="flex flex-col gap-1">
              <div data-testid="twin-notes-list-count">
                {list.twins.length} twin{list.twins.length === 1 ? "" : "s"} for{" "}
                {list.parent_asset_id}
              </div>
              <ul className="text-xs list-disc pl-4">
                {list.twins.map((t) => (
                  <li key={t.twin_id} data-testid={`twin-notes-item-${t.twin_id}`}>
                    {formatTwinSummary(t)}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          {merged ? (
            <div data-testid="twin-notes-merged" className="text-sm">
              Merged: {formatTwinSummary(merged)}
            </div>
          ) : null}
        </div>
      </LemonCard>
    </div>
  );
}
