/**
 * RecursiveTwinNoteTakerPanel — twin note-taker proposal pack.
 *
 * Free-file. twin_written, prompts_injected, live_dispatch_authorized false.
 */

import { useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../../components/lemon";
import {
  composeRecursiveTwinNoteTaker,
  formatRecursiveTwinNoteTakerSummary,
  type RecursiveTwinNoteTakerCompose,
} from "../../api/recursiveTwinNoteTakerCompose";

export interface RecursiveTwinNoteTakerPanelProps {
  composeFn?: typeof composeRecursiveTwinNoteTaker;
}

export default function RecursiveTwinNoteTakerPanel({
  composeFn = composeRecursiveTwinNoteTaker,
}: RecursiveTwinNoteTakerPanelProps) {
  const [parent, setParent] = useState("asset-1");
  const [excerpt, setExcerpt] = useState("<p>Scaling laws under noise</p>");
  const [focus, setFocus] = useState("What is the sample size?");
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<RecursiveTwinNoteTakerCompose | null>(null);

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      setResult(
        composeFn({
          parent_asset_id: parent.trim(),
          source_excerpt: excerpt.trim(),
          operator_ack: ack,
          focus_questions: focus.trim() ? [focus.trim()] : null,
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div data-testid="recursive-twin-note-taker-panel">
      <LemonCard
        title="Recursive twin note-taker"
        className="recursive-twin-note-taker-panel"
      >
        <p className="text-sm opacity-80" data-testid="rtnt-blurb">
          Propose a twin of insights/questions for any information asset.
          Pure — twin_written, prompts_injected, live_dispatch_authorized stay
          false (no invent insights).
        </p>
        <div className="flex flex-col gap-2 mt-3">
          <label className="text-sm flex flex-col gap-1">
            <span>Parent asset id</span>
            <LemonInput
              value={parent}
              onChange={(e) => setParent(e.target.value)}
              data-testid="rtnt-parent"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Source excerpt</span>
            <textarea
              value={excerpt}
              onChange={(e) => setExcerpt(e.target.value)}
              data-testid="rtnt-excerpt"
              className="border border-border rounded px-2 py-1 text-sm min-h-[3rem]"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Focus question</span>
            <LemonInput
              value={focus}
              onChange={(e) => setFocus(e.target.value)}
              data-testid="rtnt-focus"
            />
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={ack}
              onChange={(e) => setAck(e.target.checked)}
              data-testid="rtnt-ack"
            />
            <span>operator_ack</span>
          </label>
          <LemonButton
            variant="primary"
            onClick={onCompose}
            data-testid="rtnt-compose"
          >
            Propose twin note-taker pack
          </LemonButton>
          {error ? (
            <p className="text-sm text-danger" data-testid="rtnt-error">
              {error}
            </p>
          ) : null}
          {result ? (
            <div
              className="text-sm flex flex-col gap-1 mt-2"
              data-testid="rtnt-result"
            >
              <div data-testid="rtnt-ready">
                twin_propose_ready={String(result.twin_propose_ready)}
              </div>
              <div data-testid="rtnt-written">
                twin_written={String(result.twin_written)}
              </div>
              <div data-testid="rtnt-prompts">
                prompts_injected={String(result.prompts_injected)}
              </div>
              <div data-testid="rtnt-live">
                live_dispatch_authorized=
                {String(result.live_dispatch_authorized)}
              </div>
              <div data-testid="rtnt-summary">
                {formatRecursiveTwinNoteTakerSummary(result)}
              </div>
            </div>
          ) : null}
        </div>
      </LemonCard>
    </div>
  );
}
