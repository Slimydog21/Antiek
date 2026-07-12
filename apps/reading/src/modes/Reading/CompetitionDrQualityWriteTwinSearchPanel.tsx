/**
 * CompetitionDrQualityWriteTwinSearchPanel — free-file.
 */

import { useState } from "react";
import { LemonButton, LemonCard } from "../../components/lemon";
import {
  composeCompetitionDrQualityWriteTwinSearch,
  formatCompetitionDrQualityWriteTwinSearchSummary,
  type CompetitionDrQualityWriteTwinSearchCompose,
} from "../../api/competitionDrQualityWriteTwinSearchCompose";

export default function CompetitionDrQualityWriteTwinSearchPanel() {
  const [ack, setAck] = useState(true);
  const [query, setQuery] = useState("scaling orchestration citations");
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<CompetitionDrQualityWriteTwinSearchCompose | null>(null);

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      setResult(
        composeCompetitionDrQualityWriteTwinSearch({
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
          search_query: query,
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div data-testid="competition-dr-quality-write-twin-search-panel">
      <LemonCard title="Research · competition quality → write → twin search">
        <p className="text-sm opacity-80">
          Competition-aware DR quality + write pack, then intelligent twin
          search/merge over derived note substrate. Pure — no live dispatch or
          remote index.
        </p>
        <label className="text-sm flex flex-col gap-1 mt-2">
          search_query
          <input
            className="border px-2 py-1 rounded text-sm"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            data-testid="cqwts-query"
          />
        </label>
        <label className="text-sm flex items-center gap-2 mt-2">
          <input
            type="checkbox"
            checked={ack}
            onChange={(e) => setAck(e.target.checked)}
            data-testid="cqwts-ack"
          />
          operator_ack
        </label>
        <LemonButton
          type="primary"
          onClick={onCompose}
          className="mt-2"
          data-testid="cqwts-compose"
        >
          Compose competition → write → twin search
        </LemonButton>
        {error && <p className="text-sm text-danger mt-2">{error}</p>}
        {result && (
          <div className="mt-3 text-sm" data-testid="cqwts-result">
            <p>{formatCompetitionDrQualityWriteTwinSearchSummary(result)}</p>
            <ul className="list-disc pl-5">
              <li>pack_ready={String(result.pack_ready)}</li>
              <li>hits={result.twin_search.search.hits.length}</li>
              <li>corpus={result.twin_corpus.length}</li>
              <li>twin_written={String(result.twin_written)}</li>
              <li>remote_index_queried={String(result.remote_index_queried)}</li>
            </ul>
          </div>
        )}
      </LemonCard>
    </div>
  );
}
