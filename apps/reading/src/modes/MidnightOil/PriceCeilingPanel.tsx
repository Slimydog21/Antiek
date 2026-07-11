/**
 * PriceCeilingPanel — recommend MO unattended budget ceiling for approval.
 *
 * Uses pure recommendPriceCeiling (#827). Advisory only — never spends.
 * Free-file: does not own MidnightOil/index.tsx.
 */

import { useMemo, useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../../components/lemon";
import {
  formatCeilingUsd,
  recommendPriceCeiling,
  type PriceCeilingRecommendation,
} from "../../api/priceCeiling";

export interface PriceCeilingPanelProps {
  recommendFn?: typeof recommendPriceCeiling;
  initialHours?: number;
  initialGoals?: string;
}

export default function PriceCeilingPanel({
  recommendFn = recommendPriceCeiling,
  initialHours = 2,
  initialGoals = "goal-1\ngoal-2",
}: PriceCeilingPanelProps) {
  const [hoursRaw, setHoursRaw] = useState(String(initialHours));
  const [goalsRaw, setGoalsRaw] = useState(initialGoals);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<PriceCeilingRecommendation | null>(null);

  const goals = useMemo(
    () =>
      goalsRaw
        .split(/\n|,/)
        .map((s) => s.trim())
        .filter(Boolean),
    [goalsRaw],
  );

  function onRecommend() {
    setError(null);
    try {
      const hours = Number(hoursRaw);
      const body = recommendFn({ hours, goals });
      setResult(body);
    } catch (e) {
      setResult(null);
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div data-testid="price-ceiling-panel">
      <LemonCard title="Midnight Oil price ceiling" className="price-ceiling-panel">
        <p className="text-sm opacity-80" data-testid="price-ceiling-blurb">
          Set planned hours and goals to get a recommended USD ceiling for
          operator approval. Advisory only — does not reserve or spend.
        </p>
        <div className="flex flex-col gap-3 mt-3">
          <label className="text-sm flex flex-col gap-1">
            <span>Hours of unattended work</span>
            <LemonInput
              value={hoursRaw}
              onChange={(e) => setHoursRaw(e.target.value)}
              data-testid="price-ceiling-hours"
              aria-label="Hours"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Goals (one per line or comma-separated)</span>
            <textarea
              className="min-h-[80px] w-full rounded border border-border bg-bg-light px-2 py-1 text-sm"
              value={goalsRaw}
              onChange={(e) => setGoalsRaw(e.target.value)}
              data-testid="price-ceiling-goals"
              aria-label="Goals"
            />
          </label>
          <LemonButton
            variant="primary"
            onClick={onRecommend}
            data-testid="price-ceiling-recommend"
          >
            Recommend ceiling
          </LemonButton>
          {error ? (
            <div className="text-sm text-danger" data-testid="price-ceiling-error">
              {error}
            </div>
          ) : null}
          {result ? (
            <div data-testid="price-ceiling-result" className="flex flex-col gap-1">
              <div data-testid="price-ceiling-authority">
                Authority: {result.authority} (proposal only)
              </div>
              <div data-testid="price-ceiling-recommended">
                Recommended: {formatCeilingUsd(result.recommended_ceiling_usd)}
              </div>
              <div data-testid="price-ceiling-range">
                Range: {formatCeilingUsd(result.low_usd)} –{" "}
                {formatCeilingUsd(result.high_usd)}
              </div>
              <div data-testid="price-ceiling-meta">
                Hours={result.hours}; goals={result.goal_count}
              </div>
            </div>
          ) : null}
        </div>
      </LemonCard>
    </div>
  );
}
