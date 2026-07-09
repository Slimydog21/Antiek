/**
 * ResearchProgressPanel — multi-minute deep-research progress telemetry UI.
 *
 * Residual (ax): plan → gather → synthesize → cite (+ terminal) for a spawn.
 * Residual (cp): autoLoad (and optional empty-pipeline seed) on mount for
 * competitive multi-minute job visibility without an extra click.
 * Residual (hk): research-progress-metrics machine attrs for multi-minute
 * plan→cite audit (parity twin/flywheel metrics).
 * Residual (ij): Settings deep-link for driver + budget during multi-minute jobs.
 * Residual (jq): optional researchTier for long-horizon wrestle posture chrome.
 * HTML-first; never PDF.
 */

import { useCallback, useEffect, useState } from "react";
import {
  fetchResearchProgress,
  seedResearchProgress,
  type ResearchProgressResponse,
} from "../../api/engagement";

export type ResearchProgressPanelProps = {
  spawnId: string;
  /** Residual (cp): fetch progress on mount. */
  autoLoad?: boolean;
  /**
   * When autoLoad finds zero events, seed the offline plan→cite pipeline
   * so the operator sees stages immediately (honest offline scaffold).
   */
  autoSeedIfEmpty?: boolean;
  /**
   * Residual (cr): poll interval ms while non-terminal (competitive multi-minute
   * telemetry). 0/undefined disables polling after mount load.
   */
  pollIntervalMs?: number;
  /**
   * Residual (jq): closed research tier for competitive posture chrome
   * (wrestle → multi-minute long-horizon note).
   */
  researchTier?: "fast" | "deep" | "wrestle" | string | null;
};

export function ResearchProgressPanel({
  spawnId,
  autoLoad = false,
  autoSeedIfEmpty = false,
  pollIntervalMs = 0,
  researchTier = null,
}: ResearchProgressPanelProps) {
  const [progress, setProgress] = useState<ResearchProgressResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async (): Promise<ResearchProgressResponse | null> => {
    setBusy(true);
    setError(null);
    try {
      const p = await fetchResearchProgress(spawnId, { includeHtml: true });
      if (p.view_format !== "html") {
        throw new Error("progress view_format must be html");
      }
      setProgress(p);
      return p;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      return null;
    } finally {
      setBusy(false);
    }
  }, [spawnId]);

  const seed = useCallback(async (): Promise<ResearchProgressResponse | null> => {
    setBusy(true);
    setError(null);
    try {
      const p = await seedResearchProgress(spawnId, { includeHtml: true });
      if (p.view_format !== "html") {
        throw new Error("progress view_format must be html");
      }
      setProgress(p);
      return p;
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      return null;
    } finally {
      setBusy(false);
    }
  }, [spawnId]);

  useEffect(() => {
    if (!autoLoad || !spawnId.trim()) return;
    void (async () => {
      const p = await load();
      if (
        autoSeedIfEmpty &&
        p &&
        (p.event_count === 0 || (p.events || []).length === 0)
      ) {
        await seed();
      }
    })();
    // Mount-once per spawn when autoLoad is on (residual cp).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoLoad, autoSeedIfEmpty, spawnId]);

  // Residual (cr): poll while non-terminal for multi-minute deep research.
  useEffect(() => {
    if (!autoLoad || !pollIntervalMs || pollIntervalMs < 500) return;
    if (!spawnId.trim()) return;
    const id = window.setInterval(() => {
      // Stop polling once terminal; still refresh once more if already terminal.
      if (progress?.is_terminal) return;
      void load();
    }, pollIntervalMs);
    return () => window.clearInterval(id);
  }, [autoLoad, pollIntervalMs, spawnId, progress?.is_terminal, load]);

  const tier = (researchTier || "").trim().toLowerCase();
  const tierKnown =
    tier === "fast" || tier === "deep" || tier === "wrestle" ? tier : null;

  return (
    <section
      className="research-progress-panel"
      data-testid="research-progress-panel"
      data-view-format="html"
      data-poll-ms={String(pollIntervalMs || 0)}
      data-research-tier={tierKnown || ""}
      aria-label="Research progress"
    >
      <header>
        <h2>Research progress</h2>
        <p className="meta">
          spawn <code>{spawnId}</code> · plan → gather → synthesize → cite
          {tierKnown ? ` · tier=${tierKnown}` : ""}
        </p>
        {/* Residual (jq): long-horizon wrestle posture for competitive multi-minute. */}
        {tierKnown === "wrestle" ? (
          <p
            className="meta font-mono text-[11px]"
            data-testid="research-progress-wrestle-note"
            role="status"
          >
            Wrestle depth: multi-minute long-horizon synthesis (competitive Deep
            Research posture) · plan→cite may run longer than deep
          </p>
        ) : null}
        {/* Residual (ij): Settings deep-link for model driver + budget. */}
        <p className="meta font-mono text-[11px]">
          <a
            href="/settings"
            data-testid="research-progress-settings-link"
            title="Open Settings for decision-tree driver and daily budget"
          >
            Settings · driver & budget
          </a>
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
          {/* Residual (hk): machine-readable multi-minute progress metrics. */}
          <div
            data-testid="research-progress-metrics"
            data-spawn-id={progress.spawn_id ?? spawnId}
            data-event-count={String(progress.event_count ?? 0)}
            data-latest-stage={progress.latest_stage ?? ""}
            data-is-terminal={String(Boolean(progress.is_terminal))}
            data-view-format="html"
            data-product-panel={
              progress.product_panel ?? "research_progress"
            }
            data-source={progress.source ?? "engagement_spine.progress"}
            role="status"
          >
            Research progress · stage={progress.latest_stage ?? "(none)"} ·
            events={progress.event_count ?? 0} · terminal=
            {String(Boolean(progress.is_terminal))}
          </div>
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
