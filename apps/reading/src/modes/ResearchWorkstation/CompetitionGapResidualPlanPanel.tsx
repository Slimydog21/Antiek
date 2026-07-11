/**
 * CompetitionGapResidualPlanPanel - gap matrix → ordered residual plan.
 *
 * Free-file. Never mutates product backlog; backlog_mutated always false.
 */

import { useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../../components/lemon";
import {
  buildCompetitionGapResidualPlan,
  formatCompetitionGapResidualPlanSummary,
  type CompetitionGapResidualPlan,
} from "../../api/competitionGapResidualPlan";
import type {
  CompetitorDecision,
  DecisionArea,
  GapStatus,
} from "../../api/competitionDeepResearchGap";

export interface CompetitionGapResidualPlanPanelProps {
  buildFn?: typeof buildCompetitionGapResidualPlan;
}

const DEFAULT_JSON = JSON.stringify(
  [
    {
      competitor: "Elicit",
      area: "citation_grounding",
      decision_summary: "Paper-grounded claims with spans",
      antiek_status: "behind",
      residual: "Wire citation spans into DR quality floor",
    },
    {
      competitor: "Consensus",
      area: "evaluation_harness",
      decision_summary: "Literature meta-analysis UX",
      antiek_status: "unknown",
    },
  ],
  null,
  2,
);

export default function CompetitionGapResidualPlanPanel({
  buildFn = buildCompetitionGapResidualPlan,
}: CompetitionGapResidualPlanPanelProps) {
  const [jsonRaw, setJsonRaw] = useState(DEFAULT_JSON);
  const [maxRaw, setMaxRaw] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<CompetitionGapResidualPlan | null>(null);

  function onBuild() {
    setError(null);
    setResult(null);
    try {
      const parsed = JSON.parse(jsonRaw) as CompetitorDecision[];
      if (!Array.isArray(parsed)) {
        throw new Error("decisions JSON must be an array");
      }
      const maxTrim = maxRaw.trim();
      const max_items = maxTrim ? Number(maxTrim) : null;
      setResult(
        buildFn({
          decisions: parsed.map((d) => ({
            competitor: d.competitor,
            area: d.area as DecisionArea,
            decision_summary: d.decision_summary,
            antiek_status: d.antiek_status as GapStatus,
            residual: d.residual,
          })),
          max_items,
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div data-testid="competition-gap-residual-plan-panel">
      <LemonCard
        title="Competition gap → residual plan"
        className="competition-gap-residual-plan-panel"
      >
        <p className="text-sm opacity-80" data-testid="cgrp-blurb">
          Turn operator-supplied competition gap decisions into an ordered
          residual plan for future agents. Pure advisory —
          backlog_mutated stays false.
        </p>
        <div className="flex flex-col gap-3 mt-3">
          <label className="text-sm flex flex-col gap-1">
            <span>Decisions JSON array</span>
            <textarea
              value={jsonRaw}
              onChange={(e) => setJsonRaw(e.target.value)}
              data-testid="cgrp-json"
              className="border border-border rounded px-2 py-1 text-sm min-h-[10rem] font-mono"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>max_items (blank = all)</span>
            <LemonInput
              value={maxRaw}
              onChange={(e) => setMaxRaw(e.target.value)}
              data-testid="cgrp-max"
            />
          </label>
          <LemonButton
            variant="primary"
            onClick={onBuild}
            data-testid="cgrp-build"
          >
            Build residual plan
          </LemonButton>
          {error ? (
            <div className="text-sm text-danger" data-testid="cgrp-error">
              {error}
            </div>
          ) : null}
          {result ? (
            <div
              data-testid="cgrp-result"
              className="text-sm flex flex-col gap-1"
            >
              <div data-testid="cgrp-summary">
                {formatCompetitionGapResidualPlanSummary(result)}
              </div>
              <div data-testid="cgrp-mutated">
                backlog_mutated={String(result.backlog_mutated)}
              </div>
              <ol data-testid="cgrp-items" className="list-decimal pl-5">
                {result.items.map((it) => (
                  <li key={it.residual_id} data-testid={`cgrp-item-${it.residual_id}`}>
                    [{it.priority}] {it.residual_text}
                  </li>
                ))}
              </ol>
            </div>
          ) : null}
        </div>
      </LemonCard>
    </div>
  );
}
