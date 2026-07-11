/**
 * ReadingHighlightFloatTwinFeedPanel — highlight float + twin feed UI.
 *
 * Free-file. live_dispatched, merge_executed, twin_written always false.
 */

import { useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../../components/lemon";
import {
  composeReadingHighlightFloatTwinFeed,
  formatReadingHighlightFloatTwinFeedSummary,
  type ReadingHighlightFloatTwinFeedCompose,
} from "../../api/readingHighlightFloatTwinFeedCompose";
import type { ReadingSurfaceAction } from "../../api/readingHighlightFloatMergeTrayCompose";

export interface ReadingHighlightFloatTwinFeedPanelProps {
  composeFn?: typeof composeReadingHighlightFloatTwinFeed;
}

export default function ReadingHighlightFloatTwinFeedPanel({
  composeFn = composeReadingHighlightFloatTwinFeed,
}: ReadingHighlightFloatTwinFeedPanelProps) {
  const [sessionId, setSessionId] = useState("sess-1");
  const [parent, setParent] = useState("book-1");
  const [highlight, setHighlight] = useState("scaling laws under noise");
  const [action, setAction] = useState<ReadingSurfaceAction>("spawn_only");
  const [ack, setAck] = useState(true);
  const [includeTwin, setIncludeTwin] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<ReadingHighlightFloatTwinFeedCompose | null>(null);

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      setResult(
        composeFn({
          session_id: sessionId.trim(),
          parent_asset_id: parent.trim(),
          highlight: highlight.trim(),
          gated: false,
          would_exceed: false,
          surface_action: action,
          operator_ack: ack,
          source_families: ["arxiv", "substack"],
          include_twin_feed: includeTwin,
          mark_for_prompt_context: true,
          twin_findings: [
            {
              source_id: "extra-1",
              body: "operator insight from highlight",
              kind: "insight",
            },
          ],
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div data-testid="reading-highlight-float-twin-feed-panel">
      <LemonCard
        title="Reading · highlight → float + twin feed"
        className="reading-highlight-float-twin-feed-panel"
      >
        <p className="text-sm opacity-80" data-testid="rhftf-blurb">
          From a highlight: floating deep research tray intents and twin note
          substrate feed. Pure — never dispatches or writes twins.
        </p>
        <div className="flex flex-col gap-2 mt-3">
          <label className="text-sm flex flex-col gap-1">
            <span>Session</span>
            <LemonInput
              value={sessionId}
              onChange={(e) => setSessionId(e.target.value)}
              data-testid="rhftf-session"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Parent asset</span>
            <LemonInput
              value={parent}
              onChange={(e) => setParent(e.target.value)}
              data-testid="rhftf-parent"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Highlight</span>
            <LemonInput
              value={highlight}
              onChange={(e) => setHighlight(e.target.value)}
              data-testid="rhftf-highlight"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Surface action</span>
            <select
              value={action}
              onChange={(e) =>
                setAction(e.target.value as ReadingSurfaceAction)
              }
              data-testid="rhftf-action"
              className="border border-border rounded px-2 py-1 text-sm"
            >
              <option value="spawn_only">spawn_only</option>
              <option value="spawn_and_fullscreen">spawn_and_fullscreen</option>
              <option value="spawn_and_draft_merge">spawn_and_draft_merge</option>
            </select>
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={includeTwin}
              onChange={(e) => setIncludeTwin(e.target.checked)}
              data-testid="rhftf-twin"
            />
            <span>include_twin_feed</span>
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={ack}
              onChange={(e) => setAck(e.target.checked)}
              data-testid="rhftf-ack"
            />
            <span>operator_ack</span>
          </label>
          <LemonButton
            variant="primary"
            onClick={onCompose}
            data-testid="rhftf-compose"
          >
            Compose highlight float + twin feed
          </LemonButton>
          {error ? (
            <p className="text-sm text-danger" data-testid="rhftf-error">
              {error}
            </p>
          ) : null}
          {result ? (
            <div
              className="text-sm flex flex-col gap-1 mt-2"
              data-testid="rhftf-result"
            >
              <div data-testid="rhftf-ready">
                pack_ready={String(result.pack_ready)}
              </div>
              <div data-testid="rhftf-live">
                live_dispatched={String(result.live_dispatched)}
              </div>
              <div data-testid="rhftf-merge">
                merge_executed={String(result.merge_executed)}
              </div>
              <div data-testid="rhftf-twin-w">
                twin_written={String(result.twin_written)}
              </div>
              <div data-testid="rhftf-summary">
                {formatReadingHighlightFloatTwinFeedSummary(result)}
              </div>
            </div>
          ) : null}
        </div>
      </LemonCard>
    </div>
  );
}
