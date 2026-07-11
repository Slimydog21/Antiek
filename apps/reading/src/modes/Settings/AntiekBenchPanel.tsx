/**
 * AntiekBenchPanel — weekly model quality by task (advisory presentation).
 *
 * Injects weekly records to POST /settings/antiek-bench/weekly. Does not run
 * the bench or dispatch models. Mount from Settings/index when free (#770).
 */

import { useState } from "react";
import { LemonButton, LemonCard, LemonInput } from "../../components/lemon";
import {
  fetchWeeklyBenchView,
  formatBestModel,
  formatScore,
  type WeeklyBenchViewResponse,
} from "../../api/antiekBench";

export interface AntiekBenchPanelProps {
  fetchFn?: typeof fetchWeeklyBenchView;
  /** Optional demo records for offline dogfood without a live store. */
  demoRecords?: Array<{
    task: string;
    model_id: string;
    score: number | null;
    n_runs?: number;
  }>;
}

const DEFAULT_DEMO = [
  { task: "deep_research", model_id: "thinker", score: 0.88, n_runs: 2 },
  { task: "deep_research", model_id: "flash", score: 0.55, n_runs: 2 },
  { task: "note_taker", model_id: "flash", score: 0.91, n_runs: 3 },
  { task: "note_taker", model_id: "thinker", score: 0.6, n_runs: 3 },
];

export default function AntiekBenchPanel({
  fetchFn = fetchWeeklyBenchView,
  demoRecords = DEFAULT_DEMO,
}: AntiekBenchPanelProps) {
  const [weekId, setWeekId] = useState("2026-W28");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [view, setView] = useState<WeeklyBenchViewResponse | null>(null);

  async function onLoad() {
    setBusy(true);
    setError(null);
    try {
      const body = await fetchFn({
        week_id: weekId,
        records: demoRecords,
      });
      setView(body);
    } catch (e) {
      setView(null);
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div data-testid="antiek-bench-panel">
      <LemonCard title="Antiek-bench (weekly)" className="antiek-bench-panel">
        <p className="text-sm opacity-80" data-testid="antiek-bench-blurb">
          Advisory weekly model quality by task. Presentation only — not a
          production router. Unmeasured scores show as NOT MEASURED.
        </p>
        <div className="flex flex-col gap-3 mt-3">
          <label className="text-sm flex flex-col gap-1">
            <span>Week id</span>
            <LemonInput
              value={weekId}
              onChange={(e) => setWeekId(e.target.value)}
              data-testid="antiek-bench-week"
              aria-label="Bench week id"
            />
          </label>
          <LemonButton
            variant="primary"
            disabled={busy}
            onClick={() => void onLoad()}
            data-testid="antiek-bench-load"
          >
            {busy ? "Loading…" : "Load weekly view"}
          </LemonButton>
          {error ? (
            <div className="text-sm text-danger" data-testid="antiek-bench-error">
              {error}
            </div>
          ) : null}
          {view ? (
            <div data-testid="antiek-bench-result">
              <div data-testid="antiek-bench-authority">
                Authority: {view.authority}
              </div>
              <div data-testid="antiek-bench-incomplete">
                Incomplete: {view.incomplete ? "yes" : "no"}
              </div>
              <div data-testid="antiek-bench-best">
                Best by task:{" "}
                {Object.keys(view.best_by_task).length === 0
                  ? "none"
                  : Object.entries(view.best_by_task)
                      .map(([t, m]) => `${t}→${formatBestModel(m)}`)
                      .join(", ")}
              </div>
              <ul data-testid="antiek-bench-scores">
                {view.scores.map((s) => (
                  <li
                    key={`${s.task}:${s.model_id}`}
                    data-testid={`score-${s.task}-${s.model_id}`}
                  >
                    {s.task} / {s.model_id}: {formatScore(s.score)}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      </LemonCard>
    </div>
  );
}
