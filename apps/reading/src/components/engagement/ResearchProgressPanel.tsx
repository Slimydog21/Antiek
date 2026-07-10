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
 * Residual (ka): prefer prop researchTier; fall back to progress API research_tier.
 * Residual (lr): DecisionTreeDriverBadge with resolved tier during multi-minute jobs.
 * Residual (qm): DecisionTreeDriverBadge promptText for progress posture foresight.
 * Residual (mw): competitive duration band + poll cadence honesty by tier
 * (fast/deep/wrestle) for long-horizon Deep Research posture.
 * HTML-first; never PDF.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  fetchResearchProgress,
  seedResearchProgress,
  type ResearchProgressResponse,
} from "../../api/engagement";
import {
  mapResearchTierToProgressPollMs,
  RESEARCH_TIER_PROGRESS_POLL_MS,
} from "../../lib/researchTier";
import { DecisionTreeDriverBadge } from "./DecisionTreeDriverBadge";

/**
 * Residual (mw): competitive long-horizon duration bands (honest estimates).
 * Not a timer — posture for operator expectations vs OpenAI Deep Research-class
 * multi-minute jobs. Offline offline-honest; does not invent live ETA.
 */
export function competitiveDurationBand(
  tier: "fast" | "deep" | "wrestle" | null,
): { label: string; bandMinutes: string; pollMs: number } {
  if (tier === "wrestle") {
    return {
      label: "wrestle long-horizon",
      bandMinutes: "10–30+",
      pollMs: RESEARCH_TIER_PROGRESS_POLL_MS.wrestle,
    };
  }
  if (tier === "fast") {
    return {
      label: "fast distill",
      bandMinutes: "1–3",
      pollMs: RESEARCH_TIER_PROGRESS_POLL_MS.fast,
    };
  }
  // deep default
  return {
    label: "deep synthesize",
    bandMinutes: "3–10",
    pollMs: RESEARCH_TIER_PROGRESS_POLL_MS.deep,
  };
}

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

  // Residual (ka): prop wins; else spawn tier from progress payload (jz).
  const fromApi = (progress?.research_tier || "").trim().toLowerCase();
  const fromProp = (researchTier || "").trim().toLowerCase();
  const tierRaw = fromProp || fromApi;
  const tierKnown =
    tierRaw === "fast" || tierRaw === "deep" || tierRaw === "wrestle"
      ? tierRaw
      : null;
  const tierSource = fromProp
    ? "prop"
    : fromApi
      ? "api"
      : "none";

  // Residual (mw): competitive duration band + effective poll cadence honesty.
  const durationBand = useMemo(
    () => competitiveDurationBand(tierKnown),
    [tierKnown],
  );
  const effectivePollMs =
    pollIntervalMs && pollIntervalMs >= 500
      ? pollIntervalMs
      : mapResearchTierToProgressPollMs(tierKnown);

  return (
    <section
      className="research-progress-panel"
      data-testid="research-progress-panel"
      data-view-format="html"
      data-poll-ms={String(pollIntervalMs || 0)}
      data-research-tier={tierKnown || ""}
      data-research-tier-source={tierSource}
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
        {/* Residual (mw): competitive duration band + poll cadence honesty. */}
        {tierKnown ? (
          <p
            className="meta font-mono text-[11px]"
            data-testid="research-progress-competitive-band"
            data-research-tier={tierKnown}
            data-band-minutes={durationBand.bandMinutes}
            data-poll-ms={String(effectivePollMs)}
            data-view-format="html"
            role="status"
          >
            Competitive posture: {durationBand.label} · expected band ~
            {durationBand.bandMinutes} min · poll every{" "}
            {(effectivePollMs / 1000).toFixed(0)}s (offline-honest estimate, not
            a live ETA)
          </p>
        ) : null}
        {/* Residual (ij): Settings deep-link for model driver + budget. */}
        <p className="meta font-mono text-[11px] space-x-3">
          <a
            href="/settings"
            data-testid="research-progress-settings-link"
            title="Open Settings for decision-tree driver and daily budget"
          >
            Settings · driver & budget
          </a>
          <a
            href="/docs/campaigns/2026-07-09-research-reading-spine/DUAL-GATE-L1-L4-OPERATOR-CHECKLIST.md"
            data-testid="research-progress-dual-gate-checklist-link"
            title="Dual-gate L1–L4 checklist (prep only)"
          >
            Dual-gate L1–L4 checklist
          </a>
        </p>
        {/* Residual (lr): model+budget+depth during multi-minute plan→cite. */}
        {tierKnown ? (
          <div
            data-testid="research-progress-driver-badge-mount"
            data-view-format="html"
            data-research-tier={tierKnown}
          >
            <DecisionTreeDriverBadge
              researchTier={tierKnown}
              promptText={
                `research progress · spawn=${spawnId.trim()}` +
                (tierKnown ? ` · tier=${tierKnown}` : "") +
                (progress?.latest_stage
                  ? ` · stage=${progress.latest_stage}`
                  : "")
              }
            />
          </div>
        ) : null}
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
