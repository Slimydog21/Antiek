/**
 * TwinSearchPanel — search recursive twin insight/question substrate.
 *
 * Uses searchTwins (#842). Free-file engagement panel; never invents hits.
 */

import { useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../lemon";
import {
  searchTwins,
  type TwinSearchResponse,
} from "../../api/twinSearch";

export interface TwinSearchPanelProps {
  searchFn?: typeof searchTwins;
  initialQuery?: string;
  initialParentId?: string;
}

export default function TwinSearchPanel({
  searchFn = searchTwins,
  initialQuery = "",
  initialParentId = "",
}: TwinSearchPanelProps) {
  const [q, setQ] = useState(initialQuery);
  const [parentId, setParentId] = useState(initialParentId);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<TwinSearchResponse | null>(null);

  async function onSearch() {
    setBusy(true);
    setError(null);
    try {
      const body = await searchFn({
        q,
        parent_asset_id: parentId.trim() ? parentId.trim() : null,
      });
      setResult(body);
    } catch (e) {
      setResult(null);
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div data-testid="twin-search-panel">
      <LemonCard title="Twin notes search" className="twin-search-panel">
        <p className="text-sm opacity-80" data-testid="twin-search-blurb">
          Search LLM twin insights and questions across your information
          assets. Empty queries fail closed — hits are never invented.
        </p>
        <div className="flex flex-col gap-3 mt-3">
          <label className="text-sm flex flex-col gap-1">
            <span>Query</span>
            <LemonInput
              value={q}
              onChange={(e) => {
                setQ(e.target.value);
                setResult(null);
                setError(null);
              }}
              data-testid="twin-search-q"
              aria-label="Twin search query"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Parent asset id (optional filter)</span>
            <LemonInput
              value={parentId}
              onChange={(e) => {
                setParentId(e.target.value);
                setResult(null);
                setError(null);
              }}
              data-testid="twin-search-parent"
              aria-label="Parent asset id"
            />
          </label>
          <LemonButton
            variant="primary"
            disabled={busy}
            onClick={() => void onSearch()}
            data-testid="twin-search-run"
          >
            {busy ? "Searching…" : "Search twins"}
          </LemonButton>
          {error ? (
            <div className="text-sm text-danger" data-testid="twin-search-error">
              {error}
            </div>
          ) : null}
          {result ? (
            <div data-testid="twin-search-result" className="flex flex-col gap-2">
              <div data-testid="twin-search-count">
                {result.count} hit{result.count === 1 ? "" : "s"} for “
                {result.query}”
              </div>
              {result.hits.length === 0 ? (
                <div data-testid="twin-search-empty">No twins matched.</div>
              ) : (
                <ul data-testid="twin-search-hits">
                  {result.hits.map((h) => (
                    <li
                      key={h.twin_id}
                      data-testid={`twin-search-hit-${h.twin_id}`}
                    >
                      {h.twin_id} (parent={h.parent_asset_id}, score={h.score})
                      {h.matched_insights.length
                        ? ` — insights: ${h.matched_insights.join("; ")}`
                        : ""}
                      {h.matched_questions.length
                        ? ` — questions: ${h.matched_questions.join("; ")}`
                        : ""}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ) : null}
        </div>
      </LemonCard>
    </div>
  );
}
