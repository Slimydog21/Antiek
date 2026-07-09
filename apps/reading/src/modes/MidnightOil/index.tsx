/**
 * Midnight Oil mode — goals + duration → recommended ceiling → explicit approve.
 * HTML deliverable only (view_format html). Worker launch is out of band.
 *
 * Residual (cz): prefill model_id from Settings decision-tree driver when
 * installed (editable override). Autonomous runs should inherit the same
 * driver the operator configured for workstation prompts.
 * Residual (db): open deposit HTML deliverable in hosted_html_document window
 * so Midnight Oil results join the reading/research flywheel (da host).
 * Residual (ew): open deposit as full working-region window as well as floating.
 * Residual (ex): auto-open deposit HTML floating after successful deposit /
 * auto-deposit run so Midnight Oil joins the reading flywheel without a click.
 * Residual (fo): Open Write HTML draft handoff for deposit document_id (fl/fm/fn).
 * Residual (gk): client offline twin reseed after deposit (ensure recursive
 * note-taker when backend twin_count is thin; non-fatal reinforce).
 * Residual (gl): ResearchProgressPanel on deposit when spawn_ids present
 * (competitive multi-minute plan→gather→synthesize→cite telemetry).
 * Residual (gs): budget-panel depth tier → create research_tier (fast|deep|wrestle).
 * Residual (hn): moil-ceiling-metrics + formula note for recommended price
 * ceiling transparency (goals+duration → approve before swarm work).
 * Residual (hy): live-step status panel (offline-honest dual-gate readiness).
 * Residual (ic): Settings deep-link for decision-tree driver + daily budget.
 * Residual (js): deposit progress panels pass researchTier + tier poll cadence.
 * Residual (md): recommended ceiling vs remaining daily budget fit chrome
 * (fits | may_exceed | unknown) — never invent $0 remaining.
 * Residual (me): soft-gate approve when ceiling may_exceed remaining budget
 * (force override required; unknown remaining never blocks).
 * Residual (ml): dual-gate L1–L4 checklist deep-link (parity mj; prep only).
 * Residual (ng): competitive recommended duration by research_tier
 * (parity progress mw bands) — apply-recommended chips for time-of-work.
 * Residual (nh): when research_tier changes, soft-sync duration if still at
 * previous recommended (preserve operator override otherwise).
 * Residual (nr): on Settings depth-tier prefill, soft-apply recommended
 * duration when still at factory default 60m.
 * Residual (on): CollectiveResearchPanel on deposit when spawn_ids (and/or
 * open windows / recent_ring) exist — multi-select merge into deposit HTML
 * asset without leaving Midnight Oil (offline swarm → cohesive unit).
 * Deposit spawn_ids also push into recent_ring for closed-window merge.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { seedTwinNotes } from "../../api/engagement";
import {
  approveMidnightOilCeiling,
  createMidnightOilJob,
  depositMidnightOilJob,
  fetchMidnightOilLiveStepStatus,
  runMidnightOilJob,
  type MidnightOilDepositResponse,
  type MidnightOilJobResponse,
  type MidnightOilLiveStepStatusResponse,
  type MidnightOilRunResponse,
} from "../../api/midnightOil";
import { fetchDecisionTreeSelection, fetchDepthTiers } from "../../api/settings";
import type { ResearchTier } from "../../lib/api";
import {
  formatResearchTierCeilingFactor,
  formatResearchTierDurationBand,
  mapDepthTierToResearchTier,
  mapResearchTierToCeilingMultiplier,
  mapResearchTierToProgressPollMs,
  mapResearchTierToRecommendedDurationMinutes,
} from "../../lib/researchTier";
import { CollectiveResearchPanel } from "../../components/engagement/CollectiveResearchPanel";
import { DecisionTreeDriverBadge } from "../../components/engagement/DecisionTreeDriverBadge";
import {
  ResearchLaunchBudgetPanel,
  type ResearchLaunchBudgetProjection,
  type ResearchLaunchTier,
} from "../../components/engagement/ResearchLaunchBudgetPanel";
import { ResearchProgressPanel } from "../../components/engagement/ResearchProgressPanel";
import { openWindow } from "../../components/windows/openWindow";
import { collectDeepResearchSpawnIds } from "../../workspace/collectDeepResearchSpawnIds";
import {
  listRecentDeepResearchSpawnIds,
  pushRecentDeepResearchSpawnId,
} from "../../workspace/recentDeepResearchSpawns";
import { useWindows } from "../../workspace/windowsStore";

/** HTML-only deposit open (floating | full). Returns window id or null. */
export function openMidnightOilDepositWindow(
  deposit: Pick<
    MidnightOilDepositResponse,
    "view_format" | "html" | "document_id" | "asset_id" | "job_id"
  >,
  mode: "floating" | "full" = "floating",
): string | null {
  if (deposit.view_format !== "html" || !deposit.html?.trim()) {
    return null;
  }
  const docId = deposit.document_id || deposit.asset_id;
  if (!docId) return null;
  const docKey = deposit.document_id || deposit.job_id || docId;
  const idSuffix = mode === "full" ? ":full" : "";
  return openWindow(
    "hosted_html_document",
    {
      document_id: docId,
      title: `Midnight Oil · ${deposit.job_id}`,
      html: deposit.html,
      view_format: "html",
      source: "midnight_oil_deposit",
    },
    {
      id: `win:moil-deposit:${docKey}${idSuffix}`,
      title: `Midnight Oil · ${deposit.job_id}`,
      mode,
    },
  );
}

export default function MidnightOil() {
  const [goalsText, setGoalsText] = useState("");
  const [durationMinutes, setDurationMinutes] = useState(60);
  /** Default until decision-tree prefill (cz); ceiling pricing accepts "default". */
  const [modelId, setModelId] = useState("default");
  const [driverPrefill, setDriverPrefill] = useState<
    "pending" | "installed" | "none" | "error"
  >("pending");
  const [job, setJob] = useState<MidnightOilJobResponse | null>(null);
  const [deposit, setDeposit] = useState<MidnightOilDepositResponse | null>(
    null,
  );
  const [runResult, setRunResult] = useState<MidnightOilRunResponse | null>(
    null,
  );
  const [ceilingInput, setCeilingInput] = useState("");
  const [forceBelow, setForceBelow] = useState(false);
  const [autoDeposit, setAutoDeposit] = useState(true);
  /** Residual (ex): auto-open hosted HTML after deposit (default on). */
  const [autoOpenDeposit, setAutoOpenDeposit] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [depositWindowId, setDepositWindowId] = useState<string | null>(null);
  // Residual (gk): twin reseed status after deposit.
  const [twinReseedStatus, setTwinReseedStatus] = useState<string | null>(null);
  // Residual (hy): live worker step readiness (offline default).
  const [liveStepStatus, setLiveStepStatus] =
    useState<MidnightOilLiveStepStatusResponse | null>(null);
  // Residual (on): deposit spawn → recent_ring + collective multi-select.
  const windows = useWindows((s) => s.windows);
  const [recentTick, setRecentTick] = useState(0);
  const recentSpawnIds = useMemo(
    () => listRecentDeepResearchSpawnIds(),
    [windows, recentTick, deposit],
  );
  const depositSpawnIds = useMemo(
    () =>
      (deposit?.spawn_ids ?? [])
        .map((x) => String(x || "").trim())
        .filter(Boolean),
    [deposit],
  );
  const availableSpawnIds = useMemo(
    () =>
      collectDeepResearchSpawnIds({
        currentSpawnId: null,
        extraSpawnIds: depositSpawnIds,
        windows,
        recentSpawnIds,
      }),
    [depositSpawnIds, windows, recentSpawnIds],
  );
  const depositParentAssetId = useMemo(() => {
    if (!deposit) return null;
    return (deposit.document_id || deposit.asset_id || "").trim() || null;
  }, [deposit]);

  /**
   * Residual (on): push deposit spawn ids into session recent_ring so they
   * remain multi-selectable after windows close / navigate away.
   */
  useEffect(() => {
    if (!depositSpawnIds.length) return;
    for (const sid of depositSpawnIds) {
      pushRecentDeepResearchSpawnId(sid);
    }
    setRecentTick((n) => n + 1);
  }, [depositSpawnIds]);

  const maybeAutoOpenDeposit = useCallback(
    (dep: MidnightOilDepositResponse) => {
      if (!autoOpenDeposit) return;
      const winId = openMidnightOilDepositWindow(dep, "floating");
      if (winId) setDepositWindowId(winId);
    },
    [autoOpenDeposit],
  );

  /**
   * Residual (gk): offline twin reseed after deposit lands.
   * Reinforces recursive note-taker; never blocks deposit UX.
   */
  const reseedDepositTwins = useCallback(
    async (dep: MidnightOilDepositResponse) => {
      const assetId = (dep.document_id || dep.asset_id || "").trim();
      if (!assetId || dep.view_format !== "html") {
        setTwinReseedStatus(null);
        return;
      }
      try {
        const plain = (dep.html || "")
          .replace(/<[^>]+>/g, " ")
          .replace(/\s+/g, " ")
          .trim()
          .slice(0, 2000);
        const seeded = await seedTwinNotes({
          asset_id: assetId,
          title: `Midnight Oil · ${dep.job_id}`,
          body_text: plain || dep.job_id,
          include_html: false,
          force_offline: true,
        });
        setTwinReseedStatus(
          seeded.seeded === false
            ? `Twin reseed skipped${seeded.seed_skipped ? `: ${seeded.seed_skipped}` : ""}`
            : `Twin notes reseeded for ${assetId}`,
        );
      } catch (e) {
        setTwinReseedStatus(
          e instanceof Error ? e.message : "Twin reseed failed (non-fatal)",
        );
      }
    },
    [],
  );
  // Residual (dg): soft-gate create when budget projection would exceed.
  const [budgetWarn, setBudgetWarn] = useState(false);
  const [forceOverBudget, setForceOverBudget] = useState(false);
  /**
   * Residual (md): last budget projection remaining_usd for ceiling-fit honesty.
   * null remaining = unknown (never invent $0).
   */
  const [budgetRemainingUsd, setBudgetRemainingUsd] = useState<number | null>(
    null,
  );
  /**
   * Residual (me): force approve when recommended ceiling may_exceed remaining.
   * Unknown remaining never requires force (cannot assert).
   */
  const [forceCeilingOverBudget, setForceCeilingOverBudget] = useState(false);
  // Residual (gs): depth tier for autonomous job create.
  const [researchTier, setResearchTier] = useState<ResearchTier>("deep");
  const onProjectionChange = useCallback(
    (p: ResearchLaunchBudgetProjection) => {
      setBudgetWarn(p.wouldExceedBudget === true);
      setBudgetRemainingUsd(
        typeof p.remainingUsd === "number" ? p.remainingUsd : null,
      );
    },
    [],
  );
  /**
   * Residual (nh): soft-sync duration when tier changes and operator has not
   * customized duration away from the previous recommended midpoint.
   */
  const onResearchTierChange = useCallback(
    (t: ResearchLaunchTier) => {
      setResearchTier((prev) => {
        const prevRec = mapResearchTierToRecommendedDurationMinutes(prev);
        const nextRec = mapResearchTierToRecommendedDurationMinutes(t);
        setDurationMinutes((d) => (d === prevRec ? nextRec : d));
        return t;
      });
    },
    [],
  );

  // Residual (cz): prefill model from decision-tree once on mount.
  // Residual (gt): prefill research tier from Settings depth-tier.
  useEffect(() => {
    let cancelled = false;
    void fetchDecisionTreeSelection()
      .then((tree) => {
        if (cancelled) return;
        if (tree.installed && tree.model_id?.trim()) {
          setModelId(tree.model_id.trim());
          setDriverPrefill("installed");
        } else {
          setDriverPrefill("none");
        }
      })
      .catch(() => {
        if (!cancelled) setDriverPrefill("error");
      });
    void fetchMidnightOilLiveStepStatus()
      .then((st) => {
        if (cancelled) return;
        if (st.view_format !== "html") return;
        setLiveStepStatus(st);
      })
      .catch(() => {
        /* non-fatal — offline default still true */
      });
    void fetchDepthTiers()
      .then((resp) => {
        if (cancelled) return;
        const mapped = mapDepthTierToResearchTier(resp.active_depth_tier);
        if (mapped) {
          setResearchTier(mapped);
          // Residual (nr): factory default duration is 60 — soft-apply competitive
          // recommended midpoint for the Settings depth-tier so MO time-of-work
          // matches depth posture without wiping custom edits.
          setDurationMinutes((d) =>
            d === 60
              ? mapResearchTierToRecommendedDurationMinutes(mapped)
              : d,
          );
        }
      })
      .catch(() => {
        /* keep default deep */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function onCreate(e: React.FormEvent) {
    e.preventDefault();
    if (budgetWarn && !forceOverBudget) {
      setError(
        "Projected cost may exceed remaining daily budget — enable force override or reduce goals.",
      );
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const goals = goalsText
        .split("\n")
        .map((g) => g.trim())
        .filter(Boolean);
      const created = await createMidnightOilJob({
        goals,
        duration_minutes: durationMinutes,
        model_id: modelId || null,
        research_tier: researchTier,
      });
      if (created.view_format !== "html") {
        throw new Error("Midnight Oil view_format must be html");
      }
      setJob(created);
      setCeilingInput(String(created.recommended_price_ceiling_usd));
      // Echo server-normalized tier if present.
      if (created.research_tier) {
        const rt = created.research_tier;
        if (rt === "fast" || rt === "deep" || rt === "wrestle") {
          setResearchTier(rt);
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  /** Residual (me): may_exceed remaining daily budget for a ceiling amount. */
  function ceilingMayExceedRemaining(ceilingUsd: number): boolean {
    if (budgetRemainingUsd == null || !Number.isFinite(budgetRemainingUsd)) {
      return false; // unknown → never invent block
    }
    return ceilingUsd > budgetRemainingUsd + 1e-9;
  }

  async function onApproveRecommended() {
    if (!job) return;
    const rec = job.recommended_price_ceiling_usd;
    if (ceilingMayExceedRemaining(rec) && !forceCeilingOverBudget) {
      setError(
        "Recommended ceiling may exceed remaining daily budget — enable force override or lower duration/tier.",
      );
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const approved = await approveMidnightOilCeiling({
        job_id: job.job_id,
        use_recommended: true,
      });
      setJob(approved);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function onApproveCustom() {
    if (!job) return;
    const amount = Number(ceilingInput);
    if (
      Number.isFinite(amount) &&
      ceilingMayExceedRemaining(amount) &&
      !forceCeilingOverBudget
    ) {
      setError(
        "Custom ceiling may exceed remaining daily budget — enable force override or lower the amount.",
      );
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const approved = await approveMidnightOilCeiling({
        job_id: job.job_id,
        ceiling_usd: amount,
        force_below: forceBelow,
      });
      setJob(approved);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function onDeposit() {
    if (!job) return;
    setBusy(true);
    setError(null);
    setTwinReseedStatus(null);
    try {
      const result = await depositMidnightOilJob({
        job_id: job.job_id,
        draft_combined: true,
        record_progress: true,
        mark_complete: true,
        include_progress_html: true,
      });
      if (result.view_format !== "html") {
        throw new Error("deposit view_format must be html");
      }
      setDeposit(result);
      setJob({
        ...job,
        status: result.job_status || "complete",
        asset_id: result.asset_id,
        runnable: false,
      });
      // Residual (gk): reinforce twin substrate after deposit.
      await reseedDepositTwins(result);
      // Residual (ex): auto-open floating hosted HTML flywheel.
      maybeAutoOpenDeposit(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  async function onRunOffline() {
    if (!job) return;
    setBusy(true);
    setError(null);
    try {
      const result = await runMidnightOilJob({
        job_id: job.job_id,
        auto_deposit: autoDeposit,
        spent_per_goal: 0.05,
      });
      if (result.view_format !== "html") {
        throw new Error("run view_format must be html");
      }
      setRunResult(result);
      setJob({
        ...job,
        status: result.status,
        runnable: result.runnable,
      });
      if (result.deposit) {
        setDeposit(result.deposit);
        setTwinReseedStatus(null);
        await reseedDepositTwins(result.deposit);
        // Residual (ex): auto-deposit path also auto-opens.
        maybeAutoOpenDeposit(result.deposit);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      className="h-full overflow-y-auto p-6"
      data-view-format="html"
      data-testid="midnight-oil-mode"
    >
      <header className="mb-6 space-y-1">
        <h1 className="text-2xl font-semibold">Midnight Oil</h1>
        <p className="text-sm opacity-80">
          Autonomous deep research without a live workstation session. Set goals
          and duration; review the recommended price ceiling; approve before work
          may run. Deliverable: HTML research asset (never PDF).
        </p>
      </header>

      {/* Residual (hy): live worker step dual-gate readiness (never enables). */}
      {liveStepStatus ? (
        <div
          className="mb-4 max-w-xl space-y-1 rounded border border-ink/15 p-3 font-mono text-[11px] dark:border-bright/15"
          data-testid="moil-live-step-status"
          data-offline-honest={String(liveStepStatus.offline_honest)}
          data-live-env={String(liveStepStatus.live_env)}
          data-injector-installed={String(liveStepStatus.injector_installed)}
          data-view-format="html"
          role="status"
        >
          <p>
            Worker mode:{" "}
            <strong>
              {liveStepStatus.offline_honest
                ? "offline-honest stub steps"
                : "live step dual-gate ready"}
            </strong>
          </p>
          <p>
            env <code>{liveStepStatus.live_env_flag}</code>=
            {String(liveStepStatus.live_env)} · injector=
            {String(liveStepStatus.injector_installed)}
          </p>
          {liveStepStatus.notes.map((n) => (
            <p key={n} className="opacity-80">
              {n}
            </p>
          ))}
        </div>
      ) : null}


      {/* Residual (ic/ml): Settings + dual-gate checklist (prep only). */}
      <p className="mb-4 max-w-xl text-[11px] font-mono space-x-3">
        <a
          href="/settings"
          data-testid="moil-settings-link"
          className="underline opacity-80 hover:opacity-100"
          title="Open Settings for decision-tree driver and daily budget cap"
        >
          Settings · model driver & budget
        </a>
        <a
          href="/docs/campaigns/2026-07-09-research-reading-spine/DUAL-GATE-L1-L4-OPERATOR-CHECKLIST.md"
          data-testid="moil-dual-gate-checklist-link"
          className="underline opacity-80 hover:opacity-100"
          title="Dual-gate L1–L4 operator checklist (live MO step prep; offline default)"
        >
          Dual-gate L1–L4 checklist
        </a>
      </p>

      <form onSubmit={(e) => void onCreate(e)} className="space-y-4 max-w-xl">
        <label className="block space-y-1">
          <span className="text-sm font-medium">Goals (one per line)</span>
          <textarea
            className="w-full min-h-[120px] border rounded p-2"
            value={goalsText}
            onChange={(e) => setGoalsText(e.target.value)}
            required
            disabled={busy}
          />
        </label>
        <label className="block space-y-1">
          <span className="text-sm font-medium">Duration (minutes)</span>
          <input
            type="number"
            min={1}
            className="w-full border rounded p-2"
            value={durationMinutes}
            onChange={(e) => setDurationMinutes(Number(e.target.value))}
            disabled={busy}
            data-testid="moil-duration-minutes"
          />
          {/* Residual (ng): competitive duration recommendation by depth tier. */}
          <div
            className="flex flex-wrap items-center gap-2 text-[11px] font-mono"
            data-testid="moil-duration-recommend"
            data-research-tier={researchTier}
            data-recommended-minutes={String(
              mapResearchTierToRecommendedDurationMinutes(researchTier),
            )}
            data-band-minutes={formatResearchTierDurationBand(researchTier)}
            data-current-minutes={String(durationMinutes)}
            data-matches-recommended={String(
              durationMinutes ===
                mapResearchTierToRecommendedDurationMinutes(researchTier),
            )}
            role="status"
          >
            <span className="opacity-80">
              Competitive band ({researchTier}):{" "}
              {formatResearchTierDurationBand(researchTier)} min · recommend{" "}
              {mapResearchTierToRecommendedDurationMinutes(researchTier)}m
            </span>
            <button
              type="button"
              data-testid="moil-apply-recommended-duration"
              disabled={busy}
              className="px-2 py-0.5 rounded border text-[11px]"
              title="Apply competitive recommended duration for current research tier"
              onClick={() =>
                setDurationMinutes(
                  mapResearchTierToRecommendedDurationMinutes(researchTier),
                )
              }
            >
              Use recommended ({mapResearchTierToRecommendedDurationMinutes(researchTier)}m)
            </button>
            {(["fast", "deep", "wrestle"] as const).map((tier) => (
              <button
                key={tier}
                type="button"
                data-testid={`moil-duration-chip-${tier}`}
                disabled={busy}
                className="px-2 py-0.5 rounded border text-[11px]"
                title={`Set duration to ${mapResearchTierToRecommendedDurationMinutes(tier)}m (${formatResearchTierDurationBand(tier)} band)`}
                onClick={() =>
                  setDurationMinutes(
                    mapResearchTierToRecommendedDurationMinutes(tier),
                  )
                }
              >
                {tier} {mapResearchTierToRecommendedDurationMinutes(tier)}m
              </button>
            ))}
          </div>
        </label>
        <label className="block space-y-1">
          <span className="text-sm font-medium">Model id</span>
          <input
            type="text"
            className="w-full border rounded p-2"
            value={modelId}
            onChange={(e) => setModelId(e.target.value)}
            disabled={busy}
            data-testid="moil-model-id"
            aria-label="Model id"
          />
          <div
            className="flex flex-wrap items-center gap-2"
            data-testid="moil-driver-prefill"
            data-prefill={driverPrefill}
            data-view-format="html"
          >
            <DecisionTreeDriverBadge researchTier={researchTier} />
            <span className="text-[10px] font-mono opacity-70">
              {driverPrefill === "installed"
                ? "Prefill from Settings decision tree (editable)"
                : driverPrefill === "none"
                  ? "No driver installed — using default / type a model"
                  : driverPrefill === "error"
                    ? "Driver lookup failed — using default"
                    : "Loading driver…"}
            </span>
          </div>
        </label>
        {/* Residual (cs): daily budget + prompt projection before ceiling approve. */}
        <div data-testid="moil-budget-mount" data-view-format="html">
          <ResearchLaunchBudgetPanel
            promptText={goalsText}
            researchTier={researchTier}
            allowTierPick
            onResearchTierChange={onResearchTierChange}
            onProjectionChange={onProjectionChange}
          />
          {budgetWarn ? (
            <label
              className="mt-1 flex items-center gap-2 text-[11px] font-mono text-emperor"
              data-testid="moil-over-budget-warn"
            >
              <input
                type="checkbox"
                data-testid="moil-force-over-budget"
                checked={forceOverBudget}
                onChange={(e) => setForceOverBudget(e.target.checked)}
                disabled={busy}
              />
              Force create despite budget projection
            </label>
          ) : null}
        </div>
        <button
          type="submit"
          disabled={busy || !goalsText.trim() || (budgetWarn && !forceOverBudget)}
        >
          {busy ? "Working…" : "Create job + recommend ceiling"}
        </button>
      </form>

      {error ? (
        <p className="mt-4 text-red-600" role="alert">
          {error}
        </p>
      ) : null}

      {job ? (
        <section className="mt-8 space-y-3 max-w-xl" data-testid="moil-job">
          <h2 className="text-lg font-medium">Job {job.job_id}</h2>
          <p>
            Status: <strong>{job.status}</strong>
            {job.runnable ? " · runnable" : ""}
          </p>
          {/* Residual (gs): show curated research tier on job receipt. */}
          <p
            className="font-mono text-sm"
            data-testid="moil-research-tier"
            data-research-tier={job.research_tier || researchTier}
          >
            Research tier:{" "}
            <strong>{job.research_tier || researchTier}</strong>
          </p>
          {/* Residual (hn): recommended price ceiling metrics + formula transparency. */}
          <div
            data-testid="moil-ceiling-metrics"
            data-job-id={job.job_id}
            data-status={job.status}
            data-duration-minutes={String(job.duration_minutes ?? 0)}
            data-goal-count={String((job.goals || []).length)}
            data-model-id={job.model_id || "default"}
            data-research-tier={job.research_tier || researchTier}
            data-recommended-usd={String(job.recommended_price_ceiling_usd)}
            data-approved-usd={
              job.approved_ceiling_usd != null
                ? String(job.approved_ceiling_usd)
                : ""
            }
            data-runnable={String(Boolean(job.runnable))}
            data-view-format="html"
            role="status"
          >
            Ceiling audit · duration={job.duration_minutes}m · goals=
            {(job.goals || []).length} · model=
            {job.model_id || "default"} · recommended=$
            {job.recommended_price_ceiling_usd.toFixed(2)}
          </div>
          <p
            data-testid="recommended-ceiling"
            data-recommended-usd={String(job.recommended_price_ceiling_usd)}
            data-duration-minutes={String(job.duration_minutes ?? 0)}
          >
            Recommended ceiling:{" "}
            <strong>${job.recommended_price_ceiling_usd.toFixed(2)}</strong>
          </p>
          {/* Residual (md): ceiling vs remaining daily budget fit (honest unknown). */}
          {(() => {
            const rec = job.recommended_price_ceiling_usd;
            let fit: "fits" | "may_exceed" | "unknown" = "unknown";
            if (budgetRemainingUsd != null && Number.isFinite(budgetRemainingUsd)) {
              fit = rec <= budgetRemainingUsd + 1e-9 ? "fits" : "may_exceed";
            }
            return (
              <p
                className="text-[11px] font-mono opacity-80"
                data-testid="moil-ceiling-budget-fit"
                data-fit={fit}
                data-recommended-usd={String(rec)}
                data-remaining-usd={
                  budgetRemainingUsd != null
                    ? String(budgetRemainingUsd)
                    : "unknown"
                }
                data-view-format="html"
                role="status"
              >
                Budget fit:{" "}
                <strong data-testid="moil-ceiling-budget-fit-label">
                  {fit === "fits"
                    ? "fits remaining daily budget"
                    : fit === "may_exceed"
                      ? "may exceed remaining daily budget"
                      : "unknown (remaining budget unset)"}
                </strong>
                {budgetRemainingUsd != null
                  ? ` · remaining=$${budgetRemainingUsd.toFixed(2)} · ceiling=$${rec.toFixed(2)}`
                  : " · remaining unknown — never invent $0"}
              </p>
            );
          })()}
          <p
            className="text-[11px] font-mono opacity-70"
            data-testid="moil-ceiling-formula-note"
          >
            Formula: duration × tokens/min × model rates × fanout × 1.25 safety
            × tier multiplier (fast 0.5 · deep 1.0 · wrestle 2.0)
            (recommendation only — explicit approve required before swarm work)
          </p>
          <p
            className="text-[11px] font-mono opacity-70"
            data-testid="moil-ceiling-tier-factor"
            data-research-tier={job.research_tier || researchTier}
            data-tier-multiplier={String(
              mapResearchTierToCeilingMultiplier(
                job.research_tier || researchTier,
              ),
            )}
          >
            Tier factor applied:{" "}
            <strong>
              {formatResearchTierCeilingFactor(
                job.research_tier || researchTier,
              )}
            </strong>
          </p>
          {job.approved_ceiling_usd != null ? (
            <p
              data-testid="approved-ceiling"
              data-approved-usd={String(job.approved_ceiling_usd)}
            >
              Approved ceiling:{" "}
              <strong>${job.approved_ceiling_usd.toFixed(2)}</strong>
            </p>
          ) : null}

          {job.status === "awaiting_approval" ? (
            <div className="space-y-2 border rounded p-3">
              {/* Residual (me): force when ceiling may_exceed remaining budget. */}
              <label
                className="flex items-center gap-2 text-sm font-mono"
                data-testid="moil-force-ceiling-over-budget"
              >
                <input
                  type="checkbox"
                  checked={forceCeilingOverBudget}
                  onChange={(e) => setForceCeilingOverBudget(e.target.checked)}
                  disabled={busy}
                />
                Force approve if ceiling may exceed remaining daily budget
              </label>
              <button
                type="button"
                onClick={() => void onApproveRecommended()}
                disabled={busy}
                data-testid="moil-approve-recommended"
              >
                Approve at recommended
              </button>
              <div className="flex flex-wrap items-center gap-2">
                <input
                  type="number"
                  step="0.01"
                  min="0.01"
                  className="border rounded p-2 w-32"
                  value={ceilingInput}
                  onChange={(e) => setCeilingInput(e.target.value)}
                  disabled={busy}
                />
                <label className="text-sm">
                  <input
                    type="checkbox"
                    checked={forceBelow}
                    onChange={(e) => setForceBelow(e.target.checked)}
                    disabled={busy}
                  />{" "}
                  Force below recommended
                </label>
                <button
                  type="button"
                  onClick={() => void onApproveCustom()}
                  disabled={busy}
                >
                  Approve custom ceiling
                </button>
              </div>
            </div>
          ) : null}

          {job.status === "approved" ||
          job.status === "complete" ||
          job.status === "running" ||
          job.status === "timed_out" ||
          job.status === "budget_halted" ? (
            <div className="space-y-2 border rounded p-3">
              <p className="text-sm opacity-80">
                Offline run simulates the autonomous swarm (one step per goal,
                stub spend, no live multi-provider). Deposit lands HTML + twins
                + progress. Live worker remains a separate future inject.
              </p>
              {job.status === "approved" || job.status === "running" ? (
                <>
                  <label className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      data-testid="moil-auto-deposit"
                      checked={autoDeposit}
                      onChange={(e) => setAutoDeposit(e.target.checked)}
                      disabled={busy}
                    />
                    Auto-deposit after offline run
                  </label>
                  <button
                    type="button"
                    data-testid="moil-run-offline"
                    onClick={() => void onRunOffline()}
                    disabled={busy}
                  >
                    {busy ? "Running…" : "Run offline worker"}
                  </button>
                </>
              ) : null}
              {/* Residual (ex): auto-open deposit HTML after deposit/auto-deposit. */}
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  data-testid="moil-auto-open-deposit"
                  checked={autoOpenDeposit}
                  onChange={(e) => setAutoOpenDeposit(e.target.checked)}
                  disabled={busy}
                />
                Auto-open deposit HTML window
              </label>
              <button
                type="button"
                data-testid="moil-deposit"
                onClick={() => void onDeposit()}
                disabled={busy}
              >
                {busy ? "Depositing…" : "Deposit results (HTML + twins)"}
              </button>
            </div>
          ) : null}

          {runResult ? (
            <div
              className="space-y-2 border rounded p-3"
              data-testid="moil-run-result"
              data-view-format="html"
              data-offline={String(runResult.offline)}
              data-live-step={String(Boolean(runResult.live_step))}
            >
              <h3 className="font-medium">
                {runResult.live_step
                  ? "Live step run result"
                  : "Offline run result"}
              </h3>
              {/* Residual (hw): machine-readable offline vs live swarm run metrics. */}
              <div
                data-testid="moil-run-metrics"
                data-status={runResult.status ?? ""}
                data-spent-usd={String(runResult.spent_usd ?? 0)}
                data-spawn-count={String(runResult.spawn_ids?.length ?? 0)}
                data-goals-total={String(runResult.goals_total ?? 0)}
                data-offline={String(Boolean(runResult.offline))}
                data-live-step={String(Boolean(runResult.live_step))}
                data-view-format="html"
                role="status"
              >
                Midnight Oil run · status={runResult.status} · spent=$
                {Number(runResult.spent_usd ?? 0).toFixed(4)} · spawns=
                {runResult.spawn_ids?.length ?? 0}/{runResult.goals_total ?? 0} ·
                offline={String(Boolean(runResult.offline))}
              </div>
              <p className="font-mono text-sm">
                status=<strong>{runResult.status}</strong> · spent=$
                {runResult.spent_usd.toFixed(4)} · spawns=
                {runResult.spawn_ids.length}/{runResult.goals_total} · offline=
                {String(runResult.offline)}
                {runResult.live_step != null
                  ? ` · live_step=${String(runResult.live_step)}`
                  : ""}
              </p>
              {runResult.notes_list?.length ? (
                <ul
                  className="text-[11px] font-mono text-ink-mute space-y-0.5"
                  data-testid="moil-run-notes"
                >
                  {runResult.notes_list.map((n) => (
                    <li key={n}>{n}</li>
                  ))}
                </ul>
              ) : null}
              {runResult.html ? (
                <div
                  className="prose border rounded p-3 text-sm max-h-48 overflow-auto"
                  data-testid="run-html"
                  dangerouslySetInnerHTML={{ __html: runResult.html }}
                />
              ) : null}
            </div>
          ) : null}

          {deposit ? (
            <div
              className="space-y-2 border rounded p-3"
              data-testid="moil-deposit-result"
              data-view-format="html"
            >
              <h3 className="font-medium">Deposit result</h3>
              {/* Residual (hx): machine-readable deposit land metrics. */}
              <div
                data-testid="moil-deposit-metrics"
                data-document-id={deposit.document_id ?? ""}
                data-asset-id={deposit.asset_id ?? ""}
                data-twin-count={String(deposit.twin_count ?? 0)}
                data-usage-recorded={String(Boolean(deposit.usage_recorded))}
                data-progress-seeded={String(Boolean(deposit.progress_seeded))}
                data-spawn-count={String(
                  (deposit.spawn_ids || []).filter(Boolean).length,
                )}
                data-view-format="html"
                role="status"
              >
                Midnight Oil deposit · document={deposit.document_id} · twins=
                {deposit.twin_count ?? 0} · usage=
                {String(Boolean(deposit.usage_recorded))} · progress_seeded=
                {String(Boolean(deposit.progress_seeded))}
              </div>
              <p className="font-mono text-sm">
                document=<code>{deposit.document_id}</code> · twins=
                {deposit.twin_count} · usage=
                {String(deposit.usage_recorded)} · progress_seeded=
                {String(deposit.progress_seeded)}
              </p>
              {/* Residual (gk): client twin reseed status. */}
              {twinReseedStatus ? (
                <p
                  className="font-mono text-[11px] opacity-80"
                  data-testid="moil-twin-reseed-status"
                  role="status"
                >
                  {twinReseedStatus}
                </p>
              ) : null}
              {/* Residual (gl): multi-minute progress for deposit spawn(s). */}
              {Array.isArray(deposit.spawn_ids) &&
              deposit.spawn_ids.filter(Boolean).length > 0 ? (
                <section
                  className="space-y-2 border-t border-ink/10 pt-2 dark:border-bright/10"
                  data-testid="moil-deposit-progress-mount"
                  data-view-format="html"
                  data-spawn-count={String(
                    deposit.spawn_ids.filter(Boolean).length,
                  )}
                  data-research-tier={job.research_tier || researchTier}
                >
                  <p className="text-[10px] font-mono uppercase tracking-wider opacity-70">
                    Research progress (deposit spawns)
                  </p>
                  {deposit.spawn_ids.filter(Boolean).map((sid) => {
                    const tier = (job.research_tier || researchTier || "deep")
                      .toString()
                      .toLowerCase();
                    // Residual (js/ju): shared poll map (parity DR host).
                    const pollMs = mapResearchTierToProgressPollMs(tier);
                    const closedTier =
                      tier === "fast" || tier === "deep" || tier === "wrestle"
                        ? tier
                        : "deep";
                    return (
                      <div
                        key={sid}
                        data-testid={`moil-progress-spawn-${sid}`}
                        data-spawn-id={sid}
                        data-research-tier={closedTier}
                        data-poll-ms={String(pollMs)}
                      >
                        <ResearchProgressPanel
                          spawnId={sid}
                          autoLoad
                          autoSeedIfEmpty
                          researchTier={closedTier}
                          pollIntervalMs={pollMs}
                        />
                      </div>
                    );
                  })}
                </section>
              ) : null}
              {/* Residual (on): multi-select deposit + recent DR spawns → deposit asset. */}
              {availableSpawnIds.length > 0 && depositParentAssetId ? (
                <section
                  className="space-y-2 border-t border-ink/10 pt-2 dark:border-bright/10"
                  data-testid="moil-deposit-collective-mount"
                  data-view-format="html"
                  data-available-spawn-count={String(availableSpawnIds.length)}
                  data-recent-count={String(recentSpawnIds.length)}
                  data-deposit-spawn-count={String(depositSpawnIds.length)}
                  data-asset-id={depositParentAssetId}
                >
                  <p className="text-[10px] font-mono uppercase tracking-wider opacity-70">
                    Collective research (deposit spawns)
                  </p>
                  <CollectiveResearchPanel
                    availableSpawnIds={availableSpawnIds}
                    parentAssetId={depositParentAssetId}
                    recentSpawnIds={recentSpawnIds}
                    preferredSpawnId={depositSpawnIds[0] ?? null}
                    onRecentSpawnsCleared={() => setRecentTick((n) => n + 1)}
                  />
                </section>
              ) : null}
              {deposit.progress ? (
                <p className="font-mono text-sm" data-testid="moil-progress-summary">
                  progress latest=
                  <strong>{deposit.progress.latest_stage ?? "(none)"}</strong> ·
                  events={deposit.progress.event_count ?? 0} · terminal=
                  {String(deposit.progress.is_terminal ?? false)}
                </p>
              ) : null}
              {deposit.html ? (
                <div
                  className="prose border rounded p-3 text-sm max-h-64 overflow-auto"
                  data-testid="deposit-html"
                  dangerouslySetInnerHTML={{ __html: deposit.html }}
                />
              ) : null}
              {deposit.progress?.html ? (
                <div
                  className="prose border rounded p-3 text-sm max-h-48 overflow-auto"
                  data-testid="deposit-progress-html"
                  dangerouslySetInnerHTML={{ __html: deposit.progress.html }}
                />
              ) : null}
              {/* Residual (db/ew): open deposit as hosted HTML reading window. */}
              <div className="flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  data-testid="moil-open-deposit-window"
                  disabled={
                    deposit.view_format !== "html" ||
                    !deposit.html ||
                    !deposit.document_id
                  }
                  onClick={() => {
                    const winId = openMidnightOilDepositWindow(
                      deposit,
                      "floating",
                    );
                    if (!winId) {
                      setError("deposit view_format must be html with body");
                      return;
                    }
                    setDepositWindowId(winId);
                  }}
                >
                  Open deposit in window
                </button>
                <button
                  type="button"
                  data-testid="moil-open-deposit-full"
                  disabled={
                    deposit.view_format !== "html" ||
                    !deposit.html ||
                    !deposit.document_id
                  }
                  onClick={() => {
                    const winId = openMidnightOilDepositWindow(deposit, "full");
                    if (!winId) {
                      setError("deposit view_format must be html with body");
                      return;
                    }
                    setDepositWindowId(winId);
                  }}
                >
                  Open deposit full
                </button>
                {/* Residual (fo): handoff deposit HTML into Write mode. */}
                {deposit.view_format === "html" && deposit.document_id ? (
                  <a
                    href={`/write?html_draft=${encodeURIComponent(deposit.document_id)}`}
                    data-testid="moil-open-write"
                    data-view-format="html"
                    className="rounded border border-ink/30 px-2 py-1 text-[11px] font-mono underline hover:bg-ink/5 dark:border-bright/30"
                    title="Open Write with Midnight Oil deposit as HTML draft handoff"
                  >
                    Open Write (HTML draft)
                  </a>
                ) : null}
                {depositWindowId ? (
                  <span
                    className="text-[11px] font-mono"
                    data-testid="moil-deposit-window-id"
                    role="status"
                  >
                    Window {depositWindowId}
                  </span>
                ) : null}
              </div>
            </div>
          ) : null}

          {job.html ? (
            <div
              className="prose border rounded p-3 text-sm"
              data-testid="job-html"
              dangerouslySetInnerHTML={{ __html: job.html }}
            />
          ) : null}
        </section>
      ) : null}
    </div>
  );
}
