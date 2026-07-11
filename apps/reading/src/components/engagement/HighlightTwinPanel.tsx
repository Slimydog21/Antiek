/**
 * HighlightTwinPanel — seed a twin from selected reading/research text.
 *
 * Free-file. No LLM dispatch. Gated highlights fail closed.
 */

import { useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../lemon";
import {
  parseHighlightTwinSeed,
  postHighlightTwinSeed,
  type HighlightTwinSeed,
} from "../../api/twinFromHighlight";

export interface HighlightTwinPanelProps {
  seedFn?: (
    req: Parameters<typeof postHighlightTwinSeed>[0],
  ) => Promise<HighlightTwinSeed | unknown>;
  initialParentAssetId?: string;
  initialHighlight?: string;
}

export default function HighlightTwinPanel({
  seedFn = postHighlightTwinSeed,
  initialParentAssetId = "",
  initialHighlight = "",
}: HighlightTwinPanelProps) {
  const [parent, setParent] = useState(initialParentAssetId);
  const [highlight, setHighlight] = useState(initialHighlight);
  const [insightsRaw, setInsightsRaw] = useState("");
  const [questionsRaw, setQuestionsRaw] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<HighlightTwinSeed | null>(null);

  async function onSeed() {
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const insights = insightsRaw
        .split(/\r?\n/)
        .map((s) => s.trim())
        .filter(Boolean);
      const questions = questionsRaw
        .split(/\r?\n/)
        .map((s) => s.trim())
        .filter(Boolean);
      const raw = await seedFn({
        parent_asset_id: parent.trim(),
        highlight: highlight.trim(),
        insights,
        questions,
      });
      setResult(parseHighlightTwinSeed(raw));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div data-testid="highlight-twin-panel">
      <LemonCard title="Twin from highlight" className="highlight-twin-panel">
        <p className="text-sm opacity-80" data-testid="highlight-twin-blurb">
          Seed a recursive twin note from selected text. Insights/questions are
          operator-supplied only — this panel does not call an LLM. Gated bodies
          are rejected.
        </p>
        <div className="flex flex-col gap-3 mt-3">
          <label className="text-sm flex flex-col gap-1">
            <span>Parent asset id</span>
            <LemonInput
              value={parent}
              onChange={(e) => setParent(e.target.value)}
              data-testid="highlight-twin-parent"
              disabled={busy}
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Highlight</span>
            <textarea
              className="min-h-[80px] w-full rounded border border-border bg-bg-light px-2 py-1 text-sm"
              value={highlight}
              onChange={(e) => setHighlight(e.target.value)}
              data-testid="highlight-twin-text"
              disabled={busy}
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Insights (optional, one per line)</span>
            <textarea
              className="min-h-[48px] w-full rounded border border-border bg-bg-light px-2 py-1 text-sm"
              value={insightsRaw}
              onChange={(e) => setInsightsRaw(e.target.value)}
              data-testid="highlight-twin-insights"
              disabled={busy}
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Questions (optional, one per line)</span>
            <textarea
              className="min-h-[48px] w-full rounded border border-border bg-bg-light px-2 py-1 text-sm"
              value={questionsRaw}
              onChange={(e) => setQuestionsRaw(e.target.value)}
              data-testid="highlight-twin-questions"
              disabled={busy}
            />
          </label>
          <LemonButton
            variant="primary"
            disabled={busy}
            onClick={() => void onSeed()}
            data-testid="highlight-twin-seed"
          >
            {busy ? "Seeding…" : "Seed twin"}
          </LemonButton>
          {error ? (
            <div className="text-sm text-danger" data-testid="highlight-twin-error">
              {error}
            </div>
          ) : null}
          {result ? (
            <div data-testid="highlight-twin-result" className="text-sm">
              <div data-testid="highlight-twin-authority">
                authority={result.authority}; llm_filled=
                {String(result.llm_filled)}
              </div>
              <div data-testid="highlight-twin-echo">{result.highlight}</div>
            </div>
          ) : null}
        </div>
      </LemonCard>
    </div>
  );
}
