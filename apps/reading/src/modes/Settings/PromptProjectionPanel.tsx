/**
 * PromptProjectionPanel - show how a proposed prompt affects budget remaining.
 *
 * Free-file under Settings/. Pure client math; no live meters.
 */

import { useMemo, useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../../components/lemon";
import {
  computeUsageBar,
  formatProjectionSummary,
  projectPromptAgainstBar,
  type PromptProjection,
  type UsageBarSnapshot,
} from "../../api/promptProjection";

export interface PromptProjectionPanelProps {
  /** Optional injected bar (tests); otherwise built from cap/spent fields. */
  bar?: UsageBarSnapshot | null;
  initialDailyCapUsd?: string;
  initialSpentUsd?: string;
  initialHighUsd?: string;
  initialLowUsd?: string;
  projectFn?: typeof projectPromptAgainstBar;
}

function parseOptionalNumber(raw: string): number | null {
  const t = raw.trim();
  if (!t) return null;
  const n = Number(t);
  if (!Number.isFinite(n)) {
    throw new Error("money field must be finite or blank");
  }
  return n;
}

export default function PromptProjectionPanel({
  bar = null,
  initialDailyCapUsd = "",
  initialSpentUsd = "",
  initialHighUsd = "",
  initialLowUsd = "",
  projectFn = projectPromptAgainstBar,
}: PromptProjectionPanelProps) {
  const [capRaw, setCapRaw] = useState(initialDailyCapUsd);
  const [spentRaw, setSpentRaw] = useState(initialSpentUsd);
  const [lowRaw, setLowRaw] = useState(initialLowUsd);
  const [highRaw, setHighRaw] = useState(initialHighUsd);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<PromptProjection | null>(null);

  const activeBar = useMemo(() => {
    if (bar) return bar;
    try {
      return computeUsageBar({
        daily_cap_usd: parseOptionalNumber(capRaw),
        spent_usd: parseOptionalNumber(spentRaw),
      });
    } catch {
      return null;
    }
  }, [bar, capRaw, spentRaw]);

  function onProject() {
    setError(null);
    setResult(null);
    try {
      const b =
        bar ??
        computeUsageBar({
          daily_cap_usd: parseOptionalNumber(capRaw),
          spent_usd: parseOptionalNumber(spentRaw),
        });
      const proj = projectFn(b, {
        projected_cost_usd_low: parseOptionalNumber(lowRaw),
        projected_cost_usd_high: parseOptionalNumber(highRaw),
      });
      setResult(proj);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div data-testid="prompt-projection-panel">
      <LemonCard title="Prompt budget projection" className="prompt-projection-panel">
        <p className="text-sm opacity-80" data-testid="prompt-projection-blurb">
          Project how a proposed prompt would affect remaining budget. Unknown
          remaining or high cost yields would_exceed=null (never invents safe).
        </p>
        <div className="flex flex-col gap-3 mt-3">
          {!bar ? (
            <>
              <label className="text-sm flex flex-col gap-1">
                <span>Daily cap USD (blank = unknown)</span>
                <LemonInput
                  value={capRaw}
                  onChange={(e) => setCapRaw(e.target.value)}
                  data-testid="pp-cap"
                />
              </label>
              <label className="text-sm flex flex-col gap-1">
                <span>Spent USD (blank = unknown)</span>
                <LemonInput
                  value={spentRaw}
                  onChange={(e) => setSpentRaw(e.target.value)}
                  data-testid="pp-spent"
                />
              </label>
            </>
          ) : (
            <div className="text-xs opacity-70" data-testid="pp-bar-injected">
              bar injected; remaining=
              {activeBar?.remaining_usd ?? "null"}
            </div>
          )}
          <label className="text-sm flex flex-col gap-1">
            <span>Projected cost low USD</span>
            <LemonInput
              value={lowRaw}
              onChange={(e) => setLowRaw(e.target.value)}
              data-testid="pp-low"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Projected cost high USD</span>
            <LemonInput
              value={highRaw}
              onChange={(e) => setHighRaw(e.target.value)}
              data-testid="pp-high"
            />
          </label>
          <LemonButton
            variant="primary"
            onClick={onProject}
            data-testid="pp-run"
          >
            Project against budget
          </LemonButton>
          {error ? (
            <div className="text-sm text-danger" data-testid="pp-error">
              {error}
            </div>
          ) : null}
          {result ? (
            <div data-testid="pp-result" className="text-sm flex flex-col gap-1">
              <div data-testid="pp-summary">
                {formatProjectionSummary(result)}
              </div>
              <div data-testid="pp-would-exceed">
                would_exceed=
                {result.would_exceed === null
                  ? "null"
                  : String(result.would_exceed)}
              </div>
            </div>
          ) : null}
        </div>
      </LemonCard>
    </div>
  );
}
