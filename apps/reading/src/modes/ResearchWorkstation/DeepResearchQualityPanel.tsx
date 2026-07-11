/**
 * DeepResearchQualityPanel - score deep research on quality dimensions.
 *
 * Free-file. Caller-supplied scores only; never invents quality from text.
 */

import { useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../../components/lemon";
import {
  evaluateDeepResearchQuality,
  formatQualitySummary,
  QUALITY_DIMENSIONS,
  type DeepResearchQualityReport,
  type QualityDimensionId,
} from "../../api/deepResearchQualityRubric";

export interface DeepResearchQualityPanelProps {
  evaluateFn?: typeof evaluateDeepResearchQuality;
  initialResearchId?: string;
}

export default function DeepResearchQualityPanel({
  evaluateFn = evaluateDeepResearchQuality,
  initialResearchId = "",
}: DeepResearchQualityPanelProps) {
  const [researchId, setResearchId] = useState(initialResearchId);
  const [requireAll, setRequireAll] = useState(false);
  const [scores, setScores] = useState<Record<QualityDimensionId, string>>(
    () => {
      const init = {} as Record<QualityDimensionId, string>;
      for (const d of QUALITY_DIMENSIONS) init[d] = "";
      return init;
    },
  );
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<DeepResearchQualityReport | null>(null);

  function setScore(dim: QualityDimensionId, raw: string) {
    setScores((prev) => ({ ...prev, [dim]: raw }));
  }

  function onEvaluate() {
    setError(null);
    setResult(null);
    try {
      const dimensions = QUALITY_DIMENSIONS.map((dimension) => {
        const raw = scores[dimension].trim();
        if (!raw) {
          return { dimension, score: null as number | null };
        }
        const n = Number(raw);
        if (!Number.isFinite(n)) {
          throw new Error(`${dimension} must be finite or blank`);
        }
        return { dimension, score: n };
      });
      setResult(
        evaluateFn({
          research_id: researchId.trim(),
          dimensions,
          require_all_dimensions: requireAll,
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div data-testid="deep-research-quality-panel">
      <LemonCard
        title="Deep research quality rubric"
        className="deep-research-quality-panel"
      >
        <p className="text-sm opacity-80" data-testid="drq-blurb">
          Score deep research on hard-to-vary dimensions (citations, grounding,
          honesty, questions). Scores are operator-supplied only — never invented
          from free text. overall=null when unknown.
        </p>
        <div className="flex flex-col gap-3 mt-3">
          <label className="text-sm flex flex-col gap-1">
            <span>Research id</span>
            <LemonInput
              value={researchId}
              onChange={(e) => setResearchId(e.target.value)}
              data-testid="drq-id"
            />
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={requireAll}
              onChange={(e) => setRequireAll(e.target.checked)}
              data-testid="drq-require-all"
            />
            require all dimensions for overall
          </label>
          <div className="flex flex-col gap-2" data-testid="drq-dimensions">
            {QUALITY_DIMENSIONS.map((dim) => (
              <label key={dim} className="text-sm flex flex-col gap-1">
                <span>{dim} (0–1, blank = unknown)</span>
                <LemonInput
                  value={scores[dim]}
                  onChange={(e) => setScore(dim, e.target.value)}
                  data-testid={`drq-score-${dim}`}
                />
              </label>
            ))}
          </div>
          <LemonButton
            variant="primary"
            onClick={onEvaluate}
            data-testid="drq-run"
          >
            Evaluate quality
          </LemonButton>
          {error ? (
            <div className="text-sm text-danger" data-testid="drq-error">
              {error}
            </div>
          ) : null}
          {result ? (
            <div data-testid="drq-result" className="text-sm flex flex-col gap-1">
              <div data-testid="drq-summary">{formatQualitySummary(result)}</div>
              <div data-testid="drq-overall">
                overall=
                {result.overall === null ? "null" : String(result.overall)}
              </div>
              <div data-testid="drq-persisted">
                persisted={String(result.persisted)}
              </div>
            </div>
          ) : null}
        </div>
      </LemonCard>
    </div>
  );
}
