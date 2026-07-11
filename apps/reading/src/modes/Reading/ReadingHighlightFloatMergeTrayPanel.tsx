/**
 * ReadingHighlightFloatMergeTrayPanel — reading surface end-to-end pure pack.
 *
 * Free-file. live_dispatched, merge_executed, pack_dispatched always false.
 */

import { useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../../components/lemon";
import {
  composeReadingHighlightFloatMergeTray,
  formatReadingHighlightFloatMergeTraySummary,
  type ReadingHighlightFloatMergeTrayCompose,
  type ReadingSurfaceAction,
} from "../../api/readingHighlightFloatMergeTrayCompose";

export interface ReadingHighlightFloatMergeTrayPanelProps {
  composeFn?: typeof composeReadingHighlightFloatMergeTray;
}

export default function ReadingHighlightFloatMergeTrayPanel({
  composeFn = composeReadingHighlightFloatMergeTray,
}: ReadingHighlightFloatMergeTrayPanelProps) {
  const [parent, setParent] = useState("book-1");
  const [highlight, setHighlight] = useState("scaling laws under noise");
  const [action, setAction] = useState<ReadingSurfaceAction>("spawn_only");
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<ReadingHighlightFloatMergeTrayCompose | null>(null);

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      setResult(
        composeFn({
          parent_asset_id: parent.trim(),
          highlight: highlight.trim(),
          gated: false,
          would_exceed: false,
          preferred_view_mode: "floating",
          source_families: ["arxiv", "substack"],
          surface_action: action,
          operator_ack: ack,
          existing_members:
            action === "tray_collective" || action === "tray_cohesive"
              ? [
                  {
                    instance_id: "existing-1",
                    parent_asset_id: parent.trim() || "book-1",
                    status: "completed",
                    live_dispatched: false,
                    merge_executed: false,
                  },
                ]
              : null,
          selected_instance_ids:
            action === "tray_collective" || action === "tray_cohesive"
              ? ["existing-1"]
              : null,
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div data-testid="reading-highlight-float-merge-tray-panel">
      <LemonCard
        title="Reading · highlight → float → merge tray"
        className="reading-highlight-float-merge-tray-panel"
      >
        <p className="text-sm opacity-80" data-testid="rhfmt-blurb">
          From a reading highlight: spawn floating deep research, then
          fullscreen or merge intents via tray. Pure — live_dispatched and
          merge_executed stay false.
        </p>
        <div className="flex flex-col gap-2 mt-3">
          <label className="text-sm flex flex-col gap-1">
            <span>Parent asset</span>
            <LemonInput
              value={parent}
              onChange={(e) => setParent(e.target.value)}
              data-testid="rhfmt-parent"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Highlight</span>
            <LemonInput
              value={highlight}
              onChange={(e) => setHighlight(e.target.value)}
              data-testid="rhfmt-highlight"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Surface action</span>
            <select
              value={action}
              onChange={(e) =>
                setAction(e.target.value as ReadingSurfaceAction)
              }
              data-testid="rhfmt-action"
              className="border border-border rounded px-2 py-1 text-sm"
            >
              <option value="spawn_only">spawn_only</option>
              <option value="spawn_and_fullscreen">spawn_and_fullscreen</option>
              <option value="spawn_and_draft_merge">spawn_and_draft_merge</option>
              <option value="spawn_and_full_merge">spawn_and_full_merge</option>
              <option value="tray_collective">tray_collective</option>
              <option value="tray_cohesive">tray_cohesive</option>
            </select>
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={ack}
              onChange={(e) => setAck(e.target.checked)}
              data-testid="rhfmt-ack"
            />
            <span>operator_ack</span>
          </label>
          <LemonButton
            variant="primary"
            onClick={onCompose}
            data-testid="rhfmt-compose"
          >
            Compose reading surface pack
          </LemonButton>
          {error ? (
            <p className="text-sm text-danger" data-testid="rhfmt-error">
              {error}
            </p>
          ) : null}
          {result ? (
            <div
              className="text-sm flex flex-col gap-1 mt-2"
              data-testid="rhfmt-result"
            >
              <div data-testid="rhfmt-ready">
                surface_ready={String(result.surface_ready)}
              </div>
              <div data-testid="rhfmt-live">
                live_dispatched={String(result.live_dispatched)}
              </div>
              <div data-testid="rhfmt-merged">
                merge_executed={String(result.merge_executed)}
              </div>
              <div data-testid="rhfmt-pack">
                pack_dispatched={String(result.pack_dispatched)}
              </div>
              <div data-testid="rhfmt-summary">
                {formatReadingHighlightFloatMergeTraySummary(result)}
              </div>
            </div>
          ) : null}
        </div>
      </LemonCard>
    </div>
  );
}
