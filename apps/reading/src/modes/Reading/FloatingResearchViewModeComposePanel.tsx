/**
 * FloatingResearchViewModeComposePanel — float / fullscreen / merge intents.
 *
 * Free-file. live_dispatched and merge_executed always false.
 */

import { useMemo, useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../../components/lemon";
import {
  markFloatingCompleted,
  spawnFloatingFromHighlight,
  type FloatingDeepResearchInstance,
} from "../../api/floatingDeepResearch";
import {
  composeFloatingResearchViewMode,
  formatFloatingViewModeComposeSummary,
  type FloatingResearchViewModeCompose,
  type FloatingViewModeAction,
} from "../../api/floatingResearchViewModeCompose";

export interface FloatingResearchViewModeComposePanelProps {
  composeFn?: typeof composeFloatingResearchViewMode;
  spawnFn?: typeof spawnFloatingFromHighlight;
}

export default function FloatingResearchViewModeComposePanel({
  composeFn = composeFloatingResearchViewMode,
  spawnFn = spawnFloatingFromHighlight,
}: FloatingResearchViewModeComposePanelProps) {
  const [parent, setParent] = useState("asset-read-1");
  const [highlight, setHighlight] = useState("scaling laws under noise");
  const [completed, setCompleted] = useState(false);
  const [ack, setAck] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<FloatingResearchViewModeCompose | null>(
    null,
  );
  const [instance, setInstance] = useState<FloatingDeepResearchInstance | null>(
    null,
  );

  const base = useMemo(() => {
    try {
      let inst = spawnFn({
        parent_asset_id: parent.trim() || "asset-read-1",
        highlight: highlight.trim() || "highlight",
        gated: false,
      });
      if (completed) {
        inst = markFloatingCompleted(inst);
      }
      return inst;
    } catch {
      return null;
    }
  }, [parent, highlight, completed, spawnFn]);

  function run(action: FloatingViewModeAction) {
    setError(null);
    setResult(null);
    const src = instance ?? base;
    if (!src) {
      setError("could not spawn base instance");
      return;
    }
    try {
      const c = composeFn({
        instance: src,
        action,
        operator_ack: action === "propose_full_merge" ? ack : undefined,
      });
      setResult(c);
      setInstance(c.instance);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div data-testid="floating-research-view-mode-compose-panel">
      <LemonCard
        title="Floating research · view mode compose"
        className="floating-research-view-mode-compose-panel"
      >
        <p className="text-sm opacity-80" data-testid="frvmc-blurb">
          Float, fullscreen, draft-merge intent, or full-merge intent over a
          pure floating deep-research instance. live_dispatched and
          merge_executed stay false.
        </p>
        <div className="flex flex-col gap-3 mt-3">
          <label className="text-sm flex flex-col gap-1">
            <span>Parent asset id</span>
            <LemonInput
              value={parent}
              onChange={(e) => setParent(e.target.value)}
              data-testid="frvmc-parent"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Highlight</span>
            <LemonInput
              value={highlight}
              onChange={(e) => setHighlight(e.target.value)}
              data-testid="frvmc-highlight"
            />
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={completed}
              onChange={(e) => {
                setCompleted(e.target.checked);
                setInstance(null);
              }}
              data-testid="frvmc-completed"
            />
            <span>Mark completed (required for full merge)</span>
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={ack}
              onChange={(e) => setAck(e.target.checked)}
              data-testid="frvmc-ack"
            />
            <span>operator_ack (full merge)</span>
          </label>
          <div className="flex flex-wrap gap-2">
            <LemonButton
              type="secondary"
              onClick={() => run("float")}
              data-testid="frvmc-float"
            >
              Float
            </LemonButton>
            <LemonButton
              type="secondary"
              onClick={() => run("fullscreen")}
              data-testid="frvmc-fullscreen"
            >
              Fullscreen
            </LemonButton>
            <LemonButton
              type="secondary"
              onClick={() => run("propose_draft_merge")}
              data-testid="frvmc-draft"
            >
              Draft merge intent
            </LemonButton>
            <LemonButton
              type="primary"
              onClick={() => run("propose_full_merge")}
              data-testid="frvmc-full"
            >
              Full merge intent
            </LemonButton>
          </div>
          {error ? (
            <p className="text-sm text-danger" data-testid="frvmc-error">
              {error}
            </p>
          ) : null}
          {result ? (
            <div
              className="text-sm flex flex-col gap-1 mt-2"
              data-testid="frvmc-result"
            >
              <div data-testid="frvmc-action">action={result.action}</div>
              <div data-testid="frvmc-view-mode">
                view_mode={result.view_mode}
              </div>
              <div data-testid="frvmc-applied">
                applied={String(result.action_applied)}
              </div>
              <div data-testid="frvmc-live">
                live_dispatched={String(result.live_dispatched)}
              </div>
              <div data-testid="frvmc-merged">
                merge_executed={String(result.merge_executed)}
              </div>
              <div data-testid="frvmc-intent">
                intent=
                {result.merge_intent ? result.merge_intent.kind : "none"}
              </div>
              <div data-testid="frvmc-summary">
                {formatFloatingViewModeComposeSummary(result)}
              </div>
            </div>
          ) : null}
        </div>
      </LemonCard>
    </div>
  );
}
