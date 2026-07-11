/**
 * HighlightSourceAttachQualityInterrogationTwinPanel — free-file.
 */

import { useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../../components/lemon";
import {
  composeHighlightSourceAttachQualityInterrogationTwin,
  formatHighlightSourceAttachQualityInterrogationTwinSummary,
  type HighlightSourceAttachQualityInterrogationTwinCompose,
} from "../../api/highlightSourceAttachQualityInterrogationTwinCompose";

export default function HighlightSourceAttachQualityInterrogationTwinPanel() {
  const [highlight, setHighlight] = useState("power-law scaling");
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<HighlightSourceAttachQualityInterrogationTwinCompose | null>(null);

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      setResult(
        composeHighlightSourceAttachQualityInterrogationTwin({
          parent_asset_id: "book-demo",
          highlight: highlight.trim() || "highlight",
          gated: false,
          would_exceed: false,
          selected_model_id: "gpt-5.5",
          operator_ack: ack,
          session_id: "sess-demo",
          requested_families: ["arxiv"],
          sources: [
            {
              source_id: "arx-demo",
              family: "arxiv",
              title: "Demo paper",
              html_fragment: "<article>HTML</article>",
            },
          ],
          quality_overall: 0.85,
          questions: [
            {
              question_id: "q1",
              body: "How does this relate?",
              priority: 1,
            },
          ],
          chase_mode: "single_question",
          models: [{ model_id: "gpt-5.5", projected_cost_usd_high: 0.4 }],
          daily_cap_usd: 20,
          spent_usd: 1,
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div data-testid="highlight-source-attach-quality-interrogation-twin-panel">
      <LemonCard title="Reading · highlight + sources → twin">
        <p className="text-sm opacity-80">
          Highlight DR with sources/interrogation feeding recursive twin. Pure.
        </p>
        <div className="flex flex-col gap-2 mt-3">
          <LemonInput
            value={highlight}
            onChange={(e) => setHighlight(e.target.value)}
            data-testid="hsaqit-highlight"
          />
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={ack}
              onChange={(e) => setAck(e.target.checked)}
              data-testid="hsaqit-ack"
            />
            operator_ack
          </label>
          <LemonButton type="primary" onClick={onCompose} data-testid="hsaqit-compose">
            Compose
          </LemonButton>
        </div>
        {error && <p className="text-sm text-danger mt-2">{error}</p>}
        {result && (
          <div className="mt-3 text-sm" data-testid="hsaqit-result">
            <p>{formatHighlightSourceAttachQualityInterrogationTwinSummary(result)}</p>
            <ul className="list-disc pl-5">
              <li>pack_ready={String(result.pack_ready)}</li>
              <li>twin_written={String(result.twin_written)}</li>
            </ul>
          </div>
        )}
      </LemonCard>
    </div>
  );
}
