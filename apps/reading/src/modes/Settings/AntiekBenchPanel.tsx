import { useEffect, useMemo, useState } from "react";

import {
  fetchWeeklyBenchView,
  formatScore,
  type WeeklyBenchViewResponse,
} from "../../api/antiekBench";
import { LemonButton, LemonCard } from "../../components/lemon";
import thinkingArt from "../../brand/werner/poses/session/werner_thinking_session_v1.png";

export interface AntiekBenchPanelProps {
  fetchFn?: typeof fetchWeeklyBenchView;
}

export default function AntiekBenchPanel({
  fetchFn = fetchWeeklyBenchView,
}: AntiekBenchPanelProps) {
  const [view, setView] = useState<WeeklyBenchViewResponse | null>(null);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setBusy(true);
    setError(null);
    try {
      setView(await fetchFn());
    } catch (caught) {
      setView(null);
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    void load();
  }, [fetchFn]);

  const bestByTask = useMemo(() => {
    const best = new Map<
      string,
      WeeklyBenchViewResponse["measurements"][number]
    >();
    for (const row of view?.measurements ?? []) {
      const current = best.get(row.task);
      if (
        !current ||
        row.score > current.score ||
        (row.score === current.score && row.model < current.model)
      ) {
        best.set(row.task, row);
      }
    }
    return [...best.entries()].sort(([left], [right]) =>
      left.localeCompare(right),
    );
  }, [view]);

  return (
    <LemonCard title="Antiek-bench · weekly evidence" elevation="z1">
      <div className="p-4 space-y-3" data-testid="antiek-bench-panel">
        <div className="flex items-start gap-3">
          <img
            src={thinkingArt}
            alt=""
            aria-hidden="true"
            data-testid="antiek-bench-werner"
            className="h-12 w-12 shrink-0 object-contain"
          />
          <p className="text-sm text-ink-soft dark:text-starlight">
            Advisory measurements from the latest validated server-owned report.
            This view never dispatches a model. Werner keeps score from the
            sidelines — living TV in Settings.
          </p>
        </div>
        {busy && <p role="status">Loading benchmark evidence…</p>}
        {error && (
          <div role="alert" className="space-y-2">
            <p>{error}</p>
            <LemonButton size="sm" onClick={() => void load()}>
              Retry
            </LemonButton>
          </div>
        )}
        {view?.status === "unavailable" && (
          <div data-testid="antiek-bench-unavailable">
            <strong>Not measured</strong>
            {view.notes.map((note) => (
              <p key={note} className="text-xs">
                {note}
              </p>
            ))}
          </div>
        )}
        {view?.status === "measured" && (
          <div data-testid="antiek-bench-measured" className="space-y-2">
            <p className="font-mono text-xs">
              {view.week_id} · generated {view.generated_at}
            </p>
            <ul className="space-y-1">
              {bestByTask.map(([task, row]) => (
                <li key={task}>
                  <strong>{task}</strong>: {row.model} ({row.provider}) ·{" "}
                  {formatScore(row.score)} · n={row.samples}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </LemonCard>
  );
}
