/**
 * RecursiveTwinSearchPromptContextPanel — twin search → prompt context.
 *
 * Free-file. twin_written/remote_index/prompts always false.
 */

import { useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../../components/lemon";
import {
  composeRecursiveTwinSearchPromptContext,
  formatRecursiveTwinSearchPromptContextSummary,
  type RecursiveTwinSearchPromptContextCompose,
} from "../../api/recursiveTwinSearchPromptContextCompose";

export interface RecursiveTwinSearchPromptContextPanelProps {
  composeFn?: typeof composeRecursiveTwinSearchPromptContext;
}

export default function RecursiveTwinSearchPromptContextPanel({
  composeFn = composeRecursiveTwinSearchPromptContext,
}: RecursiveTwinSearchPromptContextPanelProps) {
  const [query, setQuery] = useState("scaling laws");
  const [prompt, setPrompt] = useState("Use twin substrate for next step");
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<RecursiveTwinSearchPromptContextCompose | null>(null);

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      setResult(
        composeFn({
          session_id: "sess-demo",
          parent_asset_id: "asset-demo",
          source_excerpt: "Parent HTML about neural scaling laws.",
          focus_questions: ["What is the core claim?"],
          twin_records: [
            {
              twin_id: "twin-demo",
              parent_asset_id: "asset-demo",
              insights: ["scaling laws under compute-optimal regimes"],
              questions: ["Where do scaling laws break?"],
            },
          ],
          search_query: query.trim() || "scaling",
          user_prompt: prompt.trim() || "Continue",
          selected_model_id: "gpt-5.5",
          models: [
            { model_id: "gpt-5.5", projected_cost_usd_high: 0.4 },
            { model_id: "grok-4.5", projected_cost_usd_high: 0.2 },
          ],
          daily_cap_usd: 25,
          spent_usd: 2,
          projected_cost_usd_high: 0.4,
          operator_ack: ack,
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div data-testid="recursive-twin-search-prompt-context-panel">
      <LemonCard
        title="Research · twin search → prompt context"
        className="recursive-twin-search-prompt-context-panel"
      >
        <p className="text-sm opacity-80" data-testid="rtspc-blurb">
          Propose twin note-taker substrate, search insights/questions, and
          feed hits into prompt context with model budget projection. Pure —
          never writes twins or injects prompts.
        </p>
        <div className="flex flex-col gap-2 mt-3">
          <label className="text-sm flex flex-col gap-1">
            <span>Search query</span>
            <LemonInput
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              data-testid="rtspc-query"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>User prompt</span>
            <LemonInput
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              data-testid="rtspc-prompt"
            />
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={ack}
              onChange={(e) => setAck(e.target.checked)}
              data-testid="rtspc-ack"
            />
            <span>operator_ack</span>
          </label>
          <LemonButton
            type="primary"
            onClick={onCompose}
            data-testid="rtspc-compose"
          >
            Compose twin → search → prompt
          </LemonButton>
        </div>
        {error && (
          <p className="text-sm text-danger mt-2" data-testid="rtspc-error">
            {error}
          </p>
        )}
        {result && (
          <div className="mt-3 text-sm" data-testid="rtspc-result">
            <p data-testid="rtspc-summary">
              {formatRecursiveTwinSearchPromptContextSummary(result)}
            </p>
            <ul className="list-disc pl-5 mt-1 opacity-80">
              <li>pack_ready={String(result.pack_ready)}</li>
              <li>hits={result.search.hits.length}</li>
              <li>twin_written={String(result.twin_written)}</li>
              <li>
                remote_index_queried={String(result.remote_index_queried)}
              </li>
              <li>prompts_injected={String(result.prompts_injected)}</li>
            </ul>
          </div>
        )}
      </LemonCard>
    </div>
  );
}
