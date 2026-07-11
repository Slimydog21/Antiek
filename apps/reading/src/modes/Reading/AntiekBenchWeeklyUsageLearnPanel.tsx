/**
 * AntiekBenchWeeklyUsageLearnPanel — weekly usage → bench rewrite proposals.
 *
 * Free-file. backlog_mutated and store_mutated always false.
 */

import { useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../../components/lemon";
import {
  composeAntiekBenchWeeklyUsageLearn,
  formatAntiekBenchWeeklyUsageLearnSummary,
  type AntiekBenchWeeklyUsageLearnCompose,
} from "../../api/antiekBenchWeeklyUsageLearnCompose";

export interface AntiekBenchWeeklyUsageLearnPanelProps {
  composeFn?: typeof composeAntiekBenchWeeklyUsageLearn;
}

export default function AntiekBenchWeeklyUsageLearnPanel({
  composeFn = composeAntiekBenchWeeklyUsageLearn,
}: AntiekBenchWeeklyUsageLearnPanelProps) {
  const [weekId, setWeekId] = useState("2026-W28");
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<AntiekBenchWeeklyUsageLearnCompose | null>(null);

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      setResult(
        composeFn({
          week_id: weekId.trim(),
          operator_ack: ack,
          min_events_per_task: 2,
          events: [
            {
              event_id: "e1",
              task: "deep_research",
              model_id: "gpt-5",
              outcome: "failed",
            },
            {
              event_id: "e2",
              task: "deep_research",
              model_id: "gpt-5",
              outcome: "failed",
            },
            {
              event_id: "e3",
              task: "twin_notes",
              model_id: "claude",
              outcome: "worked",
            },
            {
              event_id: "e4",
              task: "twin_notes",
              model_id: "claude",
              outcome: "worked",
            },
          ],
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div data-testid="antiek-bench-weekly-usage-learn-panel">
      <LemonCard
        title="Antiek-bench · weekly usage learn"
        className="antiek-bench-weekly-usage-learn-panel"
      >
        <p className="text-sm opacity-80" data-testid="abwul-blurb">
          Learn from weekly usage what worked/failed to propose sub-benchmark
          rewrites. Pure — backlog_mutated and store_mutated stay false.
        </p>
        <div className="flex flex-col gap-2 mt-3">
          <label className="text-sm flex flex-col gap-1">
            <span>Week id</span>
            <LemonInput
              value={weekId}
              onChange={(e) => setWeekId(e.target.value)}
              data-testid="abwul-week"
            />
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={ack}
              onChange={(e) => setAck(e.target.checked)}
              data-testid="abwul-ack"
            />
            <span>operator_ack</span>
          </label>
          <LemonButton
            variant="primary"
            onClick={onCompose}
            data-testid="abwul-compose"
          >
            Compose weekly learn proposals
          </LemonButton>
          {error ? (
            <p className="text-sm text-danger" data-testid="abwul-error">
              {error}
            </p>
          ) : null}
          {result ? (
            <div
              className="text-sm flex flex-col gap-1 mt-2"
              data-testid="abwul-result"
            >
              <div data-testid="abwul-ready">
                learn_ready={String(result.learn_ready)}
              </div>
              <div data-testid="abwul-proposals">
                proposal_count={result.proposal_count}
              </div>
              <div data-testid="abwul-backlog">
                backlog_mutated={String(result.backlog_mutated)}
              </div>
              <div data-testid="abwul-store">
                store_mutated={String(result.store_mutated)}
              </div>
              <div data-testid="abwul-summary">
                {formatAntiekBenchWeeklyUsageLearnSummary(result)}
              </div>
            </div>
          ) : null}
        </div>
      </LemonCard>
    </div>
  );
}
