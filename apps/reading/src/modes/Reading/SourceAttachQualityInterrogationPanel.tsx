/**
 * SourceAttachQualityInterrogationPanel — arxiv/substack + chase loop.
 *
 * Free-file. remote_fetched/pdf/dispatch always false.
 */

import { useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../../components/lemon";
import {
  composeSourceAttachQualityInterrogation,
  formatSourceAttachQualityInterrogationSummary,
  type SourceAttachQualityInterrogationCompose,
} from "../../api/sourceAttachQualityInterrogationCompose";

export interface SourceAttachQualityInterrogationPanelProps {
  composeFn?: typeof composeSourceAttachQualityInterrogation;
}

export default function SourceAttachQualityInterrogationPanel({
  composeFn = composeSourceAttachQualityInterrogation,
}: SourceAttachQualityInterrogationPanelProps) {
  const [prompt, setPrompt] = useState(
    "Chase questions with arxiv/substack attached",
  );
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<SourceAttachQualityInterrogationCompose | null>(null);

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      setResult(
        composeFn({
          session_id: "sess-demo",
          parent_asset_id: "asset-demo",
          requested_families: ["arxiv", "substack"],
          sources: [
            {
              source_id: "arx-demo",
              family: "arxiv",
              title: "Demo arXiv paper",
              external_id: "arxiv:2001.08361",
              html_fragment: "<article>HTML projection</article>",
            },
            {
              source_id: "sub-demo",
              family: "substack",
              title: "Demo Substack essay",
              html_fragment: "<article>essay body</article>",
            },
          ],
          quality_overall: 0.85,
          quality_floor: 0.7,
          would_exceed: false,
          questions: [
            {
              question_id: "q1",
              body: "How do these sources ground multi-hop claims?",
              priority: 2,
            },
            {
              question_id: "q2",
              body: "Where do they disagree?",
              priority: 1,
            },
          ],
          chase_mode: "swarm_fanout",
          user_prompt: prompt.trim() || "Chase with sources",
          selected_model_id: "gpt-5.5",
          models: [
            { model_id: "gpt-5.5", projected_cost_usd_high: 0.4 },
            { model_id: "grok-4.5", projected_cost_usd_high: 0.2 },
          ],
          daily_cap_usd: 30,
          spent_usd: 3,
          projected_cost_usd_high: 0.4,
          operator_ack: ack,
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div data-testid="source-attach-quality-interrogation-panel">
      <LemonCard
        title="Research · arXiv/Substack attach + interrogation"
        className="source-attach-quality-interrogation-panel"
      >
        <p className="text-sm opacity-80" data-testid="saqi-blurb">
          Attach knowledge-dense HTML sources with quality/budget gate, then
          chase questions in the workstation. Pure — never scrapes or
          dispatches.
        </p>
        <div className="flex flex-col gap-2 mt-3">
          <label className="text-sm flex flex-col gap-1">
            <span>User prompt</span>
            <LemonInput
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              data-testid="saqi-prompt"
            />
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={ack}
              onChange={(e) => setAck(e.target.checked)}
              data-testid="saqi-ack"
            />
            <span>operator_ack</span>
          </label>
          <LemonButton
            type="primary"
            onClick={onCompose}
            data-testid="saqi-compose"
          >
            Compose source + interrogation
          </LemonButton>
        </div>
        {error && (
          <p className="text-sm text-danger mt-2" data-testid="saqi-error">
            {error}
          </p>
        )}
        {result && (
          <div className="mt-3 text-sm" data-testid="saqi-result">
            <p data-testid="saqi-summary">
              {formatSourceAttachQualityInterrogationSummary(result)}
            </p>
            <ul className="list-disc pl-5 mt-1 opacity-80">
              <li>pack_ready={String(result.pack_ready)}</li>
              <li>
                source_ready={String(result.source_quality.pack_ready)}
              </li>
              <li>
                loop_ready={String(result.interrogation.loop_ready)}
              </li>
              <li>remote_fetched={String(result.remote_fetched)}</li>
              <li>live_dispatched={String(result.live_dispatched)}</li>
            </ul>
          </div>
        )}
      </LemonCard>
    </div>
  );
}
