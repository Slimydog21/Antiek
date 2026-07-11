/**
 * HighlightDeepResearchLaunchPanel — highlight → pure DR launch package.
 *
 * Free-file. live_dispatched and merge_executed always false.
 */

import { useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../../components/lemon";
import {
  composeHighlightDeepResearchLaunch,
  formatHighlightDeepResearchLaunchSummary,
  type HighlightDeepResearchLaunchCompose,
} from "../../api/highlightDeepResearchLaunchCompose";

export interface HighlightDeepResearchLaunchPanelProps {
  composeFn?: typeof composeHighlightDeepResearchLaunch;
}

export default function HighlightDeepResearchLaunchPanel({
  composeFn = composeHighlightDeepResearchLaunch,
}: HighlightDeepResearchLaunchPanelProps) {
  const [parent, setParent] = useState("asset-read-1");
  const [highlight, setHighlight] = useState("scaling laws under noise");
  const [model, setModel] = useState("gpt-5");
  const [viewMode, setViewMode] = useState<"floating" | "fullscreen">(
    "floating",
  );
  const [wouldExceed, setWouldExceed] = useState<"false" | "true" | "null">(
    "false",
  );
  const [ack, setAck] = useState(true);
  const [arxiv, setArxiv] = useState(true);
  const [substack, setSubstack] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<HighlightDeepResearchLaunchCompose | null>(null);

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      const would_exceed =
        wouldExceed === "null"
          ? null
          : wouldExceed === "true"
            ? true
            : false;
      const source_families: Array<"arxiv" | "substack"> = [];
      if (arxiv) source_families.push("arxiv");
      if (substack) source_families.push("substack");
      setResult(
        composeFn({
          parent_asset_id: parent.trim(),
          highlight: highlight.trim(),
          gated: false,
          preferred_view_mode: viewMode,
          would_exceed,
          selected_model_id: model.trim() || null,
          source_families: source_families.length ? source_families : null,
          operator_ack: ack,
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div data-testid="highlight-deep-research-launch-panel">
      <LemonCard
        title="Highlight → deep research launch"
        className="highlight-deep-research-launch-panel"
      >
        <p className="text-sm opacity-80" data-testid="hdrl-blurb">
          Package a floating deep-research launch from a highlight with view
          mode, model choice, budget honesty, and source families. Pure —
          live_dispatched stays false.
        </p>
        <div className="flex flex-col gap-2 mt-3">
          <label className="text-sm flex flex-col gap-1">
            <span>Parent asset</span>
            <LemonInput
              value={parent}
              onChange={(e) => setParent(e.target.value)}
              data-testid="hdrl-parent"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Highlight</span>
            <LemonInput
              value={highlight}
              onChange={(e) => setHighlight(e.target.value)}
              data-testid="hdrl-highlight"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Model id</span>
            <LemonInput
              value={model}
              onChange={(e) => setModel(e.target.value)}
              data-testid="hdrl-model"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>View mode</span>
            <select
              value={viewMode}
              onChange={(e) =>
                setViewMode(e.target.value as "floating" | "fullscreen")
              }
              data-testid="hdrl-view"
              className="border border-border rounded px-2 py-1 text-sm"
            >
              <option value="floating">floating</option>
              <option value="fullscreen">fullscreen</option>
            </select>
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>would_exceed</span>
            <select
              value={wouldExceed}
              onChange={(e) =>
                setWouldExceed(e.target.value as "false" | "true" | "null")
              }
              data-testid="hdrl-budget"
              className="border border-border rounded px-2 py-1 text-sm"
            >
              <option value="false">false</option>
              <option value="true">true</option>
              <option value="null">null</option>
            </select>
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={arxiv}
              onChange={(e) => setArxiv(e.target.checked)}
              data-testid="hdrl-arxiv"
            />
            <span>arxiv</span>
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={substack}
              onChange={(e) => setSubstack(e.target.checked)}
              data-testid="hdrl-substack"
            />
            <span>substack</span>
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={ack}
              onChange={(e) => setAck(e.target.checked)}
              data-testid="hdrl-ack"
            />
            <span>operator_ack</span>
          </label>
          <LemonButton
            variant="primary"
            onClick={onCompose}
            data-testid="hdrl-compose"
          >
            Compose launch package
          </LemonButton>
          {error ? (
            <p className="text-sm text-danger" data-testid="hdrl-error">
              {error}
            </p>
          ) : null}
          {result ? (
            <div
              className="text-sm flex flex-col gap-1 mt-2"
              data-testid="hdrl-result"
            >
              <div data-testid="hdrl-ready">
                launch_ready={String(result.launch_ready)}
              </div>
              <div data-testid="hdrl-live">
                live_dispatched={String(result.live_dispatched)}
              </div>
              <div data-testid="hdrl-merged">
                merge_executed={String(result.merge_executed)}
              </div>
              <div data-testid="hdrl-mode">
                view_mode={result.preferred_view_mode}
              </div>
              <div data-testid="hdrl-summary">
                {formatHighlightDeepResearchLaunchSummary(result)}
              </div>
            </div>
          ) : null}
        </div>
      </LemonCard>
    </div>
  );
}
