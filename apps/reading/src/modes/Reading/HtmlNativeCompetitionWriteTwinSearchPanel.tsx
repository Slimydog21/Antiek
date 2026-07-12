/**
 * HtmlNativeCompetitionWriteTwinSearchPanel — free-file.
 */

import { useState } from "react";
import { LemonButton, LemonCard } from "../../components/lemon";
import {
  composeHtmlNativeCompetitionWriteTwinSearch,
  formatHtmlNativeCompetitionWriteTwinSearchSummary,
  type HtmlNativeCompetitionWriteTwinSearchCompose,
} from "../../api/htmlNativeCompetitionWriteTwinSearchCompose";

export default function HtmlNativeCompetitionWriteTwinSearchPanel() {
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<HtmlNativeCompetitionWriteTwinSearchCompose | null>(null);

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      setResult(
        composeHtmlNativeCompetitionWriteTwinSearch({
          session_id: "sess-demo",
          asset_id: "asset-demo",
          html_projection_sha: "sha-html-demo",
          view_requested: true,
          twin_bound: true,
          twin_substrate_ready: true,
          claimed_format: "html",
          operator_ack: ack,
          competition: {
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
            search_query: "scaling orchestration citations",
          },
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div data-testid="html-native-competition-write-twin-search-panel">
      <LemonCard title="Research · HTML-native competition write → twin search">
        <p className="text-sm opacity-80">
          Competition quality → write → twin search, viewable only as HTML.
          Pure — no PDF primary, no live dispatch.
        </p>
        <label className="text-sm flex items-center gap-2 mt-2">
          <input
            type="checkbox"
            checked={ack}
            onChange={(e) => setAck(e.target.checked)}
            data-testid="hncwts-ack"
          />
          operator_ack
        </label>
        <LemonButton
          type="primary"
          onClick={onCompose}
          className="mt-2"
          data-testid="hncwts-compose"
        >
          Compose HTML-native competition pack
        </LemonButton>
        {error && <p className="text-sm text-danger mt-2">{error}</p>}
        {result && (
          <div className="mt-3 text-sm" data-testid="hncwts-result">
            <p>{formatHtmlNativeCompetitionWriteTwinSearchSummary(result)}</p>
            <ul className="list-disc pl-5">
              <li>pack_ready={String(result.pack_ready)}</li>
              <li>pdf_view_authorized={String(result.pdf_view_authorized)}</li>
              <li>hits={result.competition_pack.twin_search.search.hits.length}</li>
              <li>twin_written={String(result.twin_written)}</li>
            </ul>
          </div>
        )}
      </LemonCard>
    </div>
  );
}
