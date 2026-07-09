/**
 * ResearchProgressPanel — multi-minute deep-research progress telemetry UI.
 *
 * Residual (ax): plan → gather → synthesize → cite (+ terminal) for a spawn.
 * HTML-first; never PDF.
 */

import { useCallback, useState } from "react";
import {
  fetchResearchProgress,
  seedResearchProgress,
  type ResearchProgressResponse,
} from "../../api/engagement";

export type ResearchProgressPanelProps = {
  spawnId: string;
};

export function ResearchProgressPanel({ spawnId }: ResearchProgressPanelProps) {
  const [progress, setProgress] = useState<ResearchProgressResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const p = await fetchResearchProgress(spawnId, { includeHtml: true });
      if (p.view_format !== "html") {
        throw new Error("progress view_format must be html");
      }
      setProgress(p);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, [spawnId]);

  const seed = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const p = await seedResearchProgress(spawnId, { includeHtml: true });
      if (p.view_format !== "html") {
        throw new Error("progress view_format must be html");
      }
      setProgress(p);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }, [spawnId]);

  return (
    <section
      className="research-progress-panel"
      data-testid="research-progress-panel"
      data-view-format="html"
      aria-label="Research progress"
    >
      <header>
        <h2>Research progress</h2>
        <p className="meta">
          spawn <code>{spawnId}</code> · plan → gather → synthesize → cite
        </p>
      </header>
      <div className="controls" style={{ display: "flex", gap: "0.5rem" }}>
        <button
          type="button"
          data-testid="progress-refresh"
          onClick={() => void load()}
          disabled={busy}
        >
          {busy ? "Loading…" : "Refresh progress"}
        </button>
        <button
          type="button"
          data-testid="progress-seed"
          onClick={() => void seed()}
          disabled={busy}
        >
          Seed pipeline
        </button>
      </div>
      {error ? (
        <p className="error" role="alert">
          {error}
        </p>
      ) : null}
      {progress ? (
        <div data-testid="research-progress-summary" className="font-mono text-sm">
          <p>
            latest=<strong>{progress.latest_stage ?? "(none)"}</strong> · events=
            {progress.event_count} · terminal={String(progress.is_terminal)}
          </p>
          <ol data-testid="research-progress-events">
            {progress.events.map((e) => (
              <li key={`${e.sequence}-${e.stage}`}>
                #{e.sequence} [{e.stage}] {e.message}
              </li>
            ))}
          </ol>
          {progress.html ? (
            <div
              data-testid="research-progress-html"
              dangerouslySetInnerHTML={{ __html: progress.html }}
            />
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

export default ResearchProgressPanel;
