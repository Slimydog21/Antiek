/**
 * MidnightOilSwarmBriefPanel - unattended swarm plan from time + goals.
 *
 * Free-file. Never authorizes live execution or charges.
 */

import { useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../../components/lemon";
import {
  buildMidnightOilSwarmBrief,
  formatSwarmBriefSummary,
  type MidnightOilSwarmBrief,
} from "../../api/midnightOilSwarmBrief";

export interface MidnightOilSwarmBriefPanelProps {
  initialOperatorId?: string;
  buildFn?: typeof buildMidnightOilSwarmBrief;
}

export default function MidnightOilSwarmBriefPanel({
  initialOperatorId = "",
  buildFn = buildMidnightOilSwarmBrief,
}: MidnightOilSwarmBriefPanelProps) {
  const [operatorId, setOperatorId] = useState(initialOperatorId);
  const [minutesRaw, setMinutesRaw] = useState("60");
  const [ceilingRaw, setCeilingRaw] = useState("");
  const [recommendedRaw, setRecommendedRaw] = useState("");
  const [goalsRaw, setGoalsRaw] = useState(
    "g1|Map arxiv scaling|2\ng2|Substack contrast|1",
  );
  const [approved, setApproved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<MidnightOilSwarmBrief | null>(null);

  function parseOptionalMoney(raw: string): number | null {
    const t = raw.trim();
    if (!t) return null;
    const n = Number(t);
    if (!Number.isFinite(n)) {
      throw new Error("money field must be finite or blank");
    }
    return n;
  }

  function onBuild() {
    setError(null);
    setResult(null);
    try {
      const goals = goalsRaw
        .split(/\r?\n/)
        .map((line) => line.trim())
        .filter(Boolean)
        .map((line, i) => {
          const parts = line.split("|").map((p) => p.trim());
          if (parts.length < 2) {
            throw new Error(
              `goals line ${i + 1} must be goal_id|statement|priority`,
            );
          }
          const priority = parts[2] ? Number(parts[2]) : 1;
          return {
            goal_id: parts[0],
            statement: parts[1],
            priority,
          };
        });
      const brief = buildFn({
        operator_id: operatorId.trim(),
        work_minutes: Number(minutesRaw),
        goals,
        price_ceiling_usd: parseOptionalMoney(ceilingRaw),
        recommended_ceiling_usd: parseOptionalMoney(recommendedRaw),
        operator_approved: approved,
      });
      setResult(brief);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div data-testid="mo-swarm-brief-panel">
      <LemonCard
        title="Midnight Oil swarm brief"
        className="mo-swarm-brief-panel"
      >
        <p className="text-sm opacity-80" data-testid="mo-swarm-blurb">
          Plan an unattended multi-goal research swarm: set work window, goals,
          and price ceiling. Pure brief only —
          live_execution_authorized stays false.
        </p>
        <div className="flex flex-col gap-3 mt-3">
          <label className="text-sm flex flex-col gap-1">
            <span>Operator id</span>
            <LemonInput
              value={operatorId}
              onChange={(e) => setOperatorId(e.target.value)}
              data-testid="mo-swarm-operator"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Work minutes</span>
            <LemonInput
              value={minutesRaw}
              onChange={(e) => setMinutesRaw(e.target.value)}
              data-testid="mo-swarm-minutes"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Price ceiling USD (blank = unknown)</span>
            <LemonInput
              value={ceilingRaw}
              onChange={(e) => setCeilingRaw(e.target.value)}
              data-testid="mo-swarm-ceiling"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Recommended ceiling USD (optional)</span>
            <LemonInput
              value={recommendedRaw}
              onChange={(e) => setRecommendedRaw(e.target.value)}
              data-testid="mo-swarm-recommended"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Goals (goal_id|statement|priority per line)</span>
            <textarea
              value={goalsRaw}
              onChange={(e) => setGoalsRaw(e.target.value)}
              data-testid="mo-swarm-goals"
              className="border border-border rounded px-2 py-1 text-sm min-h-[5rem]"
            />
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={approved}
              onChange={(e) => setApproved(e.target.checked)}
              data-testid="mo-swarm-approved"
            />
            operator_approved
          </label>
          <LemonButton
            variant="primary"
            onClick={onBuild}
            data-testid="mo-swarm-run"
          >
            Build swarm brief
          </LemonButton>
          {error ? (
            <div className="text-sm text-danger" data-testid="mo-swarm-error">
              {error}
            </div>
          ) : null}
          {result ? (
            <div
              data-testid="mo-swarm-result"
              className="text-sm flex flex-col gap-1"
            >
              <div data-testid="mo-swarm-summary">
                {formatSwarmBriefSummary(result)}
              </div>
              <div data-testid="mo-swarm-dispatch">
                dispatch_ready={String(result.dispatch_ready)}
              </div>
              <div data-testid="mo-swarm-live">
                live_execution_authorized=
                {String(result.live_execution_authorized)}
              </div>
            </div>
          ) : null}
        </div>
      </LemonCard>
    </div>
  );
}
