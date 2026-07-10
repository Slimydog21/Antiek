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
 * Residual (pz / FUTURE-AGENT V6): dual handoff html_draft + twin_seed so Write
 * create seeds recursive note-taker when empty (parity twin draft → Write).
 * Residual (gk): client offline twin reseed after deposit (ensure recursive
 * note-taker when backend twin_count is thin; non-fatal reinforce).
 * Residual (gl): ResearchProgressPanel on deposit when spawn_ids present
 * (competitive multi-minute plan→gather→synthesize→cite telemetry).
 * Residual (gs): budget-panel depth tier → create research_tier (fast|deep|wrestle).
 * Residual (add): ceiling metrics + formula use form fanout when job omits
 * fanout_depth (operator-selected depth honesty; parity ada–adc).
 * Residual (hn): moil-ceiling-metrics + formula note for recommended price
 * ceiling transparency (goals+duration → approve before swarm work).
 * Residual (hy): live-step status panel (offline-honest dual-gate readiness).
 * Residual (uh): Settings L4 live-step deep-link from MO mode (prep only).
 * Residual (ic): Settings deep-link for decision-tree driver + daily budget.
 * Residual (js): deposit progress panels pass researchTier + tier poll cadence.
 * Residual (md): recommended ceiling vs remaining daily budget fit chrome
 * (fits | may_exceed | unknown) — never invent $0 remaining.
 * Residual (um): remaining-after-ceiling projection (how approve affects daily cap).
 * Residual (un): custom ceiling remaining-after projection (parity um).
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
 * Residual (oo): TwinNotesPanel on deposit HTML asset (promote/chase multi-select
 * recursive note-taker) — parity hosted/Write; remount after promote/merge.
 * Residual (op): ResearchContextPanel on deposit (search/metrics over twin
 * substrate that feeds the next prompt) — remount on same refresh key as twins.
 * Residual (amp): deposit ResearchContext inherits job research_tier prefill
 * (parity marketplace amj · HostedHtml amk · DR aml · workstation amn).
 * Residual (oq): offline run spawn_ids push recent_ring even when auto_deposit
 * is off so swarm goals remain multi-selectable elsewhere (Write/hosted).
 * Residual (ot): run-result metrics surface recent_ring honesty (spawn count
 * remembered for collective multi-select without leaving MO or after navigate).
 * Residual (anu): knowledge-dense pub quick-call presets on create (parity
 * ResearchThis ahc · marketplace ahb · HostedHtml aha · offline-honest insert).
 * Residual (any): deposit land HTML-first honesty stamps + deposit-local
 * competitive DR scorecard/FUTURE deep-links (MO deposit polish · never invent L4 live).
 * Residual (oy): optional arxiv/substack/URL pub refs on create — hydrate then

 * append as grounded goals so offline swarm inherits knowledge-dense sources
 * (parity Write/ResearchThis; offline-honest hydrate default).
 * Residual (pa): budget projection promptText includes pub refs so soft-gate
 * Residual (qs): badge + budget share composeDriverPromptText (badge ≡ budget).
 * sees grounded-goal length before create (never under-project MO cost).
 * Residual (pb): dual-gate L1–L2 hydrate checklist deep-link beside pub refs
 * (prep only; never enables live arxiv/substack injectors).
 * Residual (pc): job receipt lists grounded publication goals count + chrome
 * so operator audits knowledge-dense swarm grounding after create.
 * Residual (aof): multi-goal swarm plan chrome — live goal_count + numbered
 * preview + professional research templates (one line = one swarm goal).
 * Residual (aog): job receipt lists full swarm goals (research + grounded pubs)
 * so create→job plan is auditable after recommend-ceiling (parity aof plan).
 * Residual (aoh): when goal_count > fanout_depth, soft-hint raise fan-out so
 * multi-goal swarm coverage is honest (never auto-change fanout).
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
  appendMoilGoalTemplate,
  MOIL_GOAL_TEMPLATES,
  goalsExceedFanout,
  moilDepositHtmlReadiness,
  moilPlanReadiness,
  parseMoilGoalLines,
  recommendedFanoutForGoals,
} from "../../lib/moilGoals";
import {
  estimateMoilRecommendedCeilingUsd,
  formatResearchTierCeilingFactor,
  formatResearchTierDurationBand,
  mapDepthTierToResearchTier,
  mapResearchTierToCeilingMultiplier,
  MOIL_CEILING_DEFAULT_FANOUT_DEPTH,
  MOIL_CEILING_SAFETY_FACTOR,
  MOIL_CEILING_TOKENS_PER_MINUTE,
  mapResearchTierToProgressPollMs,
  mapResearchTierToRecommendedDurationMinutes,
  resolveMoilPreviewCombinedUsdPer1m,
} from "../../lib/researchTier";
import { CollectiveResearchPanel } from "../../components/engagement/CollectiveResearchPanel";
import { DecisionTreeDriverBadge } from "../../components/engagement/DecisionTreeDriverBadge";
import { KNOWLEDGE_DENSE_PUBLICATION_PRESETS } from "../../components/engagement/PublicationAttachPanel";
import {
  ResearchLaunchBudgetPanel,
  type ResearchLaunchBudgetProjection,
  type ResearchLaunchTier,
} from "../../components/engagement/ResearchLaunchBudgetPanel";
import { ResearchContextPanel } from "../../components/engagement/ResearchContextPanel";
import { ResearchProgressPanel } from "../../components/engagement/ResearchProgressPanel";
import { TwinNotesPanel } from "../../components/engagement/TwinNotesPanel";
import { openWindow } from "../../components/windows/openWindow";
import {
  hydratePublicationRefs,
  parsePublicationRefs,
} from "../ResearchWorkstation/publicationRefs";
import { collectDeepResearchSpawnIds } from "../../workspace/collectDeepResearchSpawnIds";
import {
  competitiveDrOfflineSurfaceCatalog,
  competitiveDurationBand,
} from "../../workspace/competitiveDrQuality";
import {
  listRecentDeepResearchSpawnIds,
  pushRecentDeepResearchSpawnId,
} from "../../workspace/recentDeepResearchSpawns";
import {
  buildWriteHtmlDraftHref,
  plainTextFromHtml,
  storeTwinWriteSeed,
} from "../../workspace/twinWriteSeed";
import { useWindows } from "../../workspace/windowsStore";
import { composeDriverPromptText } from "../../lib/driverPromptText";

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
  // Residual (oy): knowledge-dense pub refs grounding for autonomous swarm.
  const [pubRefs, setPubRefs] = useState("");
  const [pubRefStatus, setPubRefStatus] = useState<string | null>(null);
  const [durationMinutes, setDurationMinutes] = useState(60);
  /**
   * Residual (adc): operator-controlled fan-out depth for recommended ceiling
   * (parity substrate DEFAULT_FANOUT_DEPTH=3; root + children).
   */
  const [fanoutDepth, setFanoutDepth] = useState(MOIL_CEILING_DEFAULT_FANOUT_DEPTH);
  // Residual (ard): plan readiness gates create (goals+duration · pure helper).
  const createPlanReadiness = useMemo(
    () =>
      moilPlanReadiness({
        goalsText,
        durationMinutes,
        fanoutDepth:
          Number.isFinite(fanoutDepth) && fanoutDepth > 0
            ? Math.floor(fanoutDepth)
            : MOIL_CEILING_DEFAULT_FANOUT_DEPTH,
      }),
    [goalsText, durationMinutes, fanoutDepth],
  );
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
  /**
   * Residual (aeg): last create-form preview USD (for post-create match audit).
   * Null until create; compared to server recommended_price_ceiling_usd.
   */
  const [lastPreviewCeilingUsd, setLastPreviewCeilingUsd] = useState<
    number | null
  >(null);
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
  // Residual (oo): remount twin panel after promote / collective merge.
  const [contextRefreshKey, setContextRefreshKey] = useState(0);
  const onContextNeedsRefresh = useCallback(() => {
    setContextRefreshKey((n) => n + 1);
  }, []);
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
  /** Residual (uf): open DR windows + deposit spawns (no recent-ring closed). */
  const openSpawnIds = useMemo(
    () =>
      collectDeepResearchSpawnIds({
        currentSpawnId: null,
        extraSpawnIds: depositSpawnIds,
        windows,
      }),
    [depositSpawnIds, windows],
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
   * Residual (on/oq): push spawn ids into session recent_ring so they remain
   * multi-selectable after windows close / navigate away.
   */
  const rememberSpawnIds = useCallback((ids: readonly string[] | null | undefined) => {
    let pushed = 0;
    for (const raw of ids ?? []) {
      const sid = String(raw || "").trim();
      if (!sid) continue;
      pushRecentDeepResearchSpawnId(sid);
      pushed += 1;
    }
    if (pushed > 0) setRecentTick((n) => n + 1);
  }, []);

  useEffect(() => {
    if (!depositSpawnIds.length) return;
    rememberSpawnIds(depositSpawnIds);
  }, [depositSpawnIds, rememberSpawnIds]);

  const maybeAutoOpenDeposit = useCallback(
    (dep: MidnightOilDepositResponse) => {
      if (!autoOpenDeposit) return;
      const winId = openMidnightOilDepositWindow(dep, "floating");
      if (winId) setDepositWindowId(winId);
    },
    [autoOpenDeposit],
  );

  /**
   * Residual (pz / FUTURE-AGENT V6): Write dual handoff — html_draft document_id
   * + sessionStorage twin_seed so create seeds twins when empty.
   */
  const depositWriteHref = useMemo(() => {
    if (!deposit || deposit.view_format !== "html" || !deposit.document_id) {
      return null;
    }
    const plain = plainTextFromHtml(deposit.html || "");
    const seedKey = plain
      ? storeTwinWriteSeed({
          plain_text: plain,
          html: deposit.html || "",
          title: `Midnight Oil · ${deposit.job_id}`,
          asset_id: deposit.document_id,
          note_ids: [],
          source: "midnight_oil_deposit",
          // Residual (adv): HTML deposit body → has_body true for rewrite feed.
          has_body: true,
        })
      : null;
    return buildWriteHtmlDraftHref({
      documentId: deposit.document_id,
      twinSeedKey: seedKey,
    });
  }, [deposit]);

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
        // Residual (ahu): MO deposit twin port honesty (offline · never invent live step).
        const portHonesty =
          "Port path: Midnight Oil deposit HTML (offline-honest · live multi-provider step dual-gate deferred · never invent L4 live worker).\n\n";
        const seeded = await seedTwinNotes({
          asset_id: assetId,
          title: `Midnight Oil · ${dep.job_id}`,
          body_text: (portHonesty + (plain || dep.job_id)).slice(0, 2200),
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
  /**
   * Residual (aue): competitiveDurationBand pure helper (atj) on MO duration
   * chrome — parity DecisionTree/LaunchBudget foresight · offline-honest.
   */
  const durationBand = useMemo(() => {
    const t = String(researchTier || "")
      .trim()
      .toLowerCase();
    if (t === "fast" || t === "flash") return competitiveDurationBand("fast");
    if (t === "wrestle") return competitiveDurationBand("wrestle");
    return competitiveDurationBand("deep");
  }, [researchTier]);
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
    setPubRefStatus(null);
    try {
      // Residual (aof): shared one-goal-per-line parser (swarm plan honesty).
      const goals = parseMoilGoalLines(goalsText);
      // Residual (oy): hydrate pub refs then append as grounded goals (HTML-first).
      const refs = parsePublicationRefs(pubRefs);
      if (refs.length > 0) {
        const hydrated = await hydratePublicationRefs(refs);
        // Swarm goals always see operator-supplied handles (never invent).
        for (const handle of refs) {
          const line = `Ground publication: ${handle}`;
          if (!goals.includes(line)) goals.push(line);
        }
        const offlineCount = (hydrated.ok || []).filter(
          (row) => row.offline_honest !== false,
        ).length;
        setPubRefStatus(
          `Hydrated ${hydrated.ok.length} pub asset(s)` +
            (hydrated.failed.length
              ? ` · ${hydrated.failed.length} failed`
              : "") +
            (offlineCount > 0
              ? ` · offline_honest≈${offlineCount}`
              : "") +
            " · HTML-first",
        );
      }
      const fanout =
        Number.isFinite(fanoutDepth) && fanoutDepth > 0
          ? Math.floor(fanoutDepth)
          : MOIL_CEILING_DEFAULT_FANOUT_DEPTH;
      // Residual (aeg): capture form preview before create for server match audit.
      const previewBeforeCreate = estimateMoilRecommendedCeilingUsd({
        durationMinutes,
        fanoutDepth: fanout,
        researchTier,
        modelId,
      });
      setLastPreviewCeilingUsd(previewBeforeCreate);
      const created = await createMidnightOilJob({
        goals,
        duration_minutes: durationMinutes,
        model_id: modelId || null,
        research_tier: researchTier,
        // Residual (adc): pass fan-out into recommended ceiling formula.
        fanout_depth: fanout,
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
      // Residual (adc): echo server fanout when present (formula honesty).
      if (
        typeof created.fanout_depth === "number" &&
        created.fanout_depth > 0
      ) {
        setFanoutDepth(created.fanout_depth);
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
      // Residual (oq): remember offline swarm spawns even if auto_deposit is off.
      rememberSpawnIds(result.spawn_ids);
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
      data-html-first="true"
      data-testid="midnight-oil-mode"
      data-multi-goal-swarm="true"
      data-goal-templates={String(MOIL_GOAL_TEMPLATES.length)}
      data-soft-budget="true"
      data-budget-before-fire="true"
      data-l4-live-step="deferred"
      data-never-auto-route="true"
    >
      <header className="mb-6 space-y-1">
        <h1 className="text-2xl font-semibold">Midnight Oil</h1>
        <p
          className="text-sm opacity-80"
          data-testid="moil-mode-intro"
          data-multi-goal-swarm="true"
          data-html-first="true"
          data-soft-budget="true"
          data-budget-before-fire="true"
        >
          Autonomous multi-goal deep research without a live workstation session.
          Set goals (one per line · research templates · fan-out coverage) and
          duration; review the recommended price ceiling; approve before the
          swarm may run. Deliverable: HTML research asset (never PDF). Soft
          budget ceiling · budget-before-fire · L4 live multi-provider step
          dual-gate · never auto-route model choice.
        </p>
        {/* Residual (aqn): MO budget/model honesty nav (parity Settings aqj–aqm). */}
        <p
          className="text-[11px] font-mono flex flex-wrap gap-x-3 gap-y-1 opacity-90"
          data-testid="moil-honesty-nav"
          data-view-format="html"
          data-soft-budget="true"
          data-budget-before-fire="true"
          data-never-auto-route="true"
          data-l4-live-step="deferred"
          role="navigation"
          aria-label="Midnight Oil budget and model honesty navigation"
        >
          <a
            href="/settings#prompt-cost-projection"
            data-testid="moil-prompt-cost-honesty-link"
            className="underline opacity-90 hover:opacity-100"
            title="Settings prompt-cost projection (soft budget foresight)"
          >
            Prompt-cost projection
          </a>
          <a
            href="/settings#decision-tree-panel"
            data-testid="moil-decision-tree-honesty-link"
            className="underline opacity-90 hover:opacity-100"
            title="Settings decision-tree driver (manual model choice · never auto-route)"
          >
            Decision-tree driver
          </a>
          <a
            href="/settings#notdiamond-advisory"
            data-testid="moil-notdiamond-honesty-link"
            className="underline opacity-90 hover:opacity-100"
            title="NotDiamond advisory only · never dispatch authority"
          >
            ND advisory
          </a>
          <span
            className="opacity-70"
            data-testid="moil-soft-budget-hint"
          >
            soft budget · budget-before-fire · L4 deferred · never auto-route
          </span>
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
          data-l4-prep="true"
          data-never-enables-live="true"
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


      {/* Residual (ic/ml/uh/aiu/arp): Settings + L4 + dual-gate + competitive DR scorecard. */}
      <p
        className="mb-4 max-w-xl text-[11px] font-mono space-x-3"
        data-testid="moil-competitive-links"
        data-view-format="html"
        data-html-first="true"
        data-offline-surface-count={String(
          competitiveDrOfflineSurfaceCatalog().count,
        )}
        data-live-injectors-deferred="true"
        data-notdiamond-is-router="false"
        role="navigation"
        aria-label="Midnight Oil competitive deep-research navigation"
      >
        <a
          href="/settings#decision-tree-panel"
          data-testid="moil-settings-link"
          className="underline opacity-80 hover:opacity-100"
          title="Open Settings decision-tree: driver, budget bar, sample cost projection"
        >
          Settings · model driver & budget
        </a>
        <a
          href="/settings#moil-live-step-status"
          data-testid="moil-settings-l4-live-step-link"
          className="underline opacity-80 hover:opacity-100"
          title="Open Settings Midnight Oil L4 live-step readiness (offline default · never enables live worker)"
        >
          Settings · L4 MO live-step
        </a>
        {/* Residual (wx): L4 MO live-step checklist section deep-link. */}
        <a
          href="/docs/campaigns/2026-07-09-research-reading-spine/DUAL-GATE-L1-L4-OPERATOR-CHECKLIST.md#l4-moil"
          data-testid="moil-dual-gate-checklist-link"
          className="underline opacity-80 hover:opacity-100"
          title="Dual-gate L4 Midnight Oil live-step checklist (prep only · offline default)"
        >
          Dual-gate L4 MO checklist
        </a>
        {/* Residual (aiu/arp): autonomous swarm → competitive DR honesty map (parity arm/arn/aro). */}
        <a
          href="/settings#settings-competitive-dr-scorecard"
          data-testid="moil-competitive-scorecard-link"
          data-offline-surface-count={String(
            competitiveDrOfflineSurfaceCatalog().count,
          )}
          data-notdiamond-is-router="false"
          className="underline opacity-80 hover:opacity-100"
          title={competitiveDrOfflineSurfaceCatalog().summary}
        >
          Settings · competitive DR scorecard
        </a>
        <a
          href="/docs/campaigns/2026-07-09-research-reading-spine/FUTURE-AGENT-SPEC-competitive-deep-research-quality.md"
          data-testid="moil-competitive-dr-future-agent-link"
          className="underline opacity-80 hover:opacity-100"
          title="FUTURE-AGENT competitive deep-research quality brief (L4 MO live dual-gate)"
        >
          FUTURE · competitive DR brief
        </a>
        {/* Residual (akk): autonomous budget-before-fire → Settings prompt-cost projection (ake). */}
        <a
          href="/settings#prompt-cost-projection"
          data-testid="moil-prompt-cost-projection-link"
          className="underline opacity-80 hover:opacity-100"
          title="Settings prompt-cost projection: estimate how a proposed prompt hits remaining daily budget"
        >
          Settings · prompt-cost projection
        </a>
      </p>

      <form onSubmit={(e) => void onCreate(e)} className="space-y-4 max-w-xl">
        <div className="block space-y-1">
          <label className="block space-y-1">
            <span className="text-sm font-medium">Goals (one per line)</span>
            <p className="text-[11px] font-mono opacity-70">
              Each non-empty line is one autonomous swarm goal. Templates append
              without inventing content — edit freely before create.
            </p>
            <textarea
              className="w-full min-h-[120px] border rounded p-2"
              value={goalsText}
              onChange={(e) => setGoalsText(e.target.value)}
              required
              disabled={busy}
              data-testid="moil-goals-input"
              aria-label="Goals (one per line)"
            />
          </label>
          {/* Residual (aof): multi-goal swarm plan chrome + research templates
              (outside label so getByLabelText stays unique for goals field). */}
          {(() => {
            const goalLines = parseMoilGoalLines(goalsText);
            // Residual (ara): pure plan readiness before create + ceiling.
            const planReady = moilPlanReadiness({
              goalsText,
              durationMinutes,
              fanoutDepth:
                Number.isFinite(fanoutDepth) && fanoutDepth > 0
                  ? Math.floor(fanoutDepth)
                  : MOIL_CEILING_DEFAULT_FANOUT_DEPTH,
            });
            return (
              <div
                className="space-y-1 font-mono text-[11px]"
                data-testid="moil-goals-plan"
                data-goal-count={String(goalLines.length)}
                data-template-count={String(MOIL_GOAL_TEMPLATES.length)}
                data-view-format="html"
                data-plan-ready={String(planReady.plan_ready)}
                data-duration-ready={String(planReady.duration_ready)}
                data-goals-ready={String(planReady.goals_ready)}
                role="status"
              >
                <p
                  className="opacity-80"
                  data-testid="moil-plan-readiness"
                  data-plan-ready={String(planReady.plan_ready)}
                  data-goal-count={String(planReady.goal_count)}
                  data-duration-minutes={String(planReady.duration_minutes)}
                  data-fanout-depth={String(planReady.fanout_depth)}
                  data-goals-exceed-fanout={String(
                    planReady.goals_exceed_fanout,
                  )}
                  data-recommended-fanout={String(planReady.recommended_fanout)}
                  data-html-first="true"
                >
                  Plan readiness · {planReady.summary}
                </p>
                <p className="opacity-80">
                  Swarm plan · {goalLines.length} goal
                  {goalLines.length === 1 ? "" : "s"}
                  {goalLines.length === 0
                    ? " · add at least one line before create"
                    : ""}
                </p>
                {goalLines.length > 0 ? (
                  <ol
                    className="list-decimal pl-5 space-y-0.5 opacity-90"
                    data-testid="moil-goals-plan-list"
                  >
                    {goalLines.map((g, i) => (
                      <li
                        key={`${i}-${g.slice(0, 24)}`}
                        data-testid={`moil-goals-plan-item-${i}`}
                        data-goal-index={String(i)}
                      >
                        {g.length > 160 ? `${g.slice(0, 157)}…` : g}
                      </li>
                    ))}
                  </ol>
                ) : null}
                <div
                  className="flex flex-wrap gap-1 items-center pt-1"
                  data-testid="moil-goal-templates"
                >
                  <span className="opacity-70">Templates:</span>
                  {MOIL_GOAL_TEMPLATES.map((t) => (
                    <button
                      key={t.id}
                      type="button"
                      data-testid={`moil-goal-template-${t.id}`}
                      disabled={busy}
                      className="px-2 py-0.5 rounded border text-[11px]"
                      title={t.text}
                      onClick={() =>
                        setGoalsText((prev) =>
                          appendMoilGoalTemplate(prev, t.text),
                        )
                      }
                    >
                      {t.label}
                    </button>
                  ))}
                </div>
                {/* Residual (aoh): soft-hint when goals exceed fan-out depth.
                    Residual (aop): explicit Match fan-out action (operator click only). */}
                {(() => {
                  const effectiveFanout =
                    Number.isFinite(fanoutDepth) && fanoutDepth > 0
                      ? Math.floor(fanoutDepth)
                      : MOIL_CEILING_DEFAULT_FANOUT_DEPTH;
                  // Residual (aox): pure exceeds predicate (parity aow match target).
                  const exceeds = goalsExceedFanout(
                    goalLines.length,
                    effectiveFanout,
                  );
                  // Residual (aow): pure helper for Match fan-out target (cap 12).
                  const matchTarget = recommendedFanoutForGoals(
                    goalLines.length,
                    12,
                  );
                  return (
                    <div
                      className="space-y-1"
                      data-testid="moil-goals-fanout-coverage"
                      data-goal-count={String(goalLines.length)}
                      data-fanout-depth={String(effectiveFanout)}
                      data-exceeds-fanout={String(exceeds)}
                    >
                      <p
                        className="opacity-80"
                        data-testid="moil-goals-fanout-hint"
                        data-goal-count={String(goalLines.length)}
                        data-fanout-depth={String(effectiveFanout)}
                        data-exceeds-fanout={String(exceeds)}
                        role="status"
                      >
                        {exceeds
                          ? `Soft hint: ${goalLines.length} goals > fan-out depth ${effectiveFanout} — raise fan-out so multi-goal swarm can branch (never auto-changed)`
                          : goalLines.length > 0
                            ? `Fan-out depth ${effectiveFanout} covers ${goalLines.length} goal${goalLines.length === 1 ? "" : "s"} (coverage ok)`
                            : `Fan-out depth ${effectiveFanout} · add goals for swarm coverage audit`}
                      </p>
                      {exceeds ? (
                        <button
                          type="button"
                          data-testid="moil-match-fanout-to-goals"
                          data-match-target={String(matchTarget)}
                          disabled={busy}
                          className="px-2 py-0.5 rounded border text-[11px]"
                          title={`Set fan-out depth to ${matchTarget} to cover ${goalLines.length} goals (operator click · never auto)`}
                          onClick={() => setFanoutDepth(matchTarget)}
                        >
                          Match fan-out to goals ({matchTarget})
                        </button>
                      ) : null}
                    </div>
                  );
                })()}
              </div>
            );
          })()}
        </div>
        {/* Residual (oy/anu): knowledge-dense arxiv/substack/URL grounding. */}
        <div
          className="block space-y-1"
          data-testid="moil-pub-refs-block"
          data-view-format="html"
          data-offline-default="true"
          data-l1-l2-hydrate-prep="true"
          data-seamless-pub-quick-call="true"
          data-knowledge-dense-presets={String(
            KNOWLEDGE_DENSE_PUBLICATION_PRESETS.length,
          )}
        >
          <span className="text-sm font-medium">
            Publication refs (optional · one per line)
          </span>
          <p className="text-[11px] font-mono opacity-70">
            arxiv / substack / URL — hydrated then appended as grounded goals
            for the offline swarm (HTML-first; live body hydrate is dual-gate).
          </p>
          {/* Residual (anu): MO create quick-call (parity ResearchThis ahc). */}
          <div
            className="flex flex-wrap gap-1 items-center"
            data-testid="moil-publication-quick-call"
            data-preset-count={String(KNOWLEDGE_DENSE_PUBLICATION_PRESETS.length)}
            data-seamless-pub-quick-call="true"
            data-auto-hydrate="false"
            role="group"
            aria-label="Knowledge-dense publication quick-call presets"
          >
            <span className="text-[10px] font-mono opacity-70 mr-1">
              Quick-call:
            </span>
            {KNOWLEDGE_DENSE_PUBLICATION_PRESETS.map((p) => (
              <button
                key={p.id}
                type="button"
                data-testid={`moil-preset-${p.id}`}
                data-preset-id={p.id}
                data-kind={p.kind}
                data-reference={p.reference}
                data-auto-hydrate="false"
                disabled={busy}
                onClick={() => {
                  const ref = p.reference.trim();
                  if (!ref) return;
                  setPubRefs((prev) => {
                    const existing = new Set(
                      prev
                        .split(/\r?\n/)
                        .map((l) => l.trim())
                        .filter(Boolean),
                    );
                    if (existing.has(ref)) return prev;
                    const base = prev.trim();
                    return base ? `${base}\n${ref}` : ref;
                  });
                }}
                className="text-[10px] font-mono border rounded px-1.5 py-0.5 opacity-80 hover:opacity-100 disabled:opacity-50 border-ink/20 dark:border-bright/20"
                title={`Insert ${p.reference} (hydrates offline-honest on create · never auto-live)`}
              >
                {p.label}
              </button>
            ))}
          </div>
          <textarea
            className="w-full min-h-[72px] border rounded p-2 font-mono text-sm"
            value={pubRefs}
            onChange={(e) => setPubRefs(e.target.value)}
            disabled={busy}
            data-testid="moil-pub-refs"
            data-view-format="html"
            placeholder={"arxiv:1706.03762\nhttps://…"}
            aria-label="Publication references for Midnight Oil grounding"
          />
          {/* Residual (pb/uw): L1/L2 hydrate prep deep-links (parity marketplace uu). */}
          <p className="text-[11px] font-mono space-x-2">
            <a
              href="/settings#hydrate-live-status"
              data-testid="moil-pub-refs-hydrate-settings-link"
              className="underline opacity-80 hover:opacity-100"
              title="Settings publication hydrate readiness (arxiv/substack · offline default)"
            >
              Settings · hydrate readiness
            </a>
            {/* Residual (xy): L1 arxiv checklist section (pub-refs hydrate prep). */}
            <a
              href="/docs/campaigns/2026-07-09-research-reading-spine/DUAL-GATE-L1-L4-OPERATOR-CHECKLIST.md#l1-arxiv"
              data-testid="moil-pub-refs-dual-gate-link"
              className="underline opacity-80 hover:opacity-100"
              title="Dual-gate L1 arxiv hydrate checklist (prep only · offline identity default)"
            >
              Dual-gate L1 arxiv checklist
            </a>
            {/* Residual (aan): L2 Substack section (parity aal/aam · midnight oil pubs). */}
            <a
              href="/docs/campaigns/2026-07-09-research-reading-spine/DUAL-GATE-L1-L4-OPERATOR-CHECKLIST.md#l2-substack"
              data-testid="moil-pub-refs-dual-gate-l2-link"
              className="underline opacity-80 hover:opacity-100"
              title="Dual-gate L2 Substack hydrate checklist (prep only · factory + ToS)"
            >
              Dual-gate L2 Substack checklist
            </a>
            <span
              className="opacity-70"
              data-testid="moil-pub-refs-offline-default"
              data-offline-honest="true"
              role="status"
            >
              offline identity default
            </span>
          </p>
          {pubRefStatus ? (
            <p
              className="text-[11px] font-mono opacity-80"
              data-testid="moil-pub-refs-status"
              role="status"
            >
              {pubRefStatus}
            </p>
          ) : null}
        </div>
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
          {/* Residual (ng/aue): competitive duration recommendation by depth tier
              + competitiveDurationBand pure helper stamps (atj). */}
          <div
            className="flex flex-wrap items-center gap-2 text-[11px] font-mono"
            data-testid="moil-duration-recommend"
            data-research-tier={researchTier}
            data-recommended-minutes={String(
              mapResearchTierToRecommendedDurationMinutes(researchTier),
            )}
            data-band-minutes={durationBand.bandMinutes}
            data-band-label={durationBand.label}
            data-poll-ms={String(durationBand.pollMs)}
            data-competitive-duration-band="true"
            data-current-minutes={String(durationMinutes)}
            data-matches-recommended={String(
              durationMinutes ===
                mapResearchTierToRecommendedDurationMinutes(researchTier),
            )}
            role="status"
          >
            <span className="opacity-80">
              Competitive band ({researchTier} · {durationBand.label}):{" "}
              {durationBand.bandMinutes} min · recommend{" "}
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
        {/* Residual (adc): fan-out depth for recommended price ceiling intensity. */}
        <label className="block space-y-1">
          <span className="text-sm font-medium">Fan-out depth</span>
          <p className="text-[11px] font-mono opacity-70">
            Investigation tree depth (root + children). Scales recommended
            ceiling · default {MOIL_CEILING_DEFAULT_FANOUT_DEPTH} · recommendation
            only.
          </p>
          <input
            type="number"
            min={1}
            max={12}
            className="w-full border rounded p-2"
            value={fanoutDepth}
            onChange={(e) => setFanoutDepth(Number(e.target.value))}
            disabled={busy}
            data-testid="moil-fanout-depth"
            data-default-fanout={String(MOIL_CEILING_DEFAULT_FANOUT_DEPTH)}
            aria-label="Midnight Oil fan-out depth for ceiling formula"
          />
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
            <DecisionTreeDriverBadge
              researchTier={researchTier}
              /* Residual (pg): project goals+pub refs cost vs remaining budget. */
              promptText={composeDriverPromptText(goalsText, pubRefs)}
            />
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
        <div
          data-testid="moil-budget-mount"
          data-view-format="html"
          data-pub-refs-chars={String(pubRefs.trim().length)}
          data-prompt-includes-pub-refs={String(Boolean(pubRefs.trim()))}
        >
          <ResearchLaunchBudgetPanel
            /* Residual (pa): include pub refs so projection matches create goals. */
            promptText={composeDriverPromptText(goalsText, pubRefs)}
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
        {/* Residual (adx/ady): live recommended ceiling preview before create. */}
        {(() => {
          const pricing = resolveMoilPreviewCombinedUsdPer1m(modelId);
          const previewUsd = estimateMoilRecommendedCeilingUsd({
            durationMinutes,
            fanoutDepth,
            researchTier,
            modelId,
          });
          if (previewUsd == null) return null;
          let fit: "fits" | "may_exceed" | "unknown" = "unknown";
          let remainingAfter: number | null = null;
          if (budgetRemainingUsd != null && Number.isFinite(budgetRemainingUsd)) {
            fit =
              previewUsd <= budgetRemainingUsd + 1e-9 ? "fits" : "may_exceed";
            remainingAfter = budgetRemainingUsd - previewUsd;
          }
          return (
            <div
              className="font-mono text-[11px] space-y-0.5 border border-ink/15 rounded p-2 dark:border-bright/15"
              data-testid="moil-ceiling-preview"
              data-preview-only="true"
              data-pricing-source={pricing.pricing_source}
              data-model-id={String(modelId || "default").trim() || "default"}
              data-combined-usd-per-1m={String(pricing.combined)}
              data-duration-minutes={String(durationMinutes)}
              data-fanout-depth={String(
                Number.isFinite(fanoutDepth) && fanoutDepth > 0
                  ? Math.floor(fanoutDepth)
                  : MOIL_CEILING_DEFAULT_FANOUT_DEPTH,
              )}
              data-research-tier={researchTier}
              data-recommended-usd={String(previewUsd)}
              data-budget-fit={fit}
              data-remaining-after-usd={
                remainingAfter != null ? String(remainingAfter) : ""
              }
              data-tokens-per-minute={String(MOIL_CEILING_TOKENS_PER_MINUTE)}
              data-safety-factor={String(MOIL_CEILING_SAFETY_FACTOR)}
              data-tier-multiplier={String(
                mapResearchTierToCeilingMultiplier(researchTier),
              )}
              role="status"
            >
              <p>
                Preview recommended ceiling ≈{" "}
                <strong data-testid="moil-ceiling-preview-usd">
                  ${previewUsd.toFixed(2)}
                </strong>{" "}
                · duration={durationMinutes}m · fanout=
                {Number.isFinite(fanoutDepth) && fanoutDepth > 0
                  ? Math.floor(fanoutDepth)
                  : MOIL_CEILING_DEFAULT_FANOUT_DEPTH}{" "}
                · tier={formatResearchTierCeilingFactor(researchTier)} · model=
                {String(modelId || "default").trim() || "default"}
              </p>
              <p className="opacity-80">
                {fit === "fits"
                  ? "Fits remaining daily budget (preview)"
                  : fit === "may_exceed"
                    ? "May exceed remaining daily budget (preview · soft gate on create)"
                    : "Remaining budget unknown — cannot assert fit"}
                {remainingAfter != null
                  ? ` · remaining after≈$${remainingAfter.toFixed(2)}`
                  : ""}{" "}
                · create job remains authoritative · rates=
                {pricing.pricing_source}
              </p>
            </div>
          );
        })()}
        <button
          type="submit"
          data-testid="moil-create-recommend-ceiling"
          data-plan-ready={String(createPlanReadiness.plan_ready)}
          data-budget-soft-gate={String(budgetWarn && !forceOverBudget)}
          data-html-first="true"
          disabled={
            busy ||
            !createPlanReadiness.plan_ready ||
            (budgetWarn && !forceOverBudget)
          }
          title={
            !createPlanReadiness.plan_ready
              ? createPlanReadiness.summary
              : budgetWarn && !forceOverBudget
                ? "Over budget — enable force override before create"
                : "Create job and receive recommended price ceiling"
          }
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
          {/* Residual (hn/add): recommended price ceiling metrics + formula transparency. */}
          {(() => {
            // Residual (add): job.fanout_depth preferred; else form fanout (create path);
            // never collapse operator-selected depth to silent default-only.
            const effectiveFanout =
              typeof job.fanout_depth === "number" && job.fanout_depth > 0
                ? Math.floor(job.fanout_depth)
                : Number.isFinite(fanoutDepth) && fanoutDepth > 0
                  ? Math.floor(fanoutDepth)
                  : MOIL_CEILING_DEFAULT_FANOUT_DEPTH;
            const fanoutSource =
              typeof job.fanout_depth === "number" && job.fanout_depth > 0
                ? "job"
                : Number.isFinite(fanoutDepth) && fanoutDepth > 0
                  ? "form"
                  : "default";
            // Residual (aeg): preview vs server recommended match audit.
            const serverRec = Number(job.recommended_price_ceiling_usd);
            const previewMatch =
              lastPreviewCeilingUsd != null &&
              Number.isFinite(serverRec) &&
              Math.abs(lastPreviewCeilingUsd - serverRec) < 0.005;
            return (
          <div
            data-testid="moil-ceiling-metrics"
            data-job-id={job.job_id}
            data-status={job.status}
            data-duration-minutes={String(job.duration_minutes ?? 0)}
            data-goal-count={String((job.goals || []).length)}
            data-grounded-pub-goal-count={String(
              (job.goals || []).filter((g) =>
                String(g || "").startsWith("Ground publication:"),
              ).length,
            )}
            data-model-id={job.model_id || "default"}
            data-research-tier={job.research_tier || researchTier}
            data-recommended-usd={String(job.recommended_price_ceiling_usd)}
            data-approved-usd={
              job.approved_ceiling_usd != null
                ? String(job.approved_ceiling_usd)
                : ""
            }
            data-runnable={String(Boolean(job.runnable))}
            data-fanout-depth={String(effectiveFanout)}
            data-fanout-source={fanoutSource}
            // Residual (aeg): form preview vs authoritative server ceiling.
            data-preview-usd={
              lastPreviewCeilingUsd != null
                ? String(lastPreviewCeilingUsd)
                : ""
            }
            data-preview-matches-server={
              lastPreviewCeilingUsd != null ? String(previewMatch) : "unknown"
            }
            data-view-format="html"
            role="status"
          >
            Ceiling audit · duration={job.duration_minutes}m · goals=
            {(job.goals || []).length} · grounded_pubs=
            {
              (job.goals || []).filter((g) =>
                String(g || "").startsWith("Ground publication:"),
              ).length
            }{" "}
            · fanout={effectiveFanout} · model=
            {job.model_id || "default"} · recommended=$
            {job.recommended_price_ceiling_usd.toFixed(2)}
            {lastPreviewCeilingUsd != null ? (
              <>
                {" "}
                · preview=$
                {lastPreviewCeilingUsd.toFixed(2)}
                {previewMatch ? " · preview=server" : " · preview≠server"}
              </>
            ) : null}
          </div>
            );
          })()}
          {/* Residual (aog): full swarm goal plan on job receipt (create→job audit). */}
          {(job.goals || []).length > 0 ? (
            <div
              className="space-y-1 font-mono text-[11px]"
              data-testid="moil-job-goals-plan"
              data-goal-count={String((job.goals || []).length)}
              data-research-goal-count={String(
                (job.goals || []).filter(
                  (g) => !String(g || "").startsWith("Ground publication:"),
                ).length,
              )}
              data-grounded-pub-goal-count={String(
                (job.goals || []).filter((g) =>
                  String(g || "").startsWith("Ground publication:"),
                ).length,
              )}
              data-view-format="html"
              role="status"
            >
              <p className="opacity-80">
                Job swarm plan · {(job.goals || []).length} goal
                {(job.goals || []).length === 1 ? "" : "s"} (
                {
                  (job.goals || []).filter(
                    (g) => !String(g || "").startsWith("Ground publication:"),
                  ).length
                }{" "}
                research ·{" "}
                {
                  (job.goals || []).filter((g) =>
                    String(g || "").startsWith("Ground publication:"),
                  ).length
                }{" "}
                grounded pubs)
              </p>
              <ol
                className="list-decimal pl-5 space-y-0.5 opacity-90"
                data-testid="moil-job-goals-plan-list"
              >
                {(job.goals || []).map((g, i) => {
                  const text = String(g || "").trim();
                  const grounded = text.startsWith("Ground publication:");
                  return (
                    <li
                      key={`${i}-${text.slice(0, 32)}`}
                      data-testid={`moil-job-goals-plan-item-${i}`}
                      data-goal-index={String(i)}
                      data-grounded-pub={String(grounded)}
                    >
                      {text.length > 200 ? `${text.slice(0, 197)}…` : text}
                    </li>
                  );
                })}
              </ol>
            </div>
          ) : null}
          {/* Residual (pc): grounded publication goals on job receipt. */}
          {(job.goals || []).some((g) =>
            String(g || "").startsWith("Ground publication:"),
          ) ? (
            <ul
              className="list-disc pl-5 font-mono text-[11px] opacity-90"
              data-testid="moil-grounded-pub-goals"
              data-count={String(
                (job.goals || []).filter((g) =>
                  String(g || "").startsWith("Ground publication:"),
                ).length,
              )}
              data-view-format="html"
            >
              {(job.goals || [])
                .filter((g) =>
                  String(g || "").startsWith("Ground publication:"),
                )
                .map((g) => (
                  <li key={g} data-grounded-goal={g}>
                    {g}
                  </li>
                ))}
            </ul>
          ) : null}
          <p
            data-testid="recommended-ceiling"
            data-recommended-usd={String(job.recommended_price_ceiling_usd)}
            data-duration-minutes={String(job.duration_minutes ?? 0)}
          >
            Recommended ceiling:{" "}
            <strong>${job.recommended_price_ceiling_usd.toFixed(2)}</strong>
          </p>
          {/* Residual (md/um): ceiling vs remaining daily budget fit + after-approve projection. */}
          {(() => {
            const rec = job.recommended_price_ceiling_usd;
            let fit: "fits" | "may_exceed" | "unknown" = "unknown";
            let remainingAfter: number | null = null;
            if (budgetRemainingUsd != null && Number.isFinite(budgetRemainingUsd)) {
              fit = rec <= budgetRemainingUsd + 1e-9 ? "fits" : "may_exceed";
              // Residual (um): projected remaining if operator approves this ceiling
              // (soft foresight only — does not spend or invent $0 when unknown).
              remainingAfter = budgetRemainingUsd - rec;
            }
            return (
              <>
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
                <p
                  className="text-[11px] font-mono opacity-80"
                  data-testid="moil-ceiling-remaining-after"
                  data-remaining-after-usd={
                    remainingAfter != null ? String(remainingAfter) : "unknown"
                  }
                  data-recommended-usd={String(rec)}
                  data-remaining-usd={
                    budgetRemainingUsd != null
                      ? String(budgetRemainingUsd)
                      : "unknown"
                  }
                  data-view-format="html"
                  role="status"
                >
                  After approve (projection):{" "}
                  <strong data-testid="moil-ceiling-remaining-after-label">
                    {remainingAfter != null
                      ? `remaining≈$${remainingAfter.toFixed(2)}`
                      : "unknown (remaining budget unset)"}
                  </strong>
                  {remainingAfter != null
                    ? ` · if full ceiling $${rec.toFixed(2)} is spent`
                    : " · never invent $0"}
                </p>
              </>
            );
          })()}
          <p
            className="text-[11px] font-mono opacity-70"
            data-testid="moil-ceiling-formula-note"
            // Residual (ada/add): machine-readable formula constants; fanout
            // prefers job → form → default (operator depth honesty).
            data-tokens-per-minute={String(MOIL_CEILING_TOKENS_PER_MINUTE)}
            data-safety-factor={String(MOIL_CEILING_SAFETY_FACTOR)}
            data-fanout-depth={String(
              typeof job.fanout_depth === "number" && job.fanout_depth > 0
                ? Math.floor(job.fanout_depth)
                : Number.isFinite(fanoutDepth) && fanoutDepth > 0
                  ? Math.floor(fanoutDepth)
                  : MOIL_CEILING_DEFAULT_FANOUT_DEPTH,
            )}
            data-fanout-source={
              typeof job.fanout_depth === "number" && job.fanout_depth > 0
                ? "job"
                : Number.isFinite(fanoutDepth) && fanoutDepth > 0
                  ? "form"
                  : "default"
            }
            data-research-tier={job.research_tier || researchTier || "deep"}
            data-tier-multiplier={String(
              mapResearchTierToCeilingMultiplier(
                job.research_tier || researchTier,
              ),
            )}
            data-view-format="html"
          >
            Formula: duration × tokens/min ({MOIL_CEILING_TOKENS_PER_MINUTE}) ×
            model rates × fanout (
            {typeof job.fanout_depth === "number" && job.fanout_depth > 0
              ? Math.floor(job.fanout_depth)
              : Number.isFinite(fanoutDepth) && fanoutDepth > 0
                ? Math.floor(fanoutDepth)
                : MOIL_CEILING_DEFAULT_FANOUT_DEPTH}
            ) × {MOIL_CEILING_SAFETY_FACTOR} safety × tier multiplier (fast 0.5 ·
            deep 1.0 · wrestle 2.0)
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
              {/* Residual (me/arz): force when ceiling may_exceed remaining budget · CTA soft-gate. */}
              {(() => {
                const rec = Number(job.recommended_price_ceiling_usd);
                const recValid = Number.isFinite(rec) && rec > 0;
                const recMayExceed =
                  recValid && ceilingMayExceedRemaining(rec);
                const recApproveReady =
                  recValid && (!recMayExceed || forceCeilingOverBudget);
                const customAmount = Number(ceilingInput);
                const customValid =
                  Number.isFinite(customAmount) && customAmount > 0;
                const customMayExceed =
                  customValid && ceilingMayExceedRemaining(customAmount);
                const customApproveReady =
                  customValid && (!customMayExceed || forceCeilingOverBudget);
                return (
                  <>
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
                disabled={busy || !recApproveReady}
                data-testid="moil-approve-recommended"
                data-approve-ready={String(recApproveReady)}
                data-may-exceed={String(recMayExceed)}
                data-force-over-budget={String(forceCeilingOverBudget)}
                data-budget-soft-gate={String(recMayExceed && !forceCeilingOverBudget)}
                title={
                  !recValid
                    ? "Recommended ceiling unavailable"
                    : recMayExceed && !forceCeilingOverBudget
                      ? "Recommended ceiling may exceed remaining daily budget — enable force override or lower duration/tier"
                      : "Approve Midnight Oil at recommended price ceiling"
                }
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
                  data-testid="moil-custom-ceiling-input"
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
                  disabled={busy || !customApproveReady}
                  data-testid="moil-approve-custom"
                  data-approve-ready={String(customApproveReady)}
                  data-may-exceed={String(customMayExceed)}
                  data-custom-valid={String(customValid)}
                  data-force-over-budget={String(forceCeilingOverBudget)}
                  data-budget-soft-gate={String(
                    customMayExceed && !forceCeilingOverBudget,
                  )}
                  title={
                    !customValid
                      ? "Enter a positive custom ceiling amount"
                      : customMayExceed && !forceCeilingOverBudget
                        ? "Custom ceiling may exceed remaining daily budget — enable force override or lower the amount"
                        : "Approve Midnight Oil at custom price ceiling"
                  }
                >
                  Approve custom ceiling
                </button>
              </div>
                  </>
                );
              })()}
              {/* Residual (un): custom ceiling remaining-after projection (parity um). */}
              {(() => {
                const amount = Number(ceilingInput);
                const valid = Number.isFinite(amount) && amount > 0;
                let remainingAfter: number | null = null;
                let fit: "fits" | "may_exceed" | "unknown" = "unknown";
                if (
                  valid &&
                  budgetRemainingUsd != null &&
                  Number.isFinite(budgetRemainingUsd)
                ) {
                  remainingAfter = budgetRemainingUsd - amount;
                  fit =
                    amount <= budgetRemainingUsd + 1e-9
                      ? "fits"
                      : "may_exceed";
                } else if (!valid) {
                  fit = "unknown";
                }
                return (
                  <p
                    className="text-[11px] font-mono opacity-80 w-full"
                    data-testid="moil-custom-ceiling-remaining-after"
                    data-remaining-after-usd={
                      remainingAfter != null
                        ? String(remainingAfter)
                        : "unknown"
                    }
                    data-custom-usd={valid ? String(amount) : "invalid"}
                    data-remaining-usd={
                      budgetRemainingUsd != null
                        ? String(budgetRemainingUsd)
                        : "unknown"
                    }
                    data-fit={fit}
                    data-view-format="html"
                    role="status"
                  >
                    Custom after approve (projection):{" "}
                    <strong data-testid="moil-custom-ceiling-remaining-after-label">
                      {!valid
                        ? "enter a positive ceiling"
                        : remainingAfter != null
                          ? `remaining≈$${remainingAfter.toFixed(2)}`
                          : "unknown (remaining budget unset)"}
                    </strong>
                    {valid && remainingAfter != null
                      ? ` · if full custom $${amount.toFixed(2)} is spent`
                      : valid
                        ? " · never invent $0"
                        : ""}
                  </p>
                );
              })()}
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
                    data-runnable={String(Boolean(job.runnable))}
                    data-run-ready={String(
                      Boolean(job.runnable) &&
                        (job.status === "approved" || job.status === "running"),
                    )}
                    data-job-status={job.status}
                    data-l4-live-step="deferred"
                    data-offline-worker="true"
                    disabled={
                      busy ||
                      !job.runnable ||
                      (job.status !== "approved" && job.status !== "running")
                    }
                    title={
                      !job.runnable
                        ? "Job not runnable — approve a price ceiling first"
                        : job.status === "running"
                          ? "Continue offline worker step (L4 live multi-provider deferred)"
                          : "Run offline worker (stub steps · L4 live deferred · never invent live swarm)"
                    }
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
              {/* Residual (hw/ot): machine-readable offline vs live swarm run metrics. */}
              <div
                data-testid="moil-run-metrics"
                data-status={runResult.status ?? ""}
                data-spent-usd={String(runResult.spent_usd ?? 0)}
                data-spawn-count={String(runResult.spawn_ids?.length ?? 0)}
                data-goals-total={String(runResult.goals_total ?? 0)}
                data-offline={String(Boolean(runResult.offline))}
                data-live-step={String(Boolean(runResult.live_step))}
                data-recent-ring-count={String(recentSpawnIds.length)}
                data-recent-ring-has-run-spawns={String(
                  (runResult.spawn_ids || [])
                    .map((x) => String(x || "").trim())
                    .filter(Boolean)
                    .every((sid) => recentSpawnIds.includes(sid)) &&
                    (runResult.spawn_ids || []).filter(Boolean).length > 0,
                )}
                data-view-format="html"
                role="status"
              >
                Midnight Oil run · status={runResult.status} · spent=$
                {Number(runResult.spent_usd ?? 0).toFixed(4)} · spawns=
                {runResult.spawn_ids?.length ?? 0}/{runResult.goals_total ?? 0} ·
                offline={String(Boolean(runResult.offline))} · recent_ring=
                {recentSpawnIds.length}
              </div>
              {/* Residual (ot): honesty — offline swarm spawns join collective ring. */}
              {(runResult.spawn_ids || []).filter(Boolean).length > 0 ? (
                <p
                  className="text-[11px] font-mono opacity-80"
                  data-testid="moil-run-recent-ring-status"
                  data-spawn-count={String(
                    (runResult.spawn_ids || []).filter(Boolean).length,
                  )}
                  data-recent-ring-count={String(recentSpawnIds.length)}
                  role="status"
                >
                  Spawn ids remembered in session recent_ring for collective
                  multi-select (Write / hosted / ResearchThis / deposit
                  collective) even if auto-deposit is off.
                </p>
              ) : null}
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
              data-html-first="true"
              data-seamless-moil-deposit="true"
              data-l4-live-step="deferred"
            >
              <h3 className="font-medium">Deposit result</h3>
              {/* Residual (hx/any): machine-readable deposit land metrics + HTML-first. */}
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
                data-html-first="true"
                data-seamless-moil-deposit="true"
                data-deposit-html-present={String(
                  Boolean(String(deposit.html || "").trim()),
                )}
                data-research-tier={(
                  job.research_tier ||
                  researchTier ||
                  "deep"
                )
                  .toString()
                  .toLowerCase()}
                data-l4-live-step="deferred"
                role="status"
              >
                Midnight Oil deposit · document={deposit.document_id} · twins=
                {deposit.twin_count ?? 0} · usage=
                {String(Boolean(deposit.usage_recorded))} · progress_seeded=
                {String(Boolean(deposit.progress_seeded))}
                {" · HTML-first · L4 live deferred"}
              </div>
              {/* Residual (any): deposit-local competitive DR honesty (parity progress aim). */}
              <p
                className="text-[11px] font-mono space-x-2"
                data-testid="moil-deposit-competitive-links"
                data-view-format="html"
                data-l4-live-step="deferred"
              >
                <a
                  href="/settings#settings-competitive-dr-scorecard"
                  data-testid="moil-deposit-competitive-scorecard-link"
                  className="underline opacity-80 hover:opacity-100"
                  title="Settings competitive deep-research scorecard (MO deposit offline land · L4 live deferred)"
                >
                  Settings · competitive DR scorecard
                </a>
                <a
                  href="/docs/campaigns/2026-07-09-research-reading-spine/FUTURE-AGENT-SPEC-competitive-deep-research-quality.md"
                  data-testid="moil-deposit-competitive-dr-future-agent-link"
                  className="underline opacity-80 hover:opacity-100"
                  title="FUTURE-AGENT competitive deep-research quality brief (L4 MO live dual-gate)"
                >
                  FUTURE · competitive DR brief
                </a>
                <a
                  href="/docs/campaigns/2026-07-09-research-reading-spine/DUAL-GATE-L1-L4-OPERATOR-CHECKLIST.md#l4-moil"
                  data-testid="moil-deposit-dual-gate-l4-link"
                  className="underline opacity-80 hover:opacity-100"
                  title="Dual-gate L4 Midnight Oil live-step checklist (prep only · deposit is offline HTML land)"
                >
                  Dual-gate L4 MO checklist
                </a>
              </p>
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
              {/* Residual (oo): recursive note-taker UI on deposit HTML asset. */}
              {depositParentAssetId ? (
                <section
                  className="space-y-2 border-t border-ink/10 pt-2 dark:border-bright/10"
                  data-testid="moil-deposit-twins-mount"
                  data-view-format="html"
                  data-asset-id={depositParentAssetId}
                  data-research-tier={
                    (job.research_tier || researchTier || "deep")
                      .toString()
                      .toLowerCase()
                  }
                >
                  <p className="text-[10px] font-mono uppercase tracking-wider opacity-70">
                    Twin notes (deposit asset)
                  </p>
                  <div
                    data-testid="moil-deposit-twins-refresh"
                    data-refresh-key={String(contextRefreshKey)}
                  >
                    <TwinNotesPanel
                      key={`twins-${depositParentAssetId}-${contextRefreshKey}`}
                      assetId={depositParentAssetId}
                      spawnId={depositSpawnIds[0] ?? null}
                      autoLoad
                      autoSeedIfEmpty
                      autoPromoteAfterLoad
                      onPromoted={onContextNeedsRefresh}
                      seedTitle={`Midnight Oil · ${deposit.job_id}`}
                      seedBodyText={
                        deposit.html
                          ? deposit.html.replace(/<[^>]+>/g, " ").slice(0, 500)
                          : deposit.job_id
                      }
                      researchTier={
                        (() => {
                          const tier = (
                            job.research_tier ||
                            researchTier ||
                            "deep"
                          )
                            .toString()
                            .toLowerCase();
                          return tier === "fast" ||
                            tier === "deep" ||
                            tier === "wrestle"
                            ? tier
                            : "deep";
                        })()
                      }
                    />
                  </div>
                </section>
              ) : null}
              {/* Residual (op): research context pack over deposit twin substrate. */}
              {depositParentAssetId ? (
                <section
                  className="space-y-2 border-t border-ink/10 pt-2 dark:border-bright/10"
                  data-testid="moil-deposit-context-mount"
                  data-view-format="html"
                  data-asset-id={depositParentAssetId}
                  data-research-tier={
                    (() => {
                      const tier = (
                        job.research_tier ||
                        researchTier ||
                        "deep"
                      )
                        .toString()
                        .toLowerCase();
                      return tier === "fast" ||
                        tier === "deep" ||
                        tier === "wrestle"
                        ? tier
                        : "deep";
                    })()
                  }
                  data-seamless-moil-context="true"
                >
                  <p className="text-[10px] font-mono uppercase tracking-wider opacity-70">
                    Research context (deposit asset)
                  </p>
                  <div
                    data-testid="moil-deposit-context-refresh"
                    data-refresh-key={String(contextRefreshKey)}
                  >
                    {/* Residual (amp): job depth posture into intelligent context. */}
                    <ResearchContextPanel
                      key={`ctx-${depositParentAssetId}-${contextRefreshKey}`}
                      assetId={depositParentAssetId}
                      spawnId={depositSpawnIds[0] ?? null}
                      autoLoad
                      researchTier={
                        (() => {
                          const tier = (
                            job.research_tier ||
                            researchTier ||
                            "deep"
                          )
                            .toString()
                            .toLowerCase();
                          return tier === "fast" ||
                            tier === "deep" ||
                            tier === "wrestle"
                            ? tier
                            : "deep";
                        })()
                      }
                    />
                  </div>
                </section>
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
                    openSpawnIds={openSpawnIds}
                    preferredSpawnId={depositSpawnIds[0] ?? null}
                    onDocMerged={onContextNeedsRefresh}
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
              {/* Residual (db/ew/ata/ate): open deposit as hosted HTML reading window
                  via pure moilDepositHtmlReadiness (never invent open when
                  view_format≠html / empty body / missing document_id). */}
              {(() => {
                // Residual (ate): pure deposit HTML open readiness (parity plan ara).
                const depositOpen = moilDepositHtmlReadiness({
                  view_format: deposit.view_format,
                  html: deposit.html,
                  document_id: deposit.document_id,
                });
                const depositHtmlReady = depositOpen.deposit_html_ready;
                const depositOpenTitle = depositOpen.open_title;
                return (
              <div
                className="flex flex-wrap items-center gap-2"
                data-testid="moil-deposit-open-actions"
                data-deposit-html-ready={String(depositHtmlReady)}
                data-deposit-open-summary={depositOpen.summary}
                data-view-format={deposit.view_format || ""}
                data-html-first="true"
                data-l4-live-step="deferred"
              >
                <button
                  type="button"
                  data-testid="moil-open-deposit-window"
                  data-view-format="html"
                  data-html-first="true"
                  data-window-mode="floating"
                  data-deposit-html-ready={String(depositHtmlReady)}
                  data-document-id={deposit.document_id ?? ""}
                  data-l4-live-step="deferred"
                  disabled={!depositHtmlReady}
                  title={depositOpenTitle}
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
                  data-view-format="html"
                  data-html-first="true"
                  data-window-mode="full"
                  data-deposit-html-ready={String(depositHtmlReady)}
                  data-document-id={deposit.document_id ?? ""}
                  data-l4-live-step="deferred"
                  disabled={!depositHtmlReady}
                  title={depositOpenTitle}
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
                {/* Residual (fo/pz/aep): Write dual handoff + seamless MO deposit path. */}
                {depositWriteHref ? (
                  <a
                    href={depositWriteHref}
                    data-testid="moil-open-write"
                    data-view-format="html"
                    data-html-first="true"
                    data-deposit-html-ready={String(depositHtmlReady)}
                    data-has-twin-seed={
                      depositWriteHref.includes("twin_seed=") ? "1" : "0"
                    }
                    // Residual (ack): body honesty on twin_seed (parity marketplace acf).
                    data-write-seed-has-body={String(
                      Boolean(
                        deposit.view_format === "html" &&
                          plainTextFromHtml(deposit.html || "").trim(),
                      ),
                    )}
                    // Residual (aep): autonomous MO deposit → Write note-taker path.
                    data-document-id={deposit.document_id ?? ""}
                    data-asset-id={deposit.asset_id ?? ""}
                    data-job-id={deposit.job_id ?? ""}
                    data-seamless-moil-write={String(
                      Boolean(
                        deposit.view_format === "html" &&
                          Boolean(deposit.document_id),
                      ),
                    )}
                    data-seamless-host-write={String(
                      Boolean(
                        deposit.view_format === "html" &&
                          Boolean(deposit.document_id),
                      ),
                    )}
                    className="rounded border border-ink/30 px-2 py-1 text-[11px] font-mono underline hover:bg-ink/5 dark:border-bright/30"
                    title="Open Write with Midnight Oil deposit as HTML draft + twin_seed (seamless MO deposit · seeds note-taker when empty)"
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
                );
              })()}
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
