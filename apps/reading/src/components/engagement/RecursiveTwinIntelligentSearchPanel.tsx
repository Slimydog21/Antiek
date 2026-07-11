/**
 * RecursiveTwinIntelligentSearchPanel - search twin insights/questions.
 *
 * Free-file. Pure term scan over operator-supplied records; no remote index.
 */

import { useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../lemon";
import {
  formatTwinSearchSummary,
  searchTwinSubstrate,
  type TwinSearchRecord,
  type TwinSearchResult,
} from "../../api/recursiveTwinIntelligentSearch";

const DEMO_CORPUS: TwinSearchRecord[] = [
  {
    twin_id: "demo-t1",
    parent_asset_id: "asset-1",
    insights: ["scaling laws hold under compute constraints"],
    questions: ["what is the counterexample?"],
    source_label: "arxiv",
  },
  {
    twin_id: "demo-t2",
    parent_asset_id: "asset-2",
    insights: ["market structure differs from pure scaling"],
    questions: ["how does regulation change the story?"],
  },
];

export interface RecursiveTwinIntelligentSearchPanelProps {
  searchFn?: typeof searchTwinSubstrate;
  records?: TwinSearchRecord[];
  initialQuery?: string;
}

export default function RecursiveTwinIntelligentSearchPanel({
  searchFn = searchTwinSubstrate,
  records = DEMO_CORPUS,
  initialQuery = "",
}: RecursiveTwinIntelligentSearchPanelProps) {
  const [query, setQuery] = useState(initialQuery);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<TwinSearchResult | null>(null);

  function onSearch() {
    setError(null);
    setResult(null);
    try {
      setResult(
        searchFn({
          query: query.trim(),
          records,
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div data-testid="recursive-twin-intelligent-search-panel">
      <LemonCard
        title="Twin substrate search"
        className="recursive-twin-intelligent-search-panel"
      >
        <p className="text-sm opacity-80" data-testid="rtis-blurb">
          Search insights and questions across twin notes. Pure term-overlap on
          supplied records — remote_index_queried stays false (no invent
          embeddings).
        </p>
        <div className="flex flex-col gap-3 mt-3">
          <label className="text-sm flex flex-col gap-1">
            <span>Query</span>
            <LemonInput
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              data-testid="rtis-query"
            />
          </label>
          <LemonButton
            variant="primary"
            onClick={onSearch}
            data-testid="rtis-run"
          >
            Search twins
          </LemonButton>
          {error ? (
            <div className="text-sm text-danger" data-testid="rtis-error">
              {error}
            </div>
          ) : null}
          {result ? (
            <div data-testid="rtis-result" className="text-sm flex flex-col gap-1">
              <div data-testid="rtis-summary">
                {formatTwinSearchSummary(result)}
              </div>
              <div data-testid="rtis-remote">
                remote_index_queried={String(result.remote_index_queried)}
              </div>
              <div data-testid="rtis-hit-count">hits={result.hits.length}</div>
              <ul data-testid="rtis-hits" className="list-disc pl-5">
                {result.hits.map((h) => (
                  <li key={h.twin_id} data-testid={`rtis-hit-${h.twin_id}`}>
                    {h.twin_id} · score={h.score} · {h.matched_fields.join(",")}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      </LemonCard>
    </div>
  );
}
