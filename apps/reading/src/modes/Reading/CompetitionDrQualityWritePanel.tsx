/**
 * CompetitionDrQualityWritePanel — free-file.
 */

import { useState } from "react";
import { LemonButton, LemonCard } from "../../components/lemon";
import {
  composeCompetitionDrQualityWrite,
  formatCompetitionDrQualityWriteSummary,
  type CompetitionDrQualityWriteCompose,
} from "../../api/competitionDrQualityWriteCompose";

export default function CompetitionDrQualityWritePanel() {
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<CompetitionDrQualityWriteCompose | null>(null);

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      setResult(
        composeCompetitionDrQualityWrite({
          session_id: "sess-demo",
          draft_id: "draft-demo",
          parent_asset_id: "asset-demo",
          competitor_decisions: [
            {
              competitor: "Perplexity",
              area: "citation_grounding",
              decision_summary: "Inline citations with source cards",
              antiek_status: "parity",
            },
            {
              competitor: "OpenAI DR",
              area: "multi_agent_orchestration",
              decision_summary: "Planner + browser agents",
              antiek_status: "behind",
              residual: "strengthen collective floating cohesive pack",
            },
          ],
          requested_families: ["arxiv", "substack"],
          citations: [
            {
              citation_id: "c1",
              family: "arxiv",
              title: "Scaling Laws under Noise",
              external_id: "arxiv:2301.00001",
            },
            {
              citation_id: "c2",
              family: "substack",
              title: "Research notes on evals",
              url: "https://example.substack.com/p/evals",
            },
          ],
          quality_overall: 0.8,
          quality_floor: 0.5,
          would_exceed: false,
          operator_ack: ack,
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div data-testid="competition-dr-quality-write-panel">
      <LemonCard title="Research · competition quality → write">
        <p className="text-sm opacity-80">
          Competition-aware DR quality + citations fold into write draft.
          Pure — no live dispatch or invent competitor facts.
        </p>
        <label className="text-sm flex items-center gap-2 mt-2">
          <input
            type="checkbox"
            checked={ack}
            onChange={(e) => setAck(e.target.checked)}
            data-testid="cqw-ack"
          />
          operator_ack
        </label>
        <LemonButton
          type="primary"
          onClick={onCompose}
          className="mt-2"
          data-testid="cqw-compose"
        >
          Compose competition → write
        </LemonButton>
        {error && <p className="text-sm text-danger mt-2">{error}</p>}
        {result && (
          <div className="mt-3 text-sm" data-testid="cqw-result">
            <p>{formatCompetitionDrQualityWriteSummary(result)}</p>
            <ul className="list-disc pl-5">
              <li>pack_ready={String(result.pack_ready)}</li>
              <li>
                behind={result.quality_source.competition.behind_count}
              </li>
              <li>draft_written={String(result.draft_written)}</li>
            </ul>
          </div>
        )}
      </LemonCard>
    </div>
  );
}
