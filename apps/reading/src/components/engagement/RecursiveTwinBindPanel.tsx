/**
 * RecursiveTwinBindPanel — propose twin bind for any information asset.
 *
 * Free-file. Never invents insights/questions; never creates twin store rows.
 */

import { useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../lemon";
import {
  evaluateRecursiveTwinBind,
  formatTwinBindSummary,
  type RecursiveTwinBindDecision,
  type TwinBindSource,
} from "../../api/recursiveTwinBind";

export interface RecursiveTwinBindPanelProps {
  gated: boolean;
  initialParentAssetId?: string;
  evaluateFn?: typeof evaluateRecursiveTwinBind;
}

export default function RecursiveTwinBindPanel({
  gated,
  initialParentAssetId = "",
  evaluateFn = evaluateRecursiveTwinBind,
}: RecursiveTwinBindPanelProps) {
  const [parent, setParent] = useState(initialParentAssetId);
  const [twinId, setTwinId] = useState("");
  const [insightsRaw, setInsightsRaw] = useState("");
  const [questionsRaw, setQuestionsRaw] = useState("");
  const [source, setSource] = useState<TwinBindSource>("operator");
  const [llmFilled, setLlmFilled] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<RecursiveTwinBindDecision | null>(null);

  function onEvaluate() {
    setError(null);
    setResult(null);
    try {
      if (typeof gated !== "boolean") {
        throw new Error(
          "gated must be an explicit boolean from asset provenance (fail closed)",
        );
      }
      const insights = insightsRaw
        .split(/\r?\n/)
        .map((s) => s.trim())
        .filter(Boolean);
      const questions = questionsRaw
        .split(/\r?\n/)
        .map((s) => s.trim())
        .filter(Boolean);
      const decision = evaluateFn({
        parent_asset_id: parent.trim(),
        twin_id: twinId.trim() || null,
        insights,
        questions,
        source,
        llm_filled: llmFilled,
        gated,
      });
      setResult(decision);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div data-testid="recursive-twin-bind-panel">
      <LemonCard
        title="Recursive twin bind"
        className="recursive-twin-bind-panel"
      >
        <p className="text-sm opacity-80" data-testid="rtb-blurb">
          Every information asset can carry a twin of insights and questions.
          This panel proposes a bind decision only — never invents notes from
          asset text, never writes the twin store (twin_created=false).
        </p>
        <div className="flex flex-col gap-3 mt-3">
          <label className="text-sm flex flex-col gap-1">
            <span>Parent asset id</span>
            <LemonInput
              value={parent}
              onChange={(e) => setParent(e.target.value)}
              data-testid="rtb-parent"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Existing twin id (optional)</span>
            <LemonInput
              value={twinId}
              onChange={(e) => setTwinId(e.target.value)}
              data-testid="rtb-twin"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Source</span>
            <select
              value={source}
              onChange={(e) => setSource(e.target.value as TwinBindSource)}
              data-testid="rtb-source"
              className="border border-border rounded px-2 py-1"
            >
              <option value="operator">operator</option>
              <option value="llm_note_taker">llm_note_taker</option>
              <option value="highlight_seed">highlight_seed</option>
              <option value="unknown">unknown</option>
            </select>
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={llmFilled}
              onChange={(e) => setLlmFilled(e.target.checked)}
              data-testid="rtb-llm-filled"
            />
            llm_filled (must match source)
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Insights (one per line)</span>
            <textarea
              value={insightsRaw}
              onChange={(e) => setInsightsRaw(e.target.value)}
              data-testid="rtb-insights"
              className="border border-border rounded px-2 py-1 text-sm min-h-[4rem]"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Questions (one per line)</span>
            <textarea
              value={questionsRaw}
              onChange={(e) => setQuestionsRaw(e.target.value)}
              data-testid="rtb-questions"
              className="border border-border rounded px-2 py-1 text-sm min-h-[4rem]"
            />
          </label>
          <LemonButton
            variant="primary"
            onClick={onEvaluate}
            data-testid="rtb-run"
          >
            Evaluate twin bind
          </LemonButton>
          {error ? (
            <div className="text-sm text-danger" data-testid="rtb-error">
              {error}
            </div>
          ) : null}
          {result ? (
            <div data-testid="rtb-result" className="text-sm flex flex-col gap-1">
              <div data-testid="rtb-summary">{formatTwinBindSummary(result)}</div>
              <div data-testid="rtb-bind-allowed">
                bind_allowed={String(result.bind_allowed)}
              </div>
              <div data-testid="rtb-twin-created">
                twin_created={String(result.twin_created)}
              </div>
            </div>
          ) : null}
        </div>
      </LemonCard>
    </div>
  );
}
