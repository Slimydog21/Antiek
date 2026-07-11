/**
 * LlmNoteTakerPanel — inject LLM (or human) insights/questions into twin payload.
 *
 * Free-file. Does not call models. Gated assets fail closed.
 */

import { useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../lemon";
import {
  parseTwinNotePayload,
  postTwinNoteTakerPayload,
  type TwinNotePayload,
} from "../../api/twinLlmNoteTaker";

export interface LlmNoteTakerPanelProps {
  payloadFn?: (
    req: Parameters<typeof postTwinNoteTakerPayload>[0],
  ) => Promise<TwinNotePayload | unknown>;
  initialParentAssetId?: string;
  gated: boolean;
  initialLlmFilled?: boolean;
}

export default function LlmNoteTakerPanel({
  payloadFn = postTwinNoteTakerPayload,
  initialParentAssetId = "",
  gated,
  initialLlmFilled = true,
}: LlmNoteTakerPanelProps) {
  const [parent, setParent] = useState(initialParentAssetId);
  const [insightsRaw, setInsightsRaw] = useState("");
  const [questionsRaw, setQuestionsRaw] = useState("");
  const [llmFilled, setLlmFilled] = useState(initialLlmFilled);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<TwinNotePayload | null>(null);

  async function onBuild() {
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      if (typeof gated !== "boolean") {
        throw new Error("gated must be an explicit boolean");
      }
      if (typeof llmFilled !== "boolean") {
        throw new Error("llm_filled must be an explicit boolean");
      }
      const insights = insightsRaw
        .split(/\r?\n/)
        .map((s) => s.trim())
        .filter(Boolean);
      const questions = questionsRaw
        .split(/\r?\n/)
        .map((s) => s.trim())
        .filter(Boolean);
      const raw = await payloadFn({
        parent_asset_id: parent.trim(),
        insights,
        questions,
        llm_filled: llmFilled,
        gated,
      });
      setResult(parseTwinNotePayload(raw));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div data-testid="llm-note-taker-panel">
      <LemonCard title="Recursive LLM note-taker" className="llm-note-taker-panel">
        <p className="text-sm opacity-80" data-testid="llm-note-taker-blurb">
          Shape twin insights/questions produced by an LLM (or human) for an
          asset. This panel does not call models and will not invent notes from
          asset text.
        </p>
        <div className="flex flex-col gap-3 mt-3">
          <label className="text-sm flex flex-col gap-1">
            <span>Parent asset id</span>
            <LemonInput
              value={parent}
              onChange={(e) => setParent(e.target.value)}
              data-testid="lnt-parent"
              disabled={busy}
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Insights (one per line)</span>
            <textarea
              className="min-h-[64px] w-full rounded border border-border bg-bg-light px-2 py-1 text-sm"
              value={insightsRaw}
              onChange={(e) => setInsightsRaw(e.target.value)}
              data-testid="lnt-insights"
              disabled={busy}
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Questions (one per line)</span>
            <textarea
              className="min-h-[64px] w-full rounded border border-border bg-bg-light px-2 py-1 text-sm"
              value={questionsRaw}
              onChange={(e) => setQuestionsRaw(e.target.value)}
              data-testid="lnt-questions"
              disabled={busy}
            />
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={llmFilled}
              onChange={(e) => setLlmFilled(e.target.checked)}
              data-testid="lnt-llm-filled"
              disabled={busy}
            />
            llm_filled (assert lists came from LLM)
          </label>
          <div className="text-xs opacity-70" data-testid="lnt-gated">
            gated={String(gated)}
          </div>
          <LemonButton
            variant="primary"
            disabled={busy}
            onClick={() => void onBuild()}
            data-testid="lnt-build"
          >
            {busy ? "Building…" : "Build twin payload"}
          </LemonButton>
          {error ? (
            <div className="text-sm text-danger" data-testid="lnt-error">
              {error}
            </div>
          ) : null}
          {result ? (
            <div data-testid="lnt-result" className="text-sm">
              <div data-testid="lnt-model">
                model_invoked={String(result.model_invoked)}; llm_filled=
                {String(result.llm_filled)}
              </div>
              <div data-testid="lnt-counts">
                insights={result.insights.length}; questions=
                {result.questions.length}
              </div>
            </div>
          ) : null}
        </div>
      </LemonCard>
    </div>
  );
}
