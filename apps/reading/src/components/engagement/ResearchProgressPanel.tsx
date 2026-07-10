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
 * Residual (qw): Open Write twin_seed when progress is terminal (progress
 * events/HTML seed recursive note-taker; no invented document_id).
 * Residual (rp): mid-flight Open Write (progress draft) while non-terminal.
 * Residual (sm): float|full progress HTML reading windows (plan→cite substrate).
 * Residual (acp): data-write-seed-has-body on Open Write — true only when
 * progress.html yields non-empty plain text (parity marketplace/MO/spawn).
 * Residual (aim): Settings competitive DR scorecard deep-link during multi-minute
 * jobs (world-class DR honesty map · residual aii).
 * Residual (akt): FUTURE-AGENT competitive DR quality brief deep-link (parity
 * launch/collective/spawn/flywheel/MO FUTURE matrix during multi-minute jobs).
 * Residual (apn): stage pipeline cross-links citation hop completeness (api)
 * + competitive FUTURE brief (world-class DR bar: multi-stage + multi-hop).
 * Residual (ape): competitive plan→gather→synthesize→cite→terminal stage
 * pipeline completeness chrome (world-class DR multi-stage honesty).
 * Residual (asx): float|full|Write progress CTAs stamp multi-stage pipeline
 * completeness (completed/total · coverage · multi_stage_ready · long-horizon)
 * so open HTML reading paths carry competitive long-horizon honesty without
 * inventing hops (hops remain evidence pack).
 * HTML-first; never PDF.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  fetchResearchProgress,
  seedResearchProgress,
  type ResearchProgressResponse,
} from "../../api/engagement";
import { mapResearchTierToProgressPollMs } from "../../lib/researchTier";
import {
  buildResearchProgressWriteHref,
  plainTextFromHtml,
} from "../../workspace/twinWriteSeed";
import { openWindow } from "../windows/openWindow";
import { DecisionTreeDriverBadge } from "./DecisionTreeDriverBadge";

// Residual (apw/atj): pure helpers live in workspace/competitiveDrQuality —
// re-export for existing test/import paths (ResearchProgressPanel · DecisionTree · launch).
export {
  COMPETITIVE_DR_PIPELINE_STAGES,
  competitiveDurationBand,
  competitiveDrStageProgress,
  competitiveDrWorldClassReadiness,
  normalizeCompetitiveDrStage,
  type CompetitiveDrPipelineStage,
  type CompetitiveDrStageProgress,
  type CompetitiveDrWorldClassReadiness,
  type CompetitiveDurationBand,
} from "../../workspace/competitiveDrQuality";
import {
  competitiveDurationBand,
  competitiveDrStageProgress,
  competitiveDrWorldClassReadiness,
} from "../../workspace/competitiveDrQuality";

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
  /** Residual (qw): optional parent asset for twin_seed asset_id provenance. */
  parentAssetId?: string | null;
  /** Residual (qw): optional goal line in terminal Write seed. */
  goal?: string | null;
};

export function ResearchProgressPanel({
  spawnId,
  autoLoad = false,
  autoSeedIfEmpty = false,
  pollIntervalMs = 0,
  researchTier = null,
  parentAssetId = null,
  goal = null,
}: ResearchProgressPanelProps) {
  const [progress, setProgress] = useState<ResearchProgressResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Residual (ape): competitive plan→cite pipeline completeness from events.
  // Residual (aqd): prefer substrate stage_pipeline when shaped (aqc).
  const stagePipeline = useMemo(() => {
    const server = progress?.stage_pipeline;
    if (
      server &&
      typeof server.completed_count === "number" &&
      typeof server.total === "number" &&
      Array.isArray(server.completed)
    ) {
      return {
        stages: (server.stages?.length
          ? server.stages
          : [
              "plan",
              "gather",
              "synthesize",
              "cite",
              "terminal",
            ]) as readonly ("plan" | "gather" | "synthesize" | "cite" | "terminal")[],
        completed: server.completed as (
          | "plan"
          | "gather"
          | "synthesize"
          | "cite"
          | "terminal"
        )[],
        current: (server.current ?? null) as string | null,
        completed_count: server.completed_count,
        total: server.total,
        coverage_ratio:
          typeof server.coverage_ratio === "number"
            ? server.coverage_ratio
            : server.total > 0
              ? server.completed_count / server.total
              : 0,
        is_terminal: Boolean(server.is_terminal ?? progress?.is_terminal),
        source: "substrate" as const,
      };
    }
    return {
      ...competitiveDrStageProgress({
        events: progress?.events,
        latest_stage: progress?.latest_stage,
        is_terminal: progress?.is_terminal,
      }),
      source: "client" as const,
    };
  }, [
    progress?.events,
    progress?.latest_stage,
    progress?.is_terminal,
    progress?.stage_pipeline,
  ]);

  /**
   * Residual (asx): multi-stage pipeline stamps for long-horizon open CTAs
   * (float · full · Write). Pure derivation from stagePipeline; never invents hops.
   */
  const longHorizonOpenStamps = useMemo(() => {
    const coverage =
      Math.round(stagePipeline.coverage_ratio * 1000) / 1000;
    const wc = competitiveDrWorldClassReadiness({
      stage_coverage_ratio: stagePipeline.coverage_ratio,
      hop_coverage_ratio: null,
      stage_is_terminal: stagePipeline.is_terminal,
    });
    const stageLabel = `${stagePipeline.completed_count}/${stagePipeline.total} stages`;
    return {
      completed_count: stagePipeline.completed_count,
      total: stagePipeline.total,
      coverage_ratio: coverage,
      current: stagePipeline.current ?? "",
      is_terminal: stagePipeline.is_terminal,
      pipeline_source: stagePipeline.source,
      multi_stage_ready: wc.multi_stage_ready,
      world_class_bar: wc.world_class_bar,
      stage_label: stageLabel,
    };
  }, [stagePipeline]);

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

  /** Residual (qw/rp): progress → Write twin_seed (terminal or mid-flight draft). */
  const writeHref = useMemo(() => {
    if (!progress) return null;
    return buildResearchProgressWriteHref({
      spawnId: progress.spawn_id || spawnId,
      parentAssetId,
      researchTier: tierKnown,
      latestStage: progress.latest_stage,
      isTerminal: Boolean(progress.is_terminal),
      allowInProgress: true,
      events: progress.events,
      html: progress.html,
      goal,
    });
  }, [
    progress?.is_terminal,
    progress?.spawn_id,
    progress?.latest_stage,
    progress?.event_count,
    progress?.html,
    progress?.events,
    spawnId,
    parentAssetId,
    tierKnown,
    goal,
  ]);

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
            href="/settings#decision-tree-panel"
            data-testid="research-progress-settings-link"
            title="Open Settings decision-tree: driver, budget bar, sample cost projection"
          >
            Settings · driver & budget
          </a>
          <a
            href="/docs/campaigns/2026-07-09-research-reading-spine/DUAL-GATE-L1-L4-OPERATOR-CHECKLIST.md#l4-moil"
            data-testid="research-progress-dual-gate-checklist-link"
            title="Dual-gate L4 Midnight Oil live-step checklist (prep only · offline default)"
          >
            {/* Residual (aau): label matches #l4-moil href (was L1–L4). */}
            Dual-gate L4 Midnight Oil checklist
          </a>
          {/* Residual (aim): competitive DR quality scorecard during multi-minute jobs. */}
          <a
            href="/settings#settings-competitive-dr-scorecard"
            data-testid="research-progress-competitive-scorecard-link"
            title="Settings competitive deep-research scorecard (shipped vs deferred honesty)"
          >
            Settings · competitive DR scorecard
          </a>
          {/* Residual (akt): FUTURE competitive DR quality brief during multi-minute jobs. */}
          <a
            href="/docs/campaigns/2026-07-09-research-reading-spine/FUTURE-AGENT-SPEC-competitive-deep-research-quality.md"
            data-testid="research-progress-competitive-dr-future-agent-link"
            title="FUTURE-AGENT competitive deep-research quality brief (long-horizon wrestle · multi-minute plan→cite)"
          >
            FUTURE · competitive DR quality
          </a>
          {/* Residual (akl): multi-minute wrestle budget-before-fire → Settings prompt-cost (ake/akk). */}
          <a
            href="/settings#prompt-cost-projection"
            data-testid="research-progress-prompt-cost-projection-link"
            title="Settings prompt-cost projection: estimate how long-horizon wrestle spend hits remaining daily budget"
          >
            Settings · prompt-cost projection
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
          {/* Residual (ape): competitive multi-stage pipeline completeness. */}
          <div
            className="font-mono text-[11px] space-y-0.5 border border-ink/10 rounded p-2 dark:border-bright/10"
            data-testid="research-progress-stage-pipeline"
            data-completed-count={String(stagePipeline.completed_count)}
            data-total={String(stagePipeline.total)}
            data-coverage-ratio={String(
              Math.round(stagePipeline.coverage_ratio * 1000) / 1000,
            )}
            data-current={stagePipeline.current ?? ""}
            data-completed={stagePipeline.completed.join(",") || ""}
            data-is-terminal={String(stagePipeline.is_terminal)}
            data-pipeline-source={stagePipeline.source}
            data-view-format="html"
            role="status"
          >
            <p>
              Competitive pipeline · {stagePipeline.completed_count}/
              {stagePipeline.total} stages
              {stagePipeline.current
                ? ` · current=${stagePipeline.current}`
                : ""}
              {stagePipeline.is_terminal ? " · terminal" : ""}
            </p>
            <ol
              className="flex flex-wrap gap-1 list-none p-0 m-0"
              data-testid="research-progress-stage-pipeline-list"
            >
              {stagePipeline.stages.map((stage) => {
                const done = stagePipeline.completed.some(
                  (completed) => completed === stage,
                );
                const isCurrent = stagePipeline.current === stage;
                return (
                  <li
                    key={stage}
                    data-testid={`research-progress-stage-${stage}`}
                    data-stage={stage}
                    data-completed={String(done)}
                    data-current={String(isCurrent)}
                    className={
                      done
                        ? "opacity-100 font-semibold"
                        : "opacity-50"
                    }
                  >
                    {done ? "✓" : "○"} {stage}
                    {isCurrent && !stagePipeline.is_terminal ? " ←" : ""}
                    {stage !== "terminal" ? " ·" : ""}
                  </li>
                );
              })}
            </ol>
            {/* Residual (apn): competitive multi-stage × multi-hop citation bar. */}
            {/* Residual (apu): world-class readiness pure helper chrome. */}
            {/* Residual (aqh): prefer substrate world_class_readiness when shaped (aqf). */}
            {(() => {
              const serverWc = progress?.world_class_readiness;
              const fromSubstrate =
                serverWc &&
                typeof serverWc.world_class_bar === "string" &&
                typeof serverWc.multi_stage_ready === "boolean";
              const clientWc = competitiveDrWorldClassReadiness({
                stage_coverage_ratio: stagePipeline.coverage_ratio,
                hop_coverage_ratio: null,
                stage_is_terminal: stagePipeline.is_terminal,
              });
              const wc = fromSubstrate
                ? {
                    multi_stage_ready: Boolean(serverWc.multi_stage_ready),
                    citation_hops_ready:
                      serverWc.citation_hops_ready === undefined
                        ? null
                        : serverWc.citation_hops_ready,
                    stage_coverage_ratio:
                      typeof serverWc.stage_coverage_ratio === "number"
                        ? serverWc.stage_coverage_ratio
                        : stagePipeline.coverage_ratio,
                    hop_coverage_ratio:
                      serverWc.hop_coverage_ratio === undefined
                        ? null
                        : serverWc.hop_coverage_ratio,
                    world_class_bar: String(serverWc.world_class_bar),
                    source: "substrate" as const,
                  }
                : { ...clientWc, source: "client" as const };
              return (
                <>
                  <p
                    className="font-mono text-[11px] opacity-90 mt-1"
                    data-testid="research-progress-world-class-readiness"
                    data-multi-stage-ready={String(wc.multi_stage_ready)}
                    data-citation-hops-ready={
                      wc.citation_hops_ready == null
                        ? "unknown"
                        : String(wc.citation_hops_ready)
                    }
                    data-world-class-bar={wc.world_class_bar}
                    data-world-class-source={wc.source}
                    data-stage-coverage-ratio={String(
                      Math.round(wc.stage_coverage_ratio * 1000) / 1000,
                    )}
                    data-view-format="html"
                    role="status"
                  >
                    World-class DR bar · {wc.world_class_bar.replace(/_/g, " ")}
                    {" · "}
                    stage=
                    {Math.round(wc.stage_coverage_ratio * 100)}%
                    {" · hops="}
                    {wc.citation_hops_ready == null
                      ? "unknown (evidence pack)"
                      : wc.citation_hops_ready
                        ? "ready"
                        : "incomplete"}
                  </p>
                  <p
                    className="flex flex-wrap gap-x-3 gap-y-1 opacity-90 mt-1"
                    data-testid="research-progress-pipeline-competitive-nav"
                    data-view-format="html"
                    data-is-terminal={String(stagePipeline.is_terminal)}
                    data-completed-count={String(stagePipeline.completed_count)}
                    data-world-class-bar={wc.world_class_bar}
                    role="navigation"
                    aria-label="Competitive DR pipeline and citation hop navigation"
                  >
                    <span data-testid="research-progress-pipeline-citation-hop-hint">
                      Citation hops (insights → questions → sources) live on
                      evidence pack · never invent hops here
                    </span>
                    <a
                      href="/settings#settings-competitive-dr-scorecard"
                      data-testid="research-progress-pipeline-scorecard-link"
                      className="underline opacity-90 hover:opacity-100"
                      title="Settings competitive deep-research scorecard"
                    >
                      Settings · competitive DR scorecard
                    </a>
                    <a
                      href="/docs/campaigns/2026-07-09-research-reading-spine/FUTURE-AGENT-SPEC-competitive-deep-research-quality.md"
                      data-testid="research-progress-pipeline-future-agent-link"
                      className="underline opacity-90 hover:opacity-100"
                      title="FUTURE-AGENT competitive deep-research quality brief"
                    >
                      FUTURE · competitive DR brief
                    </a>
                  </p>
                </>
              );
            })()}
          </div>
          <p>
            latest=<strong>{progress.latest_stage ?? "(none)"}</strong> · events=
            {progress.event_count} · terminal={String(progress.is_terminal)}
          </p>
          {/* Residual (sm/asx): progress HTML → float|full reading windows with
              multi-stage long-horizon pipeline stamps on open CTAs. */}
          {progress.html?.trim() ? (
            <p className="meta font-mono text-[11px] space-x-3">
              <button
                type="button"
                data-testid="research-progress-open-float"
                data-view-format="html"
                data-html-first="true"
                data-window-mode="floating"
                data-is-terminal={String(Boolean(progress.is_terminal))}
                data-stage-completed-count={String(
                  longHorizonOpenStamps.completed_count,
                )}
                data-stage-total={String(longHorizonOpenStamps.total)}
                data-stage-coverage-ratio={String(
                  longHorizonOpenStamps.coverage_ratio,
                )}
                data-stage-current={longHorizonOpenStamps.current}
                data-pipeline-source={longHorizonOpenStamps.pipeline_source}
                data-multi-stage-ready={String(
                  longHorizonOpenStamps.multi_stage_ready,
                )}
                data-world-class-bar={longHorizonOpenStamps.world_class_bar}
                data-long-horizon="true"
                className="underline opacity-90 hover:opacity-100 bg-transparent border-0 p-0 cursor-pointer font-mono text-[11px]"
                title={`Open plan→cite progress as floating HTML window · ${longHorizonOpenStamps.stage_label} · multi-stage=${longHorizonOpenStamps.multi_stage_ready ? "ready" : "incomplete"} · never PDF`}
                onClick={() => {
                  const id = `research_progress:${spawnId}:${Date.now().toString(36)}`;
                  const source = progress.is_terminal
                    ? "research_progress_complete"
                    : "research_progress_draft";
                  const status = progress.is_terminal ? "complete" : "draft";
                  openWindow(
                    "hosted_html_document",
                    {
                      document_id: id,
                      title: `Research progress · ${longHorizonOpenStamps.stage_label} · ${status} · ${spawnId}`,
                      html: progress.html,
                      view_format: "html",
                      source,
                      research_tier: progress.research_tier || researchTier || null,
                    },
                    {
                      id: `win:progress:${id}`,
                      title: `Research progress · ${longHorizonOpenStamps.stage_label}`,
                      mode: "floating",
                    },
                  );
                }}
              >
                Open float (progress HTML)
              </button>
              <button
                type="button"
                data-testid="research-progress-open-full"
                data-view-format="html"
                data-html-first="true"
                data-window-mode="full"
                data-is-terminal={String(Boolean(progress.is_terminal))}
                data-stage-completed-count={String(
                  longHorizonOpenStamps.completed_count,
                )}
                data-stage-total={String(longHorizonOpenStamps.total)}
                data-stage-coverage-ratio={String(
                  longHorizonOpenStamps.coverage_ratio,
                )}
                data-stage-current={longHorizonOpenStamps.current}
                data-pipeline-source={longHorizonOpenStamps.pipeline_source}
                data-multi-stage-ready={String(
                  longHorizonOpenStamps.multi_stage_ready,
                )}
                data-world-class-bar={longHorizonOpenStamps.world_class_bar}
                data-long-horizon="true"
                className="underline opacity-90 hover:opacity-100 bg-transparent border-0 p-0 cursor-pointer font-mono text-[11px]"
                title={`Open plan→cite progress as full working-region HTML window · ${longHorizonOpenStamps.stage_label} · multi-stage=${longHorizonOpenStamps.multi_stage_ready ? "ready" : "incomplete"} · never PDF`}
                onClick={() => {
                  const id = `research_progress:${spawnId}:full:${Date.now().toString(36)}`;
                  const source = progress.is_terminal
                    ? "research_progress_complete"
                    : "research_progress_draft";
                  const status = progress.is_terminal ? "complete" : "draft";
                  openWindow(
                    "hosted_html_document",
                    {
                      document_id: id,
                      title: `Research progress · ${longHorizonOpenStamps.stage_label} · ${status} · ${spawnId} (full)`,
                      html: progress.html,
                      view_format: "html",
                      source,
                      research_tier: progress.research_tier || researchTier || null,
                    },
                    {
                      id: `win:progress:${id}:full`,
                      title: `Research progress · ${longHorizonOpenStamps.stage_label} (full)`,
                      mode: "full",
                    },
                  );
                }}
              >
                Open full (progress HTML)
              </button>
            </p>
          ) : null}
          {/* Residual (qw/rp/acp/aex/asx): terminal or mid-flight → Open Write + path
              + multi-stage long-horizon pipeline stamps. */}
          {writeHref ? (
            <p className="meta font-mono text-[11px]">
              <a
                href={writeHref}
                data-testid="research-progress-open-write"
                data-view-format="html"
                data-html-first="true"
                data-has-twin-seed="1"
                data-is-terminal={String(Boolean(progress.is_terminal))}
                // Residual (acp): body honesty on twin_seed (parity marketplace acf / MO ack / HostedHtml acn).
                data-write-seed-has-body={String(
                  Boolean(plainTextFromHtml(progress.html || "").trim()),
                )}
                // Residual (aex): plan→cite progress → Write path honesty.
                data-spawn-id={String(spawnId || "").trim()}
                data-research-tier={
                  (
                    progress.research_tier ||
                    researchTier ||
                    ""
                  )
                    .toString()
                    .trim()
                    .toLowerCase() || ""
                }
                data-progress-source={
                  progress.is_terminal
                    ? "research_progress_complete"
                    : "research_progress_draft"
                }
                data-seamless-progress-write={String(
                  Boolean(String(spawnId || "").trim()),
                )}
                // Residual (asx): multi-stage long-horizon pipeline on Write CTA.
                data-stage-completed-count={String(
                  longHorizonOpenStamps.completed_count,
                )}
                data-stage-total={String(longHorizonOpenStamps.total)}
                data-stage-coverage-ratio={String(
                  longHorizonOpenStamps.coverage_ratio,
                )}
                data-stage-current={longHorizonOpenStamps.current}
                data-pipeline-source={longHorizonOpenStamps.pipeline_source}
                data-multi-stage-ready={String(
                  longHorizonOpenStamps.multi_stage_ready,
                )}
                data-world-class-bar={longHorizonOpenStamps.world_class_bar}
                data-long-horizon="true"
                className="underline opacity-90 hover:opacity-100"
                title={
                  progress.is_terminal
                    ? `Open Write with terminal research progress as twin_seed · ${longHorizonOpenStamps.stage_label} · multi-stage=${longHorizonOpenStamps.multi_stage_ready ? "ready" : "incomplete"} · no invented document_id`
                    : `Open Write with in-progress plan→cite draft as twin_seed · ${longHorizonOpenStamps.stage_label} · multi-stage=${longHorizonOpenStamps.multi_stage_ready ? "ready" : "incomplete"} · mid-flight · no invented document_id`
                }
              >
                {progress.is_terminal
                  ? "Open Write (research complete)"
                  : "Open Write (progress draft)"}
              </a>
            </p>
          ) : null}
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
