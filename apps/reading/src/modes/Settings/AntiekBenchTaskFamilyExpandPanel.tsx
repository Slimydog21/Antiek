/**
 * AntiekBenchTaskFamilyExpandPanel — recursive bench family expansion intent.
 *
 * Free-file. backlog_mutated, store_mutated, suite_rewritten always false.
 */

import { useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../../components/lemon";
import {
  composeAntiekBenchTaskFamilyExpand,
  formatAntiekBenchTaskFamilyExpandSummary,
  type AntiekBenchTaskFamilyExpandCompose,
} from "../../api/antiekBenchTaskFamilyExpandCompose";

export interface AntiekBenchTaskFamilyExpandPanelProps {
  composeFn?: typeof composeAntiekBenchTaskFamilyExpand;
}

export default function AntiekBenchTaskFamilyExpandPanel({
  composeFn = composeAntiekBenchTaskFamilyExpand,
}: AntiekBenchTaskFamilyExpandPanelProps) {
  const [weekId, setWeekId] = useState("2026-W28");
  const [newTask, setNewTask] = useState("marketplace_port");
  const [ack, setAck] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] =
    useState<AntiekBenchTaskFamilyExpandCompose | null>(null);

  function onCompose() {
    setError(null);
    setResult(null);
    try {
      setResult(
        composeFn({
          week_id: weekId.trim(),
          existing_tasks: ["deep_research", "twin_notes"],
          proposed_new_tasks: newTask.trim()
            ? [{ task: newTask.trim(), description: "platform expansion" }]
            : [],
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
              task: "deep_research",
              model_id: "composer",
              outcome: "failed",
            },
          ],
          operator_ack: ack,
          min_events_per_task: 3,
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <div data-testid="antiek-bench-task-family-expand-panel">
      <LemonCard
        title="Settings · Antiek-bench task family expand"
        className="antiek-bench-task-family-expand-panel"
      >
        <p className="text-sm opacity-80" data-testid="abtf-blurb">
          Propose sub-benchmark task families as the platform expands, using
          weekly usage learn. Pure — suite_rewritten stays false.
        </p>
        <div className="flex flex-col gap-2 mt-3">
          <label className="text-sm flex flex-col gap-1">
            <span>Week id</span>
            <LemonInput
              value={weekId}
              onChange={(e) => setWeekId(e.target.value)}
              data-testid="abtf-week"
            />
          </label>
          <label className="text-sm flex flex-col gap-1">
            <span>Proposed new task family</span>
            <LemonInput
              value={newTask}
              onChange={(e) => setNewTask(e.target.value)}
              data-testid="abtf-new"
            />
          </label>
          <label className="text-sm flex items-center gap-2">
            <input
              type="checkbox"
              checked={ack}
              onChange={(e) => setAck(e.target.checked)}
              data-testid="abtf-ack"
            />
            <span>operator_ack</span>
          </label>
          <LemonButton
            variant="primary"
            onClick={onCompose}
            data-testid="abtf-compose"
          >
            Compose task-family expand
          </LemonButton>
          {error ? (
            <p className="text-sm text-danger" data-testid="abtf-error">
              {error}
            </p>
          ) : null}
          {result ? (
            <div
              className="text-sm flex flex-col gap-1 mt-2"
              data-testid="abtf-result"
            >
              <div data-testid="abtf-ready">
                expand_ready={String(result.expand_ready)}
              </div>
              <div data-testid="abtf-count">
                families={result.family_count}
              </div>
              <div data-testid="abtf-backlog">
                backlog_mutated={String(result.backlog_mutated)}
              </div>
              <div data-testid="abtf-store">
                store_mutated={String(result.store_mutated)}
              </div>
              <div data-testid="abtf-suite">
                suite_rewritten={String(result.suite_rewritten)}
              </div>
              <div data-testid="abtf-summary">
                {formatAntiekBenchTaskFamilyExpandSummary(result)}
              </div>
            </div>
          ) : null}
        </div>
      </LemonCard>
    </div>
  );
}
