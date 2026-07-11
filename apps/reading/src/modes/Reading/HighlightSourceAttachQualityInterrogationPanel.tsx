/**
 * HighlightSourceAttachQualityInterrogationPanel — reading highlight → DR.
 *
 * Free-file. live_dispatched / remote_fetched always false.
 */

import { useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../../components/lemon";
import {
  composeHighlightSourceAttachQualityInterrogation,
  formatHighlightSourceAttachQualityInterrogationSummary,
  type HighlightSourceAttachQualityInterrogationCompose,
} from "../../api/highlightSourceAttachQualityInterrogationCompose";

export interface HighlightSourceAttachQualityInterrogationPanelProps {
  composeFn?: typeof composeHighlightSourceAttachQualityInterrogation;
}

export default function HighlightSourceAttachQualityInterrogationPanel({
  composeFn = composeHighlightSourceAttachQualityInterrogation,
}: HighlightSourceAttachQualityInterrogationPanelProps) {
  const [highlight, setHighlight] = useState(
    "power-law scaling of loss with compute",
  );
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<HighlightSourceAttachQualityInterrogationCompose | null>(null);

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      setResult(
        composeFn({
          parent_asset_id: "book-demo",
          highlight: highlight.trim() || "highlight",
          gated: false,
          preferred_view_mode: "floating",
          would_exceed: false,
          selected_model_id: "gpt-5.5",
          operator_ack: ack,
          session_id: "sess-demo",
          requested_families: ["arxiv", "substack"],
          sources: [
            {
              source_id: "arx-demo",
              family: "arxiv",
              title: "Demo arXiv paper",
              html_fragment: "<article>HTML</article>",
            },
            {
              source_id: "sub-demo",
              family: "substack",
              title: "Demo essay",
              html_fragment: "<article>essay</article>",
            },
          ],
          quality_overall: 0.85,
          quality_floor: 0.7,
          questions: [
            {
              question_id: "q1",
              body: "How does this highlight relate to the sources?",
              priority: 2,
            },
            {
              question_id: "q2",
              body: "What counter-evidence exists?",
              priority: 1,
            },
          ],
          chase_mode: "swarm_fanout",
          models: [
            { model_id: "gpt-5.5", projected_cost_usd_high: 0.4 },
            { model_id: "grok-4.5", projected_cost_usd_high: 0.2 },
          ],
          daily_cap_usd: 30,
          spent_usd: 3,
          projected_cost_usd_high: 0.4,
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div data-testid="highlight-source-attach-quality-interrogation-panel">
      <LemonCard
        title="Reading · highlight → sources + interrogation"
        className="highlight-source-attach-quality-interrogation-panel"
      >
        <p className="text-sm opacity-80" data-testid="hsaqi-blurb">
          From a highlight, package floating DR with arxiv/substack quality
          attach and chase. Pure — never dispatches or scrapes.
        </p>
        <div className="flex flex-col gap-2 mt-3">
          <label className="text-sm flex flex-col gap-1">
            <span>Highlight</span>
            <LemonInput
              value={highlight}
              onChange={(e) => setHighlight(e.target.value)}
              data-testid="hsaqi-highlight"
            />
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={ack}
              onChange={(e) => setAck(e.target.checked)}
              data-testid="hsaqi-ack"
            />
            <span>operator_ack</span>
          </label>
          <LemonButton
            type="primary"
            onClick={onCompose}
            data-testid="hsaqi-compose"
          >
            Compose highlight + sources
          </LemonButton>
        </div>
        {error && (
          <p className="text-sm text-danger mt-2" data-testid="hsaqi-error">
            {error}
          </p>
        )}
        {result && (
          <div className="mt-3 text-sm" data-testid="hsaqi-result">
            <p data-testid="hsaqi-summary">
              {formatHighlightSourceAttachQualityInterrogationSummary(result)}
            </p>
            <ul className="list-disc pl-5 mt-1 opacity-80">
              <li>pack_ready={String(result.pack_ready)}</li>
              <li>
                launch_ready={String(result.highlight_launch.launch_ready)}
              </li>
              <li>
                source_ready=
                {String(result.source_interrogation.pack_ready)}
              </li>
              <li>live_dispatched={String(result.live_dispatched)}</li>
              <li>remote_fetched={String(result.remote_fetched)}</li>
            </ul>
          </div>
        )}
      </LemonCard>
    </div>
  );
}
