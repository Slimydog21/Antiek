/**
 * TwinSubstrateSearchMergePanel — search twins → propose cross-asset merge.
 *
 * Free-file. remote_index/merge/twin_written always false.
 */

import { useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../../components/lemon";
import {
  composeTwinSubstrateSearchMerge,
  formatTwinSubstrateSearchMergeSummary,
  type TwinSubstrateSearchMergeCompose,
} from "../../api/twinSubstrateSearchMergeCompose";

export interface TwinSubstrateSearchMergePanelProps {
  composeFn?: typeof composeTwinSubstrateSearchMerge;
}

export default function TwinSubstrateSearchMergePanel({
  composeFn = composeTwinSubstrateSearchMerge,
}: TwinSubstrateSearchMergePanelProps) {
  const [query, setQuery] = useState("scaling laws");
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<TwinSubstrateSearchMergeCompose | null>(null);

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      setResult(
        composeFn({
          pack_id: "pack-demo",
          search_query: query.trim() || "scaling",
          twin_records: [
            {
              twin_id: "twin-1",
              parent_asset_id: "asset-1",
              insights: ["scaling laws hold under compute-optimal regimes"],
              questions: ["Does the law break at sparse models?"],
            },
            {
              twin_id: "twin-2",
              parent_asset_id: "asset-2",
              insights: ["attention efficiency tradeoffs with scaling"],
              questions: ["What is the scaling frontier?"],
            },
          ],
          operator_ack: ack,
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div data-testid="twin-substrate-search-merge-panel">
      <LemonCard
        title="Research · twin search → cross-asset merge"
        className="twin-substrate-search-merge-panel"
      >
        <p className="text-sm opacity-80" data-testid="tssm-blurb">
          Search twin note substrate and propose merging insights/questions
          across assets. Pure — never writes twins or executes merges.
        </p>
        <div className="flex flex-col gap-2 mt-3">
          <label className="text-sm flex flex-col gap-1">
            <span>Search query</span>
            <LemonInput
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              data-testid="tssm-query"
            />
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={ack}
              onChange={(e) => setAck(e.target.checked)}
              data-testid="tssm-ack"
            />
            <span>operator_ack</span>
          </label>
          <LemonButton
            type="primary"
            onClick={onCompose}
            data-testid="tssm-compose"
          >
            Compose search + merge
          </LemonButton>
        </div>
        {error && (
          <p className="text-sm text-danger mt-2" data-testid="tssm-error">
            {error}
          </p>
        )}
        {result && (
          <div className="mt-3 text-sm" data-testid="tssm-result">
            <p data-testid="tssm-summary">
              {formatTwinSubstrateSearchMergeSummary(result)}
            </p>
            <ul className="list-disc pl-5 mt-1 opacity-80">
              <li>pack_ready={String(result.pack_ready)}</li>
              <li>hits={result.search.hits.length}</li>
              <li>
                merge_ready={String(result.merge?.merge_ready ?? false)}
              </li>
              <li>merge_executed={String(result.merge_executed)}</li>
              <li>twin_written={String(result.twin_written)}</li>
            </ul>
          </div>
        )}
      </LemonCard>
    </div>
  );
}
