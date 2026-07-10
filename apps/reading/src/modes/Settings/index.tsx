import { useEffect, useMemo, useState } from "react";
import {
  notDiamondBenchDelta,
  notDiamondBenchDeltaLabel,
  notDiamondDriverDelta,
  notDiamondDriverDeltaLabel,
} from "../../lib/notDiamondDriverDelta";
import {
  groupProposedTasksByClass,
  primaryFeedSourceFromBySource,
  rankedFeedSourcesFromBySource,
} from "../../lib/suiteProposalTasks";
import {
  countWriteSeedKnownSources,
  isWriteSeedFeedSource,
} from "../../lib/writeSeedFeedSources";
import { useViewportTier } from "../../workspace/useViewportTier";
import LemonCard from "../../components/lemon/LemonCard";
import {
  applyDepthTier,
  approveAntiekBenchSuiteProposal,
  clearDecisionTreeSelection,
  estimatePromptCost,
  fetchAntiekBenchDogfoodFixtures,
  fetchAntiekBenchLeaderboard,
  fetchAntiekBenchSuiteProposal,
  fetchAntiekBenchUsageSummary,
  fetchDecisionTreeSelection,
  fetchDepthTiers,
  fetchNotDiamondAdvisory,
  fetchRegisteredModels,
  fetchSettingsBudget,
  fetchSettingsModels,
  installDecisionTreeSelection,
  registerSettingsModel,
  runAntiekBenchOffline,
  type AntiekBenchDogfoodFixturesResponse,
  type AntiekBenchLeaderboardResponse,
  type AntiekBenchRunOfflineResponse,
  type AntiekBenchSuiteApproveResponse,
  type AntiekBenchSuiteProposalResponse,
  type AntiekBenchUsageSummaryResponse,
  type BudgetResponse,
  type DecisionTreeSelectionResponse,
  type DepthTierResponse,
  type ModelRow,
  type NotDiamondAdvisoryResponse,
  type PromptCostEstimateResponse,
  type RegisteredModelsResponse,
} from "../../api/settings";
import {
  fetchHydrateLiveStatus,
  fetchTwinSeedLiveStatus,
  type HydrateLiveStatusResponse,
  type TwinSeedLiveStatusResponse,
} from "../../api/engagement";
import {
  fetchMidnightOilLiveStepStatus,
  type MidnightOilLiveStepStatusResponse,
} from "../../api/midnightOil";

/**
 * Residual (rl): NotDiamond advisory vs installed decision-tree driver delta
 * (weekly honesty; advisory never auto-applies).
 * Operator Settings — model inventory + budget + prompt projection (SPR-01)
 * + decision-tree driver install (process-local registry)
 * + Antiek-bench weekly usage summary (recorded engagement outcomes)
 * + Antiek-bench suite rewrite proposal (proposed only; not auto-promoted)
 * + competitive dogfood fixtures listing (never auto-promoted)
 * + offline dogfood suite run → populate weekly leaderboard (residual bo).
 * + Residual (hq): hydrate live-injector readiness (arxiv/substack offline-honest default).
 * + Residual (hs): twin seed live readiness (force_offline UI; dual-gate env).
 *
 * Honesty: spent/pricing may be unknown; UI never invents $0.00 when the
 * ledger or rate table is unset. Cost projection stays on #440 API.
 * Residual (wb): remaining-after-prompt on decision-tree mini estimate + full
 * prompt-cost-projection panel (parity launch wa / badge pg / MO um).
 */
export default function Settings() {
  const tier = useViewportTier();
  const isDark =
    typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-color-scheme: dark)").matches;
  const reduceMotion =
    typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  const [models, setModels] = useState<ModelRow[] | null>(null);
  const [modelsError, setModelsError] = useState<string | null>(null);
  const [budget, setBudget] = useState<BudgetResponse | null>(null);
  const [budgetError, setBudgetError] = useState<string | null>(null);
  const [inputChars, setInputChars] = useState(2000);
  const [outTokens, setOutTokens] = useState(500);
  const [estimate, setEstimate] = useState<PromptCostEstimateResponse | null>(
    null,
  );
  const [estimateError, setEstimateError] = useState<string | null>(null);
  const [estimating, setEstimating] = useState(false);
  const [selectedProvider, setSelectedProvider] = useState<string>("");
  const [selectedModel, setSelectedModel] = useState<string>("");
  const [tree, setTree] = useState<DecisionTreeSelectionResponse | null>(null);
  const [treeError, setTreeError] = useState<string | null>(null);
  const [treeBusy, setTreeBusy] = useState(false);
  /**
   * Residual (adu): client install provenance for decision-tree driver.
   * Tracks whether the active install came from manual pick, overall
   * leaderboard recommend, best-by-task (ads), or NotDiamond advisory.
   * Never implies auto-routing — honesty chrome only.
   */
  const [driverInstallProvenance, setDriverInstallProvenance] = useState<{
    source:
      | "manual"
      | "leaderboard_recommended"
      | "leaderboard_task"
      | "notdiamond"
      | null;
    task_class: string | null;
  }>({ source: null, task_class: null });
  const [usage, setUsage] = useState<AntiekBenchUsageSummaryResponse | null>(
    null,
  );
  const [usageError, setUsageError] = useState<string | null>(null);
  const [usageBusy, setUsageBusy] = useState(false);
  const [suiteProposal, setSuiteProposal] =
    useState<AntiekBenchSuiteProposalResponse | null>(null);
  const [suiteProposalError, setSuiteProposalError] = useState<string | null>(
    null,
  );
  const [suiteProposalBusy, setSuiteProposalBusy] = useState(false);
  const [suiteApprove, setSuiteApprove] =
    useState<AntiekBenchSuiteApproveResponse | null>(null);
  const [suiteApproveBusy, setSuiteApproveBusy] = useState(false);
  const [nd, setNd] = useState<NotDiamondAdvisoryResponse | null>(null);
  const [ndError, setNdError] = useState<string | null>(null);
  // Residual (he): explicit weekly refresh of NotDiamond advisory (never authority).
  const [ndBusy, setNdBusy] = useState(false);
  // Residual (hq): arxiv/substack hydrate injector readiness (offline default).
  const [hydrateLive, setHydrateLive] =
    useState<HydrateLiveStatusResponse | null>(null);
  const [hydrateLiveError, setHydrateLiveError] = useState<string | null>(null);
  const [hydrateLiveBusy, setHydrateLiveBusy] = useState(false);
  // Residual (hs): twin seed note_taker readiness (offline default).
  const [twinSeedLive, setTwinSeedLive] =
    useState<TwinSeedLiveStatusResponse | null>(null);
  const [twinSeedLiveError, setTwinSeedLiveError] = useState<string | null>(
    null,
  );
  const [twinSeedLiveBusy, setTwinSeedLiveBusy] = useState(false);
  /** Residual (sz): Midnight Oil L4 live-step readiness (offline-honest). */
  const [moilLive, setMoilLive] =
    useState<MidnightOilLiveStepStatusResponse | null>(null);
  const [moilLiveError, setMoilLiveError] = useState<string | null>(null);
  const [moilLiveBusy, setMoilLiveBusy] = useState(false);
  const [depth, setDepth] = useState<DepthTierResponse | null>(null);
  const [depthError, setDepthError] = useState<string | null>(null);
  const [depthBusy, setDepthBusy] = useState(false);
  const [dogfood, setDogfood] =
    useState<AntiekBenchDogfoodFixturesResponse | null>(null);
  const [dogfoodError, setDogfoodError] = useState<string | null>(null);
  const [dogfoodBusy, setDogfoodBusy] = useState(false);
  const [leaderboard, setLeaderboard] =
    useState<AntiekBenchLeaderboardResponse | null>(null);
  const [leaderboardError, setLeaderboardError] = useState<string | null>(null);
  const [leaderboardBusy, setLeaderboardBusy] = useState(false);
  const [offlineRun, setOfflineRun] =
    useState<AntiekBenchRunOfflineResponse | null>(null);
  const [offlineRunBusy, setOfflineRunBusy] = useState(false);
  const [offlineRunError, setOfflineRunError] = useState<string | null>(null);
  const [leaderboardWeek, setLeaderboardWeek] = useState(() => {
    // ISO-like week id: YYYY-Www (local calendar approximation)
    const d = new Date();
    const onejan = new Date(d.getFullYear(), 0, 1);
    const week = Math.ceil(
      ((d.getTime() - onejan.getTime()) / 86400000 + onejan.getDay() + 1) / 7,
    );
    return `${d.getFullYear()}-W${String(week).padStart(2, "0")}`;
  });
  const [registered, setRegistered] =
    useState<RegisteredModelsResponse | null>(null);
  const [registeredError, setRegisteredError] = useState<string | null>(null);
  const [registeredBusy, setRegisteredBusy] = useState(false);
  const [addModelId, setAddModelId] = useState("");
  const [addProviderId, setAddProviderId] = useState("");
  const [addSelectDriver, setAddSelectDriver] = useState(true);

  /** Residual (qa): primary by_source that drove this week's suite rewrite. */
  const primaryRewriteFeed = useMemo(
    () => primaryFeedSourceFromBySource(usage?.by_source),
    [usage?.by_source],
  );
  const rankedRewriteFeeds = useMemo(
    () => rankedFeedSourcesFromBySource(usage?.by_source),
    [usage?.by_source],
  );
  /**
   * Residual (ru/ry): known feed sources that are Write twin_seed paths.
   * Prefer substrate write_seed_known_count (ry) when present.
   */
  const writeSeedKnownCount = useMemo(() => {
    if (
      usage != null &&
      typeof usage.write_seed_known_count === "number" &&
      Number.isFinite(usage.write_seed_known_count)
    ) {
      return usage.write_seed_known_count;
    }
    return countWriteSeedKnownSources(usage?.known_sources);
  }, [usage?.known_sources, usage?.write_seed_known_count]);

  /** Residual (rl): advisory suggestion vs installed driver (never auto-route). */
  const ndDriverDelta = useMemo(
    () =>
      notDiamondDriverDelta({
        suggestedModelId: nd?.suggested_model_id,
        installedModelId: tree?.model_id,
      }),
    [nd?.suggested_model_id, tree?.model_id],
  );

  /**
   * Residual (ade): NotDiamond weekly pick vs Antiek-bench weekly recommended
   * (both advisory only — never auto-route dispatch).
   */
  const ndBenchDelta = useMemo(
    () =>
      notDiamondBenchDelta({
        ndSuggestedModelId: nd?.suggested_model_id,
        benchRecommendedModelId: leaderboard?.recommended_model_id,
      }),
    [nd?.suggested_model_id, leaderboard?.recommended_model_id],
  );

  /**
   * Residual (sp): honor Settings deep-links (#decision-tree-panel,
   * #twin-seed-live-status, #hydrate-live-status, #notdiamond-advisory,
   * #prompt-cost-projection) after SPA navigation.
   */
  useEffect(() => {
    const scrollToHash = () => {
      if (typeof window === "undefined") return;
      const raw = (window.location.hash || "").replace(/^#/, "").trim();
      if (!raw) return;
      const el = document.getElementById(raw);
      if (!el) return;
      try {
        el.scrollIntoView({ behavior: "smooth", block: "start" });
      } catch {
        el.scrollIntoView();
      }
    };
    // Defer until panels paint (async loads may remount layout).
    const t0 = window.setTimeout(scrollToHash, 0);
    const t1 = window.setTimeout(scrollToHash, 250);
    window.addEventListener("hashchange", scrollToHash);
    return () => {
      window.clearTimeout(t0);
      window.clearTimeout(t1);
      window.removeEventListener("hashchange", scrollToHash);
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const m = await fetchSettingsModels();
        if (!cancelled) {
          setModels(m.models);
          const firstReady = m.models.find((r) => r.ready && r.primary_model);
          if (firstReady?.primary_model) {
            setSelectedProvider(firstReady.provider_id);
            setSelectedModel(firstReady.primary_model);
          }
        }
      } catch (e) {
        if (!cancelled)
          setModelsError(e instanceof Error ? e.message : String(e));
      }
      try {
        const b = await fetchSettingsBudget();
        if (!cancelled) setBudget(b);
      } catch (e) {
        if (!cancelled)
          setBudgetError(e instanceof Error ? e.message : String(e));
      }
      try {
        const t = await fetchDecisionTreeSelection();
        if (!cancelled) {
          setTree(t);
          if (t.installed && t.model_id) {
            setSelectedModel(t.model_id);
            if (t.provider_id) setSelectedProvider(t.provider_id);
          }
        }
      } catch (e) {
        if (!cancelled)
          setTreeError(e instanceof Error ? e.message : String(e));
      }
      try {
        const u = await fetchAntiekBenchUsageSummary({ includeHtml: true });
        if (!cancelled) setUsage(u);
      } catch (e) {
        if (!cancelled)
          setUsageError(e instanceof Error ? e.message : String(e));
      }
      try {
        const p = await fetchAntiekBenchSuiteProposal({ includeHtml: true });
        if (!cancelled) setSuiteProposal(p);
      } catch (e) {
        if (!cancelled)
          setSuiteProposalError(e instanceof Error ? e.message : String(e));
      }
      try {
        // Residual (hq): publication hydrate injector readiness (offline default).
        const h = await fetchHydrateLiveStatus();
        if (!cancelled) {
          if (h.view_format !== "html") {
            throw new Error("hydrate live status view_format must be html");
          }
          setHydrateLive(h);
        }
      } catch (e) {
        if (!cancelled)
          setHydrateLiveError(e instanceof Error ? e.message : String(e));
      }
      try {
        // Residual (hs): twin seed live readiness (panels force_offline).
        const ts = await fetchTwinSeedLiveStatus();
        if (!cancelled) {
          if (ts.view_format !== "html") {
            throw new Error("twin seed live status view_format must be html");
          }
          setTwinSeedLive(ts);
        }
      } catch (e) {
        if (!cancelled)
          setTwinSeedLiveError(e instanceof Error ? e.message : String(e));
      }
      try {
        // Residual (sz): MO live-step readiness (never enables live worker).
        const mo = await fetchMidnightOilLiveStepStatus();
        if (!cancelled) {
          if (mo.view_format !== "html") {
            throw new Error("moil live-step status view_format must be html");
          }
          setMoilLive(mo);
        }
      } catch (e) {
        if (!cancelled)
          setMoilLiveError(e instanceof Error ? e.message : String(e));
      }
      try {
        const n = await fetchNotDiamondAdvisory({
          includeHtml: true,
          weekId: leaderboardWeek,
        });
        if (!cancelled) setNd(n);
      } catch (e) {
        if (!cancelled) setNdError(e instanceof Error ? e.message : String(e));
      }
      try {
        const d = await fetchDepthTiers({ includeHtml: true });
        if (!cancelled) {
          setDepth(d);
          // Apply projection hints into cost estimator defaults when present.
          const hints = d.projection_hints;
          if (hints?.input_chars != null) setInputChars(hints.input_chars);
          if (hints?.expected_output_tokens != null)
            setOutTokens(hints.expected_output_tokens);
        }
      } catch (e) {
        if (!cancelled)
          setDepthError(e instanceof Error ? e.message : String(e));
      }
      try {
        const df = await fetchAntiekBenchDogfoodFixtures({
          includeHtml: true,
        });
        if (!cancelled) setDogfood(df);
      } catch (e) {
        if (!cancelled)
          setDogfoodError(e instanceof Error ? e.message : String(e));
      }
      try {
        const lb = await fetchAntiekBenchLeaderboard({
          weekId: leaderboardWeek,
          includeHtml: true,
        });
        if (!cancelled) setLeaderboard(lb);
      } catch (e) {
        if (!cancelled)
          setLeaderboardError(e instanceof Error ? e.message : String(e));
      }
      try {
        const rm = await fetchRegisteredModels();
        if (!cancelled) setRegistered(rm);
      } catch (e) {
        if (!cancelled)
          setRegisteredError(e instanceof Error ? e.message : String(e));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [leaderboardWeek]);

  async function onRegisterModel() {
    if (!addModelId.trim() || !addProviderId.trim()) {
      setRegisteredError("model_id and provider_id are required");
      return;
    }
    setRegisteredBusy(true);
    setRegisteredError(null);
    try {
      const rm = await registerSettingsModel({
        model_id: addModelId.trim(),
        provider_id: addProviderId.trim(),
        select: addSelectDriver,
      });
      if (rm.view_format !== "html") {
        throw new Error("registered models view_format must be html");
      }
      setRegistered(rm);
      if (addSelectDriver) {
        setSelectedModel(addModelId.trim());
        setSelectedProvider(addProviderId.trim());
      }
    } catch (e) {
      setRegisteredError(e instanceof Error ? e.message : String(e));
    } finally {
      setRegisteredBusy(false);
    }
  }

  async function onRefreshDogfood() {
    setDogfoodBusy(true);
    setDogfoodError(null);
    try {
      const df = await fetchAntiekBenchDogfoodFixtures({ includeHtml: true });
      if (df.view_format !== "html") {
        throw new Error("dogfood fixtures view_format must be html");
      }
      if (df.auto_promoted) {
        throw new Error("dogfood fixtures must not auto-promote");
      }
      setDogfood(df);
    } catch (e) {
      setDogfoodError(e instanceof Error ? e.message : String(e));
    } finally {
      setDogfoodBusy(false);
    }
  }

  async function onRefreshLeaderboard() {
    setLeaderboardBusy(true);
    setLeaderboardError(null);
    try {
      const lb = await fetchAntiekBenchLeaderboard({
        weekId: leaderboardWeek,
        includeHtml: true,
      });
      if (lb.view_format !== "html") {
        throw new Error("leaderboard view_format must be html");
      }
      setLeaderboard(lb);
    } catch (e) {
      setLeaderboardError(e instanceof Error ? e.message : String(e));
    } finally {
      setLeaderboardBusy(false);
    }
  }

  async function onRunOfflineDogfood() {
    setOfflineRunBusy(true);
    setOfflineRunError(null);
    setLeaderboardError(null);
    try {
      const out = await runAntiekBenchOffline({
        weekId: leaderboardWeek,
        includeHtml: true,
      });
      if (out.view_format !== "html") {
        throw new Error("offline run view_format must be html");
      }
      if (!out.offline) {
        throw new Error("offline run must report offline=true");
      }
      if (out.auto_promoted) {
        throw new Error("offline run must not auto-promote");
      }
      setOfflineRun(out);
      // Refresh leaderboard from store so install-recommended appears.
      if (out.leaderboard && out.leaderboard.view_format === "html") {
        setLeaderboard(out.leaderboard as AntiekBenchLeaderboardResponse);
      } else {
        await onRefreshLeaderboard();
      }
      // Residual (dv/dx): dogfood usage events → refresh suite proposal + usage summary
      // (proposed only; never auto-promoted).
      try {
        const p = await fetchAntiekBenchSuiteProposal({ includeHtml: true });
        if (p.view_format !== "html") {
          throw new Error("suite proposal view_format must be html");
        }
        if (p.auto_promoted) {
          throw new Error("suite proposal must not auto-promote");
        }
        setSuiteProposal(p);
        setSuiteProposalError(null);
      } catch (pe) {
        // Non-fatal: offline run still succeeded; proposal refresh is best-effort.
        setSuiteProposalError(
          pe instanceof Error ? pe.message : String(pe),
        );
      }
      try {
        const u = await fetchAntiekBenchUsageSummary({ includeHtml: true });
        setUsage(u);
        setUsageError(null);
      } catch (ue) {
        setUsageError(ue instanceof Error ? ue.message : String(ue));
      }
      // Residual (dy): refresh NotDiamond advisory from new week leaderboard.
      // Advisory only — never dispatch authority; install remains operator-gated.
      try {
        const n = await fetchNotDiamondAdvisory({
          includeHtml: true,
          weekId: leaderboardWeek,
        });
        if (n.notdiamond_is_dispatch_authority) {
          throw new Error(
            "NotDiamond reported dispatch authority — refusing to surface as router",
          );
        }
        setNd(n);
        setNdError(null);
      } catch (ne) {
        setNdError(ne instanceof Error ? ne.message : String(ne));
      }
    } catch (e) {
      setOfflineRunError(e instanceof Error ? e.message : String(e));
    } finally {
      setOfflineRunBusy(false);
    }
  }

  /** Residual (hq): refresh hydrate injector readiness (never enables network). */
  async function onRefreshHydrateLiveStatus() {
    setHydrateLiveBusy(true);
    setHydrateLiveError(null);
    try {
      const h = await fetchHydrateLiveStatus();
      if (h.view_format !== "html") {
        throw new Error("hydrate live status view_format must be html");
      }
      setHydrateLive(h);
    } catch (e) {
      setHydrateLiveError(e instanceof Error ? e.message : String(e));
    } finally {
      setHydrateLiveBusy(false);
    }
  }

  /** Residual (hs): refresh twin seed live readiness (never installs injector). */
  async function onRefreshTwinSeedLiveStatus() {
    setTwinSeedLiveBusy(true);
    setTwinSeedLiveError(null);
    try {
      const ts = await fetchTwinSeedLiveStatus();
      if (ts.view_format !== "html") {
        throw new Error("twin seed live status view_format must be html");
      }
      setTwinSeedLive(ts);
    } catch (e) {
      setTwinSeedLiveError(e instanceof Error ? e.message : String(e));
    } finally {
      setTwinSeedLiveBusy(false);
    }
  }

  /** Residual (sz): refresh MO live-step readiness (never enables live worker). */
  async function onRefreshMoilLiveStepStatus() {
    setMoilLiveBusy(true);
    setMoilLiveError(null);
    try {
      const mo = await fetchMidnightOilLiveStepStatus();
      if (mo.view_format !== "html") {
        throw new Error("moil live-step status view_format must be html");
      }
      setMoilLive(mo);
    } catch (e) {
      setMoilLiveError(e instanceof Error ? e.message : String(e));
    } finally {
      setMoilLiveBusy(false);
    }
  }

  /** Residual (he): refresh NotDiamond advisory for the active week_id. */
  async function onRefreshNotDiamondAdvisory() {
    setNdBusy(true);
    setNdError(null);
    try {
      const n = await fetchNotDiamondAdvisory({
        includeHtml: true,
        weekId: leaderboardWeek.trim() || undefined,
      });
      if (n.notdiamond_is_dispatch_authority) {
        throw new Error(
          "NotDiamond reported dispatch authority — refusing to surface as router",
        );
      }
      if (n.view_format !== "html") {
        throw new Error("NotDiamond advisory view_format must be html");
      }
      setNd(n);
    } catch (e) {
      setNdError(e instanceof Error ? e.message : String(e));
    } finally {
      setNdBusy(false);
    }
  }

  async function onInstallNotDiamondAdvisory() {
    if (!nd?.suggested_model_id) {
      setNdError("No advisory suggestion to install");
      return;
    }
    if (nd.notdiamond_is_dispatch_authority) {
      setNdError("Refusing install: NotDiamond must never be dispatch authority");
      return;
    }
    setTreeBusy(true);
    setTreeError(null);
    setNdError(null);
    try {
      const provider =
        nd.suggested_provider_id ||
        selectedProvider ||
        models?.find((m) => m.ready)?.provider_id ||
        models?.[0]?.provider_id ||
        "offline-stub";
      const mid = nd.suggested_model_id;
      const result = await installDecisionTreeSelection({
        model_id: mid,
        provider_id: provider,
      });
      setTree(result);
      setSelectedModel(mid);
      setSelectedProvider(provider);
      // Residual (adu): NotDiamond advisory install provenance (never authority).
      setDriverInstallProvenance({ source: "notdiamond", task_class: null });
    } catch (e) {
      setNdError(e instanceof Error ? e.message : String(e));
      setTreeError(e instanceof Error ? e.message : String(e));
    } finally {
      setTreeBusy(false);
    }
  }

  /**
   * Residual (ads): advisory install of a leaderboard model (overall or
   * best-by-task) into the decision-tree. Never auto-routes dispatch.
   */
  async function onInstallLeaderboardModelAsDriver(
    modelId: string,
    opts?: { taskClass?: string | null },
  ) {
    const mid = String(modelId || "").trim();
    if (!mid) {
      setLeaderboardError("No model id to install");
      return;
    }
    setTreeBusy(true);
    setTreeError(null);
    setLeaderboardError(null);
    try {
      // Advisory install: use selected provider if set, else first ready provider.
      const provider =
        selectedProvider ||
        models?.find((m) => m.ready)?.provider_id ||
        models?.[0]?.provider_id ||
        null;
      if (!provider) {
        throw new Error(
          "Select a provider (or ensure models inventory has one) before installing leaderboard driver",
        );
      }
      const result = await installDecisionTreeSelection({
        model_id: mid,
        provider_id: provider,
      });
      setTree(result);
      setSelectedModel(mid);
      setSelectedProvider(provider);
      // Residual (adu): provenance for decision-tree status honesty.
      const tc = String(opts?.taskClass || "").trim();
      setDriverInstallProvenance({
        source: tc ? "leaderboard_task" : "leaderboard_recommended",
        task_class: tc || null,
      });
      // Keep registry list in sync when add-model path shares process registry
      try {
        const rm = await fetchRegisteredModels();
        setRegistered(rm);
      } catch {
        /* optional */
      }
    } catch (e) {
      setLeaderboardError(e instanceof Error ? e.message : String(e));
      setTreeError(e instanceof Error ? e.message : String(e));
    } finally {
      setTreeBusy(false);
    }
  }

  async function onInstallRecommendedFromLeaderboard() {
    if (!leaderboard?.recommended_model_id) {
      setLeaderboardError("No recommended model to install");
      return;
    }
    await onInstallLeaderboardModelAsDriver(leaderboard.recommended_model_id);
  }

  async function onApplyDepthTier(tier: string) {
    setDepthBusy(true);
    setDepthError(null);
    try {
      const d = await applyDepthTier({
        depth_tier: tier,
        model_id: selectedModel || null,
        provider_id: selectedProvider || null,
        install_driver: Boolean(selectedModel.trim()),
        includeHtml: true,
      });
      if (d.view_format !== "html") {
        throw new Error("depth tier view_format must be html");
      }
      setDepth(d);
      const hints = d.projection_hints;
      const nextIn =
        hints?.input_chars != null ? hints.input_chars : inputChars;
      const nextOut =
        hints?.expected_output_tokens != null
          ? hints.expected_output_tokens
          : outTokens;
      if (hints?.input_chars != null) setInputChars(hints.input_chars);
      if (hints?.expected_output_tokens != null)
        setOutTokens(hints.expected_output_tokens);
      // Residual (be): auto-project cost with depth-tier hints via #440 API.
      setEstimating(true);
      setEstimateError(null);
      try {
        const res = await estimatePromptCost({
          tier: hints?.tier || "pro",
          provider: selectedProvider || null,
          model: selectedModel || null,
          input_chars: nextIn,
          expected_output_tokens: nextOut,
        });
        setEstimate(res);
      } catch (e) {
        setEstimateError(e instanceof Error ? e.message : String(e));
      } finally {
        setEstimating(false);
      }
    } catch (e) {
      setDepthError(e instanceof Error ? e.message : String(e));
    } finally {
      setDepthBusy(false);
    }
  }

  async function onRefreshUsage() {
    setUsageBusy(true);
    setUsageError(null);
    try {
      const u = await fetchAntiekBenchUsageSummary({ includeHtml: true });
      if (u.view_format !== "html") {
        throw new Error("usage summary view_format must be html");
      }
      setUsage(u);
    } catch (e) {
      setUsageError(e instanceof Error ? e.message : String(e));
    } finally {
      setUsageBusy(false);
    }
  }

  async function onRefreshSuiteProposal() {
    setSuiteProposalBusy(true);
    setSuiteProposalError(null);
    try {
      const p = await fetchAntiekBenchSuiteProposal({ includeHtml: true });
      if (p.view_format !== "html") {
        throw new Error("suite proposal view_format must be html");
      }
      if (p.auto_promoted) {
        throw new Error("suite proposal must not auto-promote");
      }
      setSuiteProposal(p);
    } catch (e) {
      setSuiteProposalError(e instanceof Error ? e.message : String(e));
    } finally {
      setSuiteProposalBusy(false);
    }
  }

  async function onApproveSuiteProposal(approve: boolean) {
    if (!suiteProposal?.proposal_id) {
      setSuiteProposalError("No proposal_id to approve/reject");
      return;
    }
    setSuiteApproveBusy(true);
    setSuiteProposalError(null);
    try {
      const result = await approveAntiekBenchSuiteProposal({
        proposal_id: suiteProposal.proposal_id,
        approve,
        includeHtml: true,
      });
      setSuiteApprove(result);
      // Refresh proposal view after gate action
      const p = await fetchAntiekBenchSuiteProposal({ includeHtml: true });
      setSuiteProposal(p);
    } catch (e) {
      setSuiteProposalError(e instanceof Error ? e.message : String(e));
    } finally {
      setSuiteApproveBusy(false);
    }
  }

  const spendPct = useMemo(() => {
    if (
      !budget ||
      budget.daily_cap_usd == null ||
      budget.spent_usd == null ||
      budget.daily_cap_usd <= 0
    ) {
      return null;
    }
    return Math.min(100, (budget.spent_usd / budget.daily_cap_usd) * 100);
  }, [budget]);

  async function onEstimate(opts?: {
    tier?: string | null;
    input_chars?: number;
    expected_output_tokens?: number;
  }) {
    setEstimating(true);
    setEstimateError(null);
    try {
      const res = await estimatePromptCost({
        tier: opts?.tier || depth?.projection_hints?.tier || "pro",
        provider: selectedProvider || null,
        model: selectedModel || null,
        input_chars: opts?.input_chars ?? inputChars,
        expected_output_tokens:
          opts?.expected_output_tokens ?? outTokens,
      });
      setEstimate(res);
    } catch (e) {
      setEstimateError(e instanceof Error ? e.message : String(e));
    } finally {
      setEstimating(false);
    }
  }

  async function onInstallDriver() {
    if (!selectedModel.trim()) {
      setTreeError("Select a model before installing");
      return;
    }
    setTreeBusy(true);
    setTreeError(null);
    try {
      const res = await installDecisionTreeSelection({
        model_id: selectedModel.trim(),
        provider_id: selectedProvider.trim() || null,
      });
      setTree(res);
      // Residual (adu): manual install provenance.
      setDriverInstallProvenance({ source: "manual", task_class: null });
    } catch (e) {
      setTreeError(e instanceof Error ? e.message : String(e));
    } finally {
      setTreeBusy(false);
    }
  }

  async function onClearDriver() {
    setTreeBusy(true);
    setTreeError(null);
    try {
      const res = await clearDecisionTreeSelection();
      setTree(res);
      // Residual (adu): clear install provenance with driver.
      setDriverInstallProvenance({ source: null, task_class: null });
    } catch (e) {
      setTreeError(e instanceof Error ? e.message : String(e));
    } finally {
      setTreeBusy(false);
    }
  }

  return (
    <div className="h-full overflow-y-auto bg-ice-2 dark:bg-space-2">
      <div className="max-w-3xl mx-auto px-6 py-8 space-y-6">
        <header>
          <h1 className="text-2xl font-serif text-ink dark:text-bright">
            Operator settings
          </h1>
          <p className="text-sm text-ink-soft dark:text-starlight font-serif italic mt-1">
            Models, budget ceiling, and prompt cost projection. Numbers over
            placeholders — unknown spend stays unknown.
          </p>
        </header>

        <LemonCard title="Environment" elevation="z1">
          <div className="p-4 space-y-3 font-mono text-[13px]">
            <Row label="Viewport tier" value={tier} />
            <Row label="OS theme" value={isDark ? "dark" : "light"} />
            <Row
              label="Reduce motion"
              value={reduceMotion ? "yes" : "no"}
            />
            <Row
              label="UI version"
              value={
                (import.meta.env.VITE_ANTIEK_UI as string | undefined) ?? "v2"
              }
            />
          </div>
        </LemonCard>

        <LemonCard title="Models & providers" elevation="z1">
          <div className="p-4 space-y-3">
            {modelsError && (
              <p className="text-sm text-red-700 dark:text-red-300 font-mono">
                {modelsError}
              </p>
            )}
            {models === null && !modelsError && (
              <p className="text-sm text-ink-soft dark:text-starlight">
                Loading providers…
              </p>
            )}
            {models && models.length === 0 && (
              <p className="text-sm text-ink-soft dark:text-starlight">
                No providers registered and none configured in dispatch
                config.
              </p>
            )}
            {models && models.length > 0 && (
              <ul className="space-y-2">
                {models.map((m) => (
                  <li
                    key={m.provider_id}
                    className="flex flex-wrap items-baseline justify-between gap-2 border-b border-ink/10 dark:border-bright/10 pb-2 font-mono text-[13px]"
                  >
                    <span className="text-ink dark:text-bright font-semibold">
                      {m.provider_id}
                      {m.primary_model ? (
                        <span className="font-normal text-ink-soft dark:text-starlight">
                          {" "}
                          · {m.primary_model}
                        </span>
                      ) : null}
                    </span>
                    <span
                      className={
                        m.ready
                          ? "text-emerald-700 dark:text-emerald-300"
                          : "text-amber-700 dark:text-amber-300"
                      }
                    >
                      {m.ready ? "ready" : "not registered"}
                    </span>
                    {m.tier_bindings.length > 0 && (
                      <span className="w-full text-[11px] text-ink-soft dark:text-starlight">
                        tiers: {m.tier_bindings.join(", ")}
                      </span>
                    )}
                    {m.notes && (
                      <span className="w-full text-[11px] text-ink-soft dark:text-starlight">
                        {m.notes}
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            )}
            <p className="text-[11px] text-ink-soft dark:text-starlight font-serif italic">
              Adding API keys / new models remains operator-gated. Decision-tree
              install below is process-local (same process as dispatch).
            </p>
          </div>
        </LemonCard>

        <LemonCard title="Add model" elevation="z1" colour="glacial">
          <div
            className="p-4 space-y-3"
            data-testid="add-model-panel"
            data-view-format="html"
          >
            <p className="text-sm text-ink dark:text-bright">
              Register a model id into the process-local decision-tree registry.
              API keys remain operator-gated — this only records identity for
              driver selection.
            </p>
            {registeredError && (
              <p className="text-sm text-red-700 dark:text-red-300 font-mono">
                {registeredError}
              </p>
            )}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 font-mono text-[13px]">
              <label className="flex flex-col gap-1">
                <span className="text-[11px] uppercase tracking-wider text-ink-soft dark:text-starlight">
                  Provider id
                </span>
                <input
                  type="text"
                  data-testid="add-model-provider"
                  value={addProviderId}
                  onChange={(e) => setAddProviderId(e.target.value)}
                  placeholder="zai"
                  className="border border-ink/20 dark:border-bright/20 bg-transparent px-2 py-1 rounded"
                />
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-[11px] uppercase tracking-wider text-ink-soft dark:text-starlight">
                  Model id
                </span>
                <input
                  type="text"
                  data-testid="add-model-id"
                  value={addModelId}
                  onChange={(e) => setAddModelId(e.target.value)}
                  placeholder="glm-5.2"
                  className="border border-ink/20 dark:border-bright/20 bg-transparent px-2 py-1 rounded"
                />
              </label>
            </div>
            <label className="flex items-center gap-2 text-sm font-mono">
              <input
                type="checkbox"
                data-testid="add-model-select"
                checked={addSelectDriver}
                onChange={(e) => setAddSelectDriver(e.target.checked)}
              />
              Install as decision-tree driver
            </label>
            <button
              type="button"
              data-testid="add-model-submit"
              onClick={() => void onRegisterModel()}
              disabled={
                registeredBusy || !addModelId.trim() || !addProviderId.trim()
              }
              className="px-3 py-1.5 rounded border border-ink dark:border-bright text-sm font-mono hover:bg-ink/5 dark:hover:bg-bright/10 disabled:opacity-50"
            >
              {registeredBusy ? "Registering…" : "Register model"}
            </button>
            {registered && (
              <div
                className="font-mono text-[13px] space-y-1"
                data-testid="add-model-summary"
              >
                <Row label="Count" value={String(registered.count)} />
                <Row
                  label="Active"
                  value={registered.active_model_id ?? "(none)"}
                />
                <ul data-testid="add-model-list" className="space-y-1">
                  {(registered.models || []).map((m) => (
                    <li key={m.model_id}>
                      {m.provider_id}/{m.model_id}
                      {m.selected ? " ✓" : ""}
                    </li>
                  ))}
                </ul>
                {registered.notes?.map((n) => (
                  <p
                    key={n}
                    className="text-[11px] text-ink-soft dark:text-starlight"
                  >
                    {n}
                  </p>
                ))}
              </div>
            )}
          </div>
        </LemonCard>

        <LemonCard title="Depth-tier presets" elevation="z1" colour="glacial">
          <div
            className="p-4 space-y-3"
            data-testid="depth-tier-panel"
            data-view-format="html"
          >
            <p className="text-sm text-ink dark:text-bright">
              Flash / Pro / Wrestle map competitive speed vs depth postures onto
              dispatch tier + Antiek-bench task class + cost-projection hints
              (#440). Process-local like the decision-tree driver.
            </p>
            {depthError && (
              <p className="text-sm text-red-700 dark:text-red-300 font-mono">
                {depthError}
              </p>
            )}
            <div className="flex flex-wrap gap-2">
              {(depth?.presets?.length
                ? depth.presets
                : [
                    { depth_tier: "flash", label: "Flash" },
                    { depth_tier: "pro", label: "Pro" },
                    { depth_tier: "wrestle", label: "Wrestle" },
                  ]
              ).map((p) => (
                <button
                  key={p.depth_tier}
                  type="button"
                  data-testid={`depth-tier-${p.depth_tier}`}
                  disabled={depthBusy}
                  onClick={() => void onApplyDepthTier(p.depth_tier)}
                  className="px-3 py-1.5 rounded border border-ink dark:border-bright text-sm font-mono hover:bg-ink/5 dark:hover:bg-bright/10 disabled:opacity-50"
                >
                  {p.label || p.depth_tier}
                  {depth?.active_depth_tier === p.depth_tier ? " ✓" : ""}
                </button>
              ))}
            </div>
            {depth && (
              <div
                className="font-mono text-[13px] space-y-1"
                data-testid="depth-tier-summary"
              >
                <Row
                  label="Active"
                  value={depth.active_depth_tier ?? "(none)"}
                />
                {depth.projection_hints ? (
                  <>
                    <Row
                      label="Dispatch tier"
                      value={String(depth.projection_hints.tier ?? "—")}
                    />
                    <Row
                      label="Task class"
                      value={String(depth.projection_hints.task_class ?? "—")}
                    />
                    <Row
                      label="Hint out tokens"
                      value={String(
                        depth.projection_hints.expected_output_tokens ?? "—",
                      )}
                    />
                  </>
                ) : null}
                {depth.notes?.map((n) => (
                  <p
                    key={n}
                    className="text-[11px] text-ink-soft dark:text-starlight"
                  >
                    {n}
                  </p>
                ))}
              </div>
            )}
          </div>
        </LemonCard>

        <LemonCard title="Decision tree driver" elevation="z1" colour="glacial">
          <div
            id="decision-tree-panel"
            className="p-4 space-y-3"
            data-testid="decision-tree-panel"
          >
            <p className="text-sm text-ink dark:text-bright">
              Select the model driver for this process. Install writes the
              choice into the decision-tree registry so research dispatch can
              apply provider+model overrides. Cost projection still uses the
              #440 settings estimate API (never invents $0).
            </p>
            {/* Residual (sw): dual-gate L1–L4 prep strip — offline-honest. */}
            <div
              className="border border-ink/10 rounded p-2 space-y-1 dark:border-bright/10"
              data-testid="settings-dual-gate-prep"
              data-l7-notdiamond="advisory_only"
              data-l5-payment-rails="deferred"
              data-l6-live-multiagent="deferred"
              data-offline-merge-unit="true"
              data-offline-default="true"
              role="status"
            >
              <p className="text-[11px] font-mono text-ink-soft dark:text-starlight">
                Dual-gate prep (L1–L4) · L5 payment deferred · L6 offline merge
                unit · offline default · never silent live injectors
              </p>
              <p className="text-[11px] font-mono space-x-2">
                <a
                  href="#hydrate-live-status"
                  className="underline opacity-80 hover:opacity-100"
                  data-testid="settings-dual-gate-l1-l2-link"
                  title="L1 arxiv / L2 substack hydrate readiness"
                >
                  L1–L2 hydrate
                </a>
                {/* Residual (xh): L1 checklist section deep-link (parity pubs/reading). */}
                <a
                  href="/docs/campaigns/2026-07-09-research-reading-spine/DUAL-GATE-L1-L4-OPERATOR-CHECKLIST.md#l1-arxiv"
                  className="underline opacity-80 hover:opacity-100"
                  data-testid="settings-dual-gate-l1-checklist-link"
                  title="L1 arxiv hydrate checklist section (prep only)"
                >
                  L1 checklist
                </a>
                {/* Residual (xr): L2 substack checklist section deep-link. */}
                <a
                  href="/docs/campaigns/2026-07-09-research-reading-spine/DUAL-GATE-L1-L4-OPERATOR-CHECKLIST.md#l2-substack"
                  className="underline opacity-80 hover:opacity-100"
                  data-testid="settings-dual-gate-l2-checklist-link"
                  title="L2 Substack hydrate checklist section (prep only · ToS factory)"
                >
                  L2 checklist
                </a>
                <a
                  href="#twin-seed-live-status"
                  className="underline opacity-80 hover:opacity-100"
                  data-testid="settings-dual-gate-l3-link"
                  title="L3 twin seed live readiness"
                >
                  L3 twin seed
                </a>
                {/* Residual (xb): L3 checklist section deep-link (parity TwinNotes xa). */}
                <a
                  href="/docs/campaigns/2026-07-09-research-reading-spine/DUAL-GATE-L1-L4-OPERATOR-CHECKLIST.md#l3-twin"
                  className="underline opacity-80 hover:opacity-100"
                  data-testid="settings-dual-gate-l3-checklist-link"
                  title="L3 twin live seed checklist section (prep only)"
                >
                  L3 checklist
                </a>
                <a
                  href="#moil-live-step-status"
                  className="underline opacity-80 hover:opacity-100"
                  data-testid="settings-dual-gate-l4-link"
                  title="L4 Midnight Oil live-step readiness (offline default)"
                >
                  L4 MO live-step
                </a>
                {/* Residual (wy): L4 checklist section deep-link (parity MO wx). */}
                <a
                  href="/docs/campaigns/2026-07-09-research-reading-spine/DUAL-GATE-L1-L4-OPERATOR-CHECKLIST.md#l4-moil"
                  className="underline opacity-80 hover:opacity-100"
                  data-testid="settings-dual-gate-l4-checklist-link"
                  title="L4 Midnight Oil live-step checklist section (prep only)"
                >
                  L4 checklist
                </a>
                {/* Residual (vt/wh): L5 payment rails honesty + checklist deep-link. */}
                <a
                  href="/docs/campaigns/2026-07-09-research-reading-spine/DUAL-GATE-L1-L4-OPERATOR-CHECKLIST.md#l5-payment"
                  className="underline opacity-80 hover:opacity-100"
                  data-testid="settings-dual-gate-l5-payment"
                  data-l5-payment-rails="deferred"
                  data-live-payment="false"
                  title="L5 marketplace payment rails deferred — manual receipt only (checklist)"
                >
                  L5 payment deferred
                </a>
                {/* Residual (vz/wh): L6 deferred + checklist deep-link (parity Collective vx). */}
                <a
                  href="/docs/campaigns/2026-07-09-research-reading-spine/DUAL-GATE-L1-L4-OPERATOR-CHECKLIST.md#l6-collective"
                  className="underline opacity-80 hover:opacity-100"
                  data-testid="settings-dual-gate-l6-collective"
                  data-l6-live-multiagent="deferred"
                  data-offline-merge-unit="true"
                  title="L6 live multi-agent council deferred — offline merge unit only (checklist)"
                >
                  L6 offline merge unit
                </a>
                <a
                  href="#notdiamond-advisory"
                  className="underline opacity-80 hover:opacity-100"
                  data-testid="settings-dual-gate-l7-link"
                  title="L7 NotDiamond advisory only — never dispatch authority"
                >
                  L7 ND advisory
                </a>
                {/* Residual (wh): L7 checklist section (never-router) alongside Settings ND panel. */}
                <a
                  href="/docs/campaigns/2026-07-09-research-reading-spine/DUAL-GATE-L1-L4-OPERATOR-CHECKLIST.md#l7-notdiamond"
                  className="underline opacity-80 hover:opacity-100"
                  data-testid="settings-dual-gate-l7-checklist-link"
                  title="L7 NotDiamond never-router checklist section"
                >
                  L7 checklist
                </a>
              </p>
            </div>
            {treeError && (
              <p className="text-sm text-red-700 dark:text-red-300 font-mono">
                {treeError}
              </p>
            )}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 font-mono text-[13px]">
              <label className="flex flex-col gap-1">
                <span className="text-[11px] uppercase tracking-wider text-ink-soft dark:text-starlight">
                  Provider
                </span>
                <select
                  data-testid="decision-tree-provider"
                  value={selectedProvider}
                  onChange={(e) => {
                    setSelectedProvider(e.target.value);
                    const row = models?.find(
                      (m) => m.provider_id === e.target.value,
                    );
                    if (row?.primary_model) setSelectedModel(row.primary_model);
                  }}
                  className="border border-ink/20 dark:border-bright/20 bg-transparent px-2 py-1 rounded"
                >
                  <option value="">—</option>
                  {(models ?? []).map((m) => (
                    <option key={m.provider_id} value={m.provider_id}>
                      {m.provider_id}
                      {m.ready ? "" : " (not ready)"}
                    </option>
                  ))}
                </select>
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-[11px] uppercase tracking-wider text-ink-soft dark:text-starlight">
                  Model id
                </span>
                <input
                  data-testid="decision-tree-model"
                  type="text"
                  value={selectedModel}
                  onChange={(e) => setSelectedModel(e.target.value)}
                  placeholder="e.g. glm-5.2"
                  className="border border-ink/20 dark:border-bright/20 bg-transparent px-2 py-1 rounded"
                />
              </label>
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                data-testid="decision-tree-install"
                onClick={onInstallDriver}
                disabled={treeBusy}
                className="px-3 py-1.5 rounded border border-ink dark:border-bright text-sm font-mono hover:bg-ink/5 dark:hover:bg-bright/10 disabled:opacity-50"
              >
                {treeBusy ? "Working…" : "Install driver"}
              </button>
              <button
                type="button"
                data-testid="decision-tree-clear"
                onClick={onClearDriver}
                disabled={treeBusy}
                className="px-3 py-1.5 rounded border border-ink/40 dark:border-bright/40 text-sm font-mono hover:bg-ink/5 dark:hover:bg-bright/10 disabled:opacity-50"
              >
                Clear
              </button>
            </div>
            <div
              className="font-mono text-[13px] space-y-1"
              data-testid="decision-tree-status"
              // Residual (adu): install provenance honesty (manual | leaderboard | ND).
              data-install-source={driverInstallProvenance.source || ""}
              data-install-task-class={
                driverInstallProvenance.task_class || ""
              }
              data-installed={String(Boolean(tree?.installed))}
              data-model-id={tree?.model_id || ""}
              data-provider-id={tree?.provider_id || ""}
              data-advisory-only="true"
            >
              <Row
                label="Installed"
                value={
                  tree?.installed
                    ? `${tree.provider_id ?? "?"} / ${tree.model_id ?? "?"}`
                    : "none"
                }
              />
              {driverInstallProvenance.source ? (
                <p
                  className="text-[11px] text-ink-soft dark:text-starlight"
                  data-testid="decision-tree-install-provenance"
                  data-install-source={driverInstallProvenance.source}
                  data-install-task-class={
                    driverInstallProvenance.task_class || ""
                  }
                  role="status"
                >
                  Install source: {driverInstallProvenance.source}
                  {driverInstallProvenance.task_class
                    ? ` · best ${driverInstallProvenance.task_class}`
                    : ""}{" "}
                  (advisory only · never auto-routes)
                </p>
              ) : null}
              {tree?.notes?.map((n) => (
                <p
                  key={n}
                  className="text-[11px] text-ink-soft dark:text-starlight"
                >
                  {n}
                </p>
              ))}
            </div>
            {/* Residual (sa): budget usage bar at decision-tree (model driver) selection. */}
            <div
              className="space-y-1.5 border border-ink/10 rounded p-2 dark:border-bright/10"
              data-testid="decision-tree-budget-bar"
              data-spent-status={budget?.spent_status ?? "unknown"}
              data-has-cap={String(
                budget?.daily_cap_usd != null && budget.daily_cap_usd > 0,
              )}
              data-spend-pct={
                spendPct != null ? String(Math.round(spendPct)) : ""
              }
              role="status"
            >
              <p className="text-[11px] font-mono text-ink-soft dark:text-starlight">
                Budget vs driver (soft gate · never invents $0)
              </p>
              <div className="font-mono text-[12px] space-y-0.5">
                <Row
                  label="Daily cap"
                  value={
                    budget?.daily_cap_usd == null
                      ? "unset"
                      : `$${budget.daily_cap_usd.toFixed(2)}`
                  }
                />
                <Row
                  label="Spent"
                  value={
                    budget?.spent_status === "known" &&
                    budget.spent_usd != null
                      ? `$${budget.spent_usd.toFixed(4)}`
                      : budget?.spent_status === "unknown"
                        ? "unknown"
                        : "—"
                  }
                />
                <Row
                  label="Remaining"
                  value={
                    budget?.remaining_usd == null
                      ? "unknown"
                      : `$${budget.remaining_usd.toFixed(4)}`
                  }
                />
              </div>
              <div
                className="h-2 w-full rounded-full bg-ink/10 dark:bg-bright/10 overflow-hidden"
                role="progressbar"
                aria-valuemin={0}
                aria-valuemax={100}
                aria-valuenow={spendPct ?? 0}
                aria-label="Decision-tree budget usage"
                data-testid="decision-tree-budget-progress"
              >
                {spendPct != null ? (
                  <div
                    className="h-full bg-ink dark:bg-bright transition-all"
                    style={{ width: `${spendPct}%` }}
                  />
                ) : (
                  <div className="h-full w-full opacity-30" />
                )}
              </div>
              <p className="text-[11px] text-ink-soft dark:text-starlight">
                {spendPct == null
                  ? "Usage bar empty when spend is unknown or cap is unset. Project prompts before install."
                  : `${Math.round(spendPct)}% of daily cap used · project any prompt cost before dispatch burns remaining.`}
              </p>
              {/* Residual (sb): mini prompt projection at decision-tree driver. */}
              <div
                className="flex flex-wrap items-center gap-2"
                data-testid="decision-tree-mini-projection"
              >
                <button
                  type="button"
                  data-testid="decision-tree-project-cost"
                  onClick={() => void onEstimate()}
                  disabled={estimating}
                  className="px-2 py-1 rounded border border-ink/40 dark:border-bright/40 text-[11px] font-mono hover:bg-ink/5 dark:hover:bg-bright/10 disabled:opacity-50"
                  title="Project sample prompt cost for selected provider/model vs remaining budget"
                >
                  {estimating ? "Estimating…" : "Project sample cost"}
                </button>
                <a
                  href="#prompt-cost-projection"
                  className="text-[11px] underline opacity-80 hover:opacity-100"
                  data-testid="decision-tree-budget-project-link"
                >
                  Full projection
                </a>
                {/* Residual (sq): jump to weekly Antiek-bench leaderboard (advisory). */}
                <a
                  href="#antiek-bench-leaderboard"
                  className="text-[11px] underline opacity-80 hover:opacity-100"
                  data-testid="decision-tree-leaderboard-link"
                  title="Weekly Antiek-bench leaderboard (advisory · never auto-routes)"
                >
                  Weekly leaderboard
                </a>
                {/* Residual (sv): jump to competitive dogfood fixtures (v2 postures). */}
                <a
                  href="#antiek-bench-dogfood"
                  className="text-[11px] underline opacity-80 hover:opacity-100"
                  data-testid="decision-tree-dogfood-link"
                  title="Competitive dogfood fixtures (offline · never auto-promotes)"
                >
                  Dogfood fixtures
                </a>
              </div>
              {estimate ? (
                <p
                  className="text-[11px] font-mono text-ink-soft dark:text-starlight"
                  data-testid="decision-tree-mini-estimate"
                  data-pricing-known={String(estimate.pricing_known === true)}
                  data-would-exceed={
                    estimate.would_exceed_budget == null
                      ? "unknown"
                      : estimate.would_exceed_budget
                        ? "yes"
                        : "no"
                  }
                  data-remaining-after-usd={
                    budget?.remaining_usd != null &&
                    estimate.estimated_usd_high != null
                      ? String(
                          budget.remaining_usd - estimate.estimated_usd_high,
                        )
                      : ""
                  }
                  // Residual (aej): parity launch/badge aeb — machine-readable over-cap foresight.
                  data-goes-negative={
                    budget?.remaining_usd != null &&
                    estimate.estimated_usd_high != null
                      ? String(
                          budget.remaining_usd - estimate.estimated_usd_high <
                            0,
                        )
                      : "unknown"
                  }
                  data-provider={estimate.provider ?? selectedProvider ?? ""}
                  data-model={estimate.model ?? selectedModel ?? ""}
                  role="status"
                >
                  Sample projection · pricing=
                  {estimate.pricing_known ? "known" : "unknown"} · would_exceed=
                  {estimate.would_exceed_budget == null
                    ? "unknown"
                    : estimate.would_exceed_budget
                      ? "yes"
                      : "no"}
                  {estimate.estimated_usd_high != null
                    ? ` · high≈$${estimate.estimated_usd_high.toFixed(4)}`
                    : " · high=—"}
                  {budget?.remaining_usd != null &&
                  estimate.estimated_usd_high != null
                    ? ` · remaining after≈$${(budget.remaining_usd - estimate.estimated_usd_high).toFixed(4)}`
                    : ""}
                  {budget?.remaining_usd != null &&
                  estimate.estimated_usd_high != null &&
                  budget.remaining_usd - estimate.estimated_usd_high < 0
                    ? " · over remaining (soft foresight)"
                    : ""}{" "}
                  (soft gate · never invents $0)
                </p>
              ) : null}
            </div>
          </div>
        </LemonCard>

        {/* Residual (hs): twin seed note_taker readiness. */}
        <LemonCard
          title="Twin seed (recursive note-taker)"
          elevation="z1"
          colour="parchment"
        >
          <div
            className="p-4 space-y-3"
            id="twin-seed-live-status"
            data-testid="twin-seed-live-status-panel"
            data-view-format="html"
            data-offline-honest={
              twinSeedLive ? String(twinSeedLive.offline_honest) : undefined
            }
            data-injector-installed={
              twinSeedLive
                ? String(twinSeedLive.injector_installed)
                : undefined
            }
            // Residual (aec): L3 live ready only when all three gates true.
            data-l3-live-ready={
              twinSeedLive
                ? String(
                    twinSeedLive.live_env === true &&
                      twinSeedLive.use_dispatch === true &&
                      twinSeedLive.injector_installed === true &&
                      twinSeedLive.offline_honest === false,
                  )
                : undefined
            }
          >
            <p className="text-sm text-ink dark:text-bright">
              Recursive note-taker UI always force_offline seeds. Live
              note_taker requires dual env gate + boot install — never silent
              LLM from this panel.
            </p>
            {/* Residual (aec): in-panel L3 checklist deep-link (parity TwinNotes xa). */}
            <div
              className="flex flex-wrap items-center gap-2 text-[11px]"
              data-testid="twin-seed-live-l3-prep"
              data-dual-gate="L3"
              role="navigation"
              aria-label="L3 twin live seed dual-gate prep"
            >
              <a
                href="/docs/campaigns/2026-07-09-research-reading-spine/DUAL-GATE-L1-L4-OPERATOR-CHECKLIST.md#l3-twin"
                className="underline opacity-80 hover:opacity-100"
                data-testid="twin-seed-live-l3-checklist-link"
                title="Dual-gate L3 twin live seed checklist (prep only · offline default)"
              >
                Dual-gate L3 twin checklist
              </a>
              <span className="opacity-40" aria-hidden>
                ·
              </span>
              <span className="font-mono opacity-70">
                prep only · never enables live from this panel
              </span>
            </div>
            <button
              type="button"
              data-testid="twin-seed-live-status-refresh"
              disabled={twinSeedLiveBusy}
              onClick={() => void onRefreshTwinSeedLiveStatus()}
              className="px-3 py-1.5 rounded border border-ink dark:border-bright text-sm font-mono hover:bg-ink/5 dark:hover:bg-bright/10 disabled:opacity-50"
            >
              {twinSeedLiveBusy ? "Refreshing…" : "Refresh twin seed status"}
            </button>
            {twinSeedLiveError ? (
              <p className="text-sm text-emperor" role="alert">
                {twinSeedLiveError}
              </p>
            ) : null}
            {twinSeedLive ? (
              <div
                className="space-y-1 font-mono text-[11px]"
                data-testid="twin-seed-live-status-metrics"
                data-offline-honest={String(twinSeedLive.offline_honest)}
                data-live-env={String(twinSeedLive.live_env)}
                data-use-dispatch={String(twinSeedLive.use_dispatch)}
                data-injector-installed={String(
                  twinSeedLive.injector_installed,
                )}
                // Residual (aec): composite L3 readiness (all gates + not offline-only).
                data-l3-live-ready={String(
                  twinSeedLive.live_env === true &&
                    twinSeedLive.use_dispatch === true &&
                    twinSeedLive.injector_installed === true &&
                    twinSeedLive.offline_honest === false,
                )}
                data-l3-gates-live-env={String(twinSeedLive.live_env === true)}
                data-l3-gates-use-dispatch={String(
                  twinSeedLive.use_dispatch === true,
                )}
                data-l3-gates-injector={String(
                  twinSeedLive.injector_installed === true,
                )}
                role="status"
              >
                <p>
                  Mode:{" "}
                  <strong>
                    {twinSeedLive.offline_honest
                      ? "offline-honest identity stubs"
                      : "live note_taker installed"}
                  </strong>
                </p>
                <p>
                  env <code>{twinSeedLive.live_env_flag}</code>=
                  {String(twinSeedLive.live_env)} ·{" "}
                  <code>{twinSeedLive.use_dispatch_env_flag}</code>=
                  {String(twinSeedLive.use_dispatch)} · injector=
                  {String(twinSeedLive.injector_installed)}
                </p>
                <p
                  data-testid="twin-seed-live-l3-gate-matrix"
                  data-l3-live-ready={String(
                    twinSeedLive.live_env === true &&
                      twinSeedLive.use_dispatch === true &&
                      twinSeedLive.injector_installed === true &&
                      twinSeedLive.offline_honest === false,
                  )}
                >
                  L3 gate matrix: live_env=
                  {twinSeedLive.live_env === true ? "on" : "off"} · use_dispatch=
                  {twinSeedLive.use_dispatch === true ? "on" : "off"} · injector=
                  {twinSeedLive.injector_installed === true ? "on" : "off"} ·
                  live_ready=
                  {twinSeedLive.live_env === true &&
                  twinSeedLive.use_dispatch === true &&
                  twinSeedLive.injector_installed === true &&
                  twinSeedLive.offline_honest === false
                    ? "true"
                    : "false"}{" "}
                  (all three + offline_honest=false required)
                </p>
                {twinSeedLive.notes.map((n) => (
                  <p key={n} className="opacity-80">
                    {n}
                  </p>
                ))}
              </div>
            ) : null}
          </div>
        </LemonCard>

        {/* Residual (sz): Midnight Oil L4 live-step readiness (offline-honest). */}
        <LemonCard
          title="Midnight Oil live-step (L4 dual-gate)"
          elevation="z1"
          colour="parchment"
        >
          <div
            id="moil-live-step-status"
            className="p-4 space-y-3"
            data-testid="moil-live-step-status-panel"
            data-view-format="html"
            data-offline-honest={
              moilLive ? String(moilLive.offline_honest) : undefined
            }
            data-injector-installed={
              moilLive ? String(moilLive.injector_installed) : undefined
            }
            // Residual (aed): L4 live ready only when env + injector true and not offline-only.
            data-l4-live-ready={
              moilLive
                ? String(
                    moilLive.live_env === true &&
                      moilLive.injector_installed === true &&
                      moilLive.offline_honest === false,
                  )
                : undefined
            }
          >
            <p className="text-sm text-ink dark:text-bright">
              Autonomous Midnight Oil worker steps default offline. Live step
              requires dual env gate + injector — this panel never enables the
              live worker.
            </p>
            {/* Residual (aed): in-panel L4 checklist deep-link (parity twin L3 aec / MO wx). */}
            <div
              className="flex flex-wrap items-center gap-2 text-[11px]"
              data-testid="moil-live-l4-prep"
              data-dual-gate="L4"
              role="navigation"
              aria-label="L4 Midnight Oil live-step dual-gate prep"
            >
              <a
                href="/docs/campaigns/2026-07-09-research-reading-spine/DUAL-GATE-L1-L4-OPERATOR-CHECKLIST.md#l4-moil"
                className="underline opacity-80 hover:opacity-100"
                data-testid="moil-live-l4-checklist-link"
                title="Dual-gate L4 Midnight Oil live-step checklist (prep only · offline default)"
              >
                Dual-gate L4 MO checklist
              </a>
              <span className="opacity-40" aria-hidden>
                ·
              </span>
              <span className="font-mono opacity-70">
                prep only · never enables live worker from this panel
              </span>
            </div>
            <button
              type="button"
              data-testid="moil-live-step-status-refresh"
              disabled={moilLiveBusy}
              onClick={() => void onRefreshMoilLiveStepStatus()}
              className="px-3 py-1.5 rounded border border-ink dark:border-bright text-sm font-mono hover:bg-ink/5 dark:hover:bg-bright/10 disabled:opacity-50"
            >
              {moilLiveBusy ? "Refreshing…" : "Refresh MO live-step status"}
            </button>
            {moilLiveError ? (
              <p className="text-sm text-emperor" role="alert">
                {moilLiveError}
              </p>
            ) : null}
            {moilLive ? (
              <div
                className="space-y-1 font-mono text-[11px]"
                data-testid="moil-live-step-status-metrics"
                data-offline-honest={String(moilLive.offline_honest)}
                data-live-env={String(moilLive.live_env)}
                data-injector-installed={String(moilLive.injector_installed)}
                // Residual (aed): composite L4 readiness (env + injector + not offline-only).
                data-l4-live-ready={String(
                  moilLive.live_env === true &&
                    moilLive.injector_installed === true &&
                    moilLive.offline_honest === false,
                )}
                data-l4-gates-live-env={String(moilLive.live_env === true)}
                data-l4-gates-injector={String(
                  moilLive.injector_installed === true,
                )}
                role="status"
              >
                <p>
                  Mode:{" "}
                  <strong>
                    {moilLive.offline_honest
                      ? "offline-honest stub steps"
                      : "live step dual-gate ready"}
                  </strong>
                </p>
                <p>
                  env <code>{moilLive.live_env_flag}</code>=
                  {String(moilLive.live_env)} · injector=
                  {String(moilLive.injector_installed)}
                </p>
                <p
                  data-testid="moil-live-l4-gate-matrix"
                  data-l4-live-ready={String(
                    moilLive.live_env === true &&
                      moilLive.injector_installed === true &&
                      moilLive.offline_honest === false,
                  )}
                >
                  L4 gate matrix: live_env=
                  {moilLive.live_env === true ? "on" : "off"} · injector=
                  {moilLive.injector_installed === true ? "on" : "off"} ·
                  live_ready=
                  {moilLive.live_env === true &&
                  moilLive.injector_installed === true &&
                  moilLive.offline_honest === false
                    ? "true"
                    : "false"}{" "}
                  (env + injector + offline_honest=false required)
                </p>
                {moilLive.notes.map((n) => (
                  <p key={n} className="opacity-80">
                    {n}
                  </p>
                ))}
              </div>
            ) : null}
          </div>
        </LemonCard>

        {/* Residual (hq): arxiv/substack hydrate injector readiness. */}
        <LemonCard
          title="Publication hydrate (arxiv / substack)"
          elevation="z1"
          colour="parchment"
        >
          <div
            className="p-4 space-y-3"
            id="hydrate-live-status"
            data-testid="hydrate-live-status-panel"
            data-view-format="html"
            data-offline-honest={
              hydrateLive ? String(hydrateLive.offline_honest) : undefined
            }
            data-any-live-injector={
              hydrateLive ? String(hydrateLive.any_live_injector) : undefined
            }
            // Residual (aee): L1 arxiv live ready / L2 substack live ready composites.
            data-l1-arxiv-live-ready={
              hydrateLive
                ? String(
                    hydrateLive.arxiv.env_enabled === true &&
                      hydrateLive.arxiv.injector_installed === true,
                  )
                : undefined
            }
            data-l2-substack-live-ready={
              hydrateLive
                ? String(
                    hydrateLive.substack.env_enabled === true &&
                      hydrateLive.substack.injector_installed === true,
                  )
                : undefined
            }
          >
            <p className="text-sm text-ink dark:text-bright">
              Knowledge-dense refs hydrate offline-honest by default (identity
              only). Live arXiv/Substack injectors are env-gated process
              installs — never silent network from this UI.
            </p>
            {/* Residual (aee): in-panel L1/L2 checklist deep-links (parity aec/aed). */}
            <div
              className="flex flex-wrap items-center gap-2 text-[11px]"
              data-testid="hydrate-live-l1-l2-prep"
              data-dual-gate="L1-L2"
              role="navigation"
              aria-label="L1 arxiv and L2 Substack hydrate dual-gate prep"
            >
              <a
                href="/docs/campaigns/2026-07-09-research-reading-spine/DUAL-GATE-L1-L4-OPERATOR-CHECKLIST.md#l1-arxiv"
                className="underline opacity-80 hover:opacity-100"
                data-testid="hydrate-live-l1-checklist-link"
                title="Dual-gate L1 arxiv hydrate checklist (prep only · offline identity default)"
              >
                Dual-gate L1 arxiv checklist
              </a>
              <span className="opacity-40" aria-hidden>
                ·
              </span>
              <a
                href="/docs/campaigns/2026-07-09-research-reading-spine/DUAL-GATE-L1-L4-OPERATOR-CHECKLIST.md#l2-substack"
                className="underline opacity-80 hover:opacity-100"
                data-testid="hydrate-live-l2-checklist-link"
                title="Dual-gate L2 Substack hydrate checklist (prep only · ToS factory)"
              >
                Dual-gate L2 Substack checklist
              </a>
              <span className="opacity-40" aria-hidden>
                ·
              </span>
              <span className="font-mono opacity-70">
                prep only · never enables live hydrate from this panel
              </span>
            </div>
            <button
              type="button"
              data-testid="hydrate-live-status-refresh"
              disabled={hydrateLiveBusy}
              onClick={() => void onRefreshHydrateLiveStatus()}
              className="px-3 py-1.5 rounded border border-ink dark:border-bright text-sm font-mono hover:bg-ink/5 dark:hover:bg-bright/10 disabled:opacity-50"
            >
              {hydrateLiveBusy ? "Refreshing…" : "Refresh hydrate status"}
            </button>
            {hydrateLiveError ? (
              <p className="text-sm text-emperor" role="alert">
                {hydrateLiveError}
              </p>
            ) : null}
            {hydrateLive ? (
              <div
                className="space-y-1 font-mono text-[11px]"
                data-testid="hydrate-live-status-metrics"
                data-offline-honest={String(hydrateLive.offline_honest)}
                data-arxiv-env={String(hydrateLive.arxiv.env_enabled)}
                data-arxiv-injector={String(
                  hydrateLive.arxiv.injector_installed,
                )}
                data-substack-env={String(hydrateLive.substack.env_enabled)}
                data-substack-injector={String(
                  hydrateLive.substack.injector_installed,
                )}
                // Residual (aee): per-source live ready composites.
                data-l1-arxiv-live-ready={String(
                  hydrateLive.arxiv.env_enabled === true &&
                    hydrateLive.arxiv.injector_installed === true,
                )}
                data-l2-substack-live-ready={String(
                  hydrateLive.substack.env_enabled === true &&
                    hydrateLive.substack.injector_installed === true,
                )}
                role="status"
              >
                <p>
                  Mode:{" "}
                  <strong>
                    {hydrateLive.offline_honest
                      ? "offline-honest identity"
                      : "live injector(s) installed"}
                  </strong>
                </p>
                <p>
                  arXiv · env{" "}
                  <code>{hydrateLive.arxiv.env_flag}</code>=
                  {String(hydrateLive.arxiv.env_enabled)} · injector=
                  {String(hydrateLive.arxiv.injector_installed)}
                </p>
                <p>
                  Substack · env{" "}
                  <code>{hydrateLive.substack.env_flag}</code>=
                  {String(hydrateLive.substack.env_enabled)} · injector=
                  {String(hydrateLive.substack.injector_installed)}
                </p>
                <p
                  data-testid="hydrate-live-l1-l2-gate-matrix"
                  data-l1-arxiv-live-ready={String(
                    hydrateLive.arxiv.env_enabled === true &&
                      hydrateLive.arxiv.injector_installed === true,
                  )}
                  data-l2-substack-live-ready={String(
                    hydrateLive.substack.env_enabled === true &&
                      hydrateLive.substack.injector_installed === true,
                  )}
                >
                  L1/L2 gate matrix: arxiv_live=
                  {hydrateLive.arxiv.env_enabled === true &&
                  hydrateLive.arxiv.injector_installed === true
                    ? "true"
                    : "false"}{" "}
                  · substack_live=
                  {hydrateLive.substack.env_enabled === true &&
                  hydrateLive.substack.injector_installed === true
                    ? "true"
                    : "false"}{" "}
                  (env + injector per source · offline identity default)
                </p>
                {hydrateLive.notes.map((n) => (
                  <p key={n} className="opacity-80">
                    {n}
                  </p>
                ))}
              </div>
            ) : null}
          </div>
        </LemonCard>

        <LemonCard title="NotDiamond advisory" elevation="z1" colour="glacial">
          {/* Residual (rm): hash target for DecisionTreeDriverBadge Settings deep-link. */}
          <div
            id="notdiamond-advisory"
            className="p-4 space-y-3"
            data-testid="notdiamond-advisory-panel"
            data-view-format="html"
            data-advisory-only="true"
            data-authority-rejected={
              nd?.authority_rejected === true ? "true" : "false"
            }
            data-is-dispatch-authority={
              nd?.notdiamond_is_dispatch_authority === true ? "true" : "false"
            }
            data-kill-switch={nd?.kill_switch_enabled ? "on" : "off"}
            data-suggestion-week={nd?.suggestion_week_id || leaderboardWeek || ""}
            data-driver-delta={ndDriverDelta.status}
            // Residual (aez): L7 never-router posture (parity L1–L4 gate matrices).
            data-l7-never-router-posture={
              nd
                ? String(
                    nd.authority_rejected === true &&
                      nd.notdiamond_is_dispatch_authority !== true &&
                      nd.advisory_allowed === true,
                  )
                : undefined
            }
            data-l7-advisory-only="true"
          >
            <p className="text-sm text-ink dark:text-bright">
              Campaign verdict: advisory GO (measured wedge only); authoritative
              dispatch REJECT under §16. NotDiamond is never the dispatch owner
              — decision-tree + Hermes remain primary.
            </p>
            {/* Residual (aez): L7 dual-gate prep + gate matrix (never enables router). */}
            <div
              className="flex flex-wrap items-center gap-2 text-[11px]"
              data-testid="notdiamond-live-l7-prep"
              data-dual-gate="L7"
              data-l7-advisory-only="true"
              role="navigation"
              aria-label="L7 NotDiamond advisory dual-gate prep"
            >
              <a
                href="/docs/campaigns/2026-07-09-research-reading-spine/DUAL-GATE-L1-L4-OPERATOR-CHECKLIST.md#l7-notdiamond"
                className="underline opacity-80 hover:opacity-100"
                data-testid="notdiamond-live-l7-checklist-link"
                title="L7 NotDiamond never-router checklist (advisory only forever)"
              >
                Dual-gate L7 checklist
              </a>
              <span className="opacity-40" aria-hidden>
                ·
              </span>
              <a
                href="#antiek-bench-leaderboard"
                className="underline opacity-80 hover:opacity-100"
                data-testid="notdiamond-live-l7-leaderboard-link"
                title="Weekly leaderboard feeds advisory suggestion (never auto-routes)"
              >
                Weekly leaderboard
              </a>
              <span className="opacity-40" aria-hidden>
                ·
              </span>
              {/* Residual (ahy): FUTURE-AGENT advisory-only verdict deep-link (ahw). */}
              <a
                href="/docs/campaigns/2026-07-09-research-reading-spine/FUTURE-AGENT-SPEC-notdiamond-advisory-only.md"
                className="underline opacity-80 hover:opacity-100"
                data-testid="notdiamond-future-agent-advisory-spec-link"
                title="Future-agent brief: NotDiamond useful as advisor, never as router"
              >
                FUTURE-AGENT ND advisory-only
              </a>
            </div>
            {/* Residual (he): weekly advisory refresh tied to leaderboard week. */}
            <div className="flex flex-wrap items-center gap-2">
              <label className="text-[11px] font-mono text-ink-soft dark:text-starlight">
                Week{" "}
                <code data-testid="notdiamond-week-id">
                  {leaderboardWeek || "—"}
                </code>
              </label>
              <button
                type="button"
                data-testid="notdiamond-refresh-advisory"
                disabled={ndBusy}
                onClick={() => void onRefreshNotDiamondAdvisory()}
                className="px-3 py-1.5 rounded border border-ink dark:border-bright text-sm font-mono hover:bg-ink/5 dark:hover:bg-bright/10 disabled:opacity-50"
              >
                {ndBusy ? "Refreshing…" : "Refresh weekly advisory"}
              </button>
            </div>
            {ndError && (
              <p
                className="text-sm text-red-700 dark:text-red-300 font-mono"
                data-testid="notdiamond-advisory-error"
                role="alert"
              >
                {ndError}
              </p>
            )}
            {nd && (
              <div
                className="font-mono text-[13px] space-y-2"
                data-testid="notdiamond-advisory-summary"
              >
                {/* Residual (aez): L7 gate matrix — never-router posture honesty. */}
                <p
                  className="text-[11px] font-mono opacity-90"
                  data-testid="notdiamond-live-l7-gate-matrix"
                  data-l7-advisory-allowed={String(nd.advisory_allowed === true)}
                  data-l7-authority-rejected={String(
                    nd.authority_rejected === true,
                  )}
                  data-l7-is-dispatch-authority={String(
                    nd.notdiamond_is_dispatch_authority === true,
                  )}
                  data-l7-kill-switch={
                    nd.kill_switch_enabled ? "on" : "off"
                  }
                  data-l7-advisory-only="true"
                  data-l7-never-router-posture={String(
                    nd.authority_rejected === true &&
                      nd.notdiamond_is_dispatch_authority !== true &&
                      nd.advisory_allowed === true,
                  )}
                  role="status"
                >
                  L7 gate matrix: advisory_allowed=
                  {nd.advisory_allowed === true ? "true" : "false"} ·
                  authority_rejected=
                  {nd.authority_rejected === true ? "true" : "false"} ·
                  is_dispatch_authority=
                  {nd.notdiamond_is_dispatch_authority === true
                    ? "true"
                    : "false"}{" "}
                  · kill_switch=
                  {nd.kill_switch_enabled ? "on" : "off"} · never_router_posture=
                  {nd.authority_rejected === true &&
                  nd.notdiamond_is_dispatch_authority !== true &&
                  nd.advisory_allowed === true
                    ? "true"
                    : "false"}{" "}
                  (advisory GO + authority REJECT + never dispatch · install
                  remains explicit)
                </p>
                <Row
                  label="Advisory"
                  value={`${nd.advisory_verdict} (allowed=${String(nd.advisory_allowed)})`}
                />
                <Row
                  label="Authority"
                  value={`${nd.authority_verdict} (rejected=${String(nd.authority_rejected)})`}
                />
                <Row
                  label="Is dispatch authority"
                  value={String(nd.notdiamond_is_dispatch_authority)}
                />
                <Row label="Dispatch owner" value={nd.dispatch_owner} />
                <Row
                  label="Kill-switch"
                  value={`${nd.kill_switch_env}=${nd.kill_switch_enabled ? "on" : "off (default)"}`}
                />
                <Row
                  label="Suggestion week"
                  value={nd.suggestion_week_id || leaderboardWeek || "—"}
                />
                <Row
                  label="Suggested model"
                  value={
                    nd.suggested_model_id
                      ? `${nd.suggested_model_id}${
                          nd.recommended_mean_score != null
                            ? ` (${nd.recommended_mean_score})`
                            : ""
                        }`
                      : "—"
                  }
                />
                <Row
                  label="Suggestion source"
                  value={nd.suggestion_source || "—"}
                />
                {/* Residual (rl): installed driver vs weekly advisory delta. */}
                <div
                  className="rounded border border-ink/15 p-2 space-y-1 dark:border-bright/15"
                  data-testid="notdiamond-driver-delta"
                  data-delta-status={ndDriverDelta.status}
                  data-suggested={ndDriverDelta.suggested}
                  data-installed={ndDriverDelta.installed}
                  data-advisory-only="true"
                  role="status"
                >
                  <p className="text-[11px] font-mono opacity-90">
                    Installed driver:{" "}
                    <code data-testid="notdiamond-installed-driver">
                      {ndDriverDelta.installed || "(none)"}
                    </code>
                  </p>
                  <p className="text-[11px] font-mono opacity-90">
                    Advisory suggestion:{" "}
                    <code data-testid="notdiamond-suggested-driver">
                      {ndDriverDelta.suggested || "(none)"}
                    </code>
                  </p>
                  <p
                    className="text-[11px] font-mono"
                    data-testid="notdiamond-driver-delta-label"
                  >
                    {notDiamondDriverDeltaLabel(ndDriverDelta)}
                  </p>
                </div>
                {/* Residual (ade): ND advisory vs Antiek-bench weekly rank (both advisory). */}
                <div
                  className="rounded border border-ink/15 p-2 space-y-1 dark:border-bright/15"
                  data-testid="notdiamond-bench-delta"
                  data-delta-status={ndBenchDelta.status}
                  data-nd-suggested={ndBenchDelta.nd_suggested}
                  data-bench-recommended={ndBenchDelta.bench_recommended}
                  data-advisory-only="true"
                  data-is-dispatch-authority="false"
                  role="status"
                >
                  <p className="text-[11px] font-mono opacity-90">
                    Antiek-bench weekly:{" "}
                    <code data-testid="notdiamond-bench-recommended">
                      {ndBenchDelta.bench_recommended || "(unset)"}
                    </code>
                  </p>
                  <p className="text-[11px] font-mono opacity-90">
                    NotDiamond advisory:{" "}
                    <code data-testid="notdiamond-bench-nd-suggested">
                      {ndBenchDelta.nd_suggested || "(none)"}
                    </code>
                  </p>
                  <p
                    className="text-[11px] font-mono"
                    data-testid="notdiamond-bench-delta-label"
                  >
                    {notDiamondBenchDeltaLabel(ndBenchDelta)}
                  </p>
                  <a
                    href="#antiek-bench-leaderboard"
                    className="text-[11px] font-mono underline opacity-80 hover:opacity-100"
                    data-testid="notdiamond-bench-leaderboard-link"
                    title="Jump to Antiek-bench weekly leaderboard (advisory · never auto-routes)"
                  >
                    Open weekly leaderboard
                  </a>
                </div>
                <Row label="View" value={nd.view_format} />
                {nd.suggested_model_id && nd.installable !== false ? (
                  <button
                    type="button"
                    data-testid="notdiamond-install-advisory"
                    disabled={
                      treeBusy ||
                      ndBusy ||
                      nd.notdiamond_is_dispatch_authority
                    }
                    onClick={() => void onInstallNotDiamondAdvisory()}
                    className="px-3 py-1.5 rounded border border-ink dark:border-bright text-sm font-mono hover:bg-ink/5 dark:hover:bg-bright/10 disabled:opacity-50"
                  >
                    Install advisory pick as decision-tree driver
                  </button>
                ) : null}
                {nd.notes?.map((n) => (
                  <p
                    key={n}
                    className="text-[11px] text-ink-soft dark:text-starlight"
                  >
                    {n}
                  </p>
                ))}
                {nd.html ? (
                  <div
                    className="prose border rounded p-2 text-sm max-h-48 overflow-auto"
                    data-testid="notdiamond-advisory-html"
                    dangerouslySetInnerHTML={{ __html: nd.html }}
                  />
                ) : null}
              </div>
            )}
          </div>
        </LemonCard>

        <LemonCard
          title="Antiek-bench weekly leaderboard"
          elevation="z1"
          colour="glacial"
        >
          <div
            id="antiek-bench-leaderboard"
            className="p-4 space-y-3"
            data-testid="antiek-bench-leaderboard-panel"
            data-view-format="html"
          >
            <p className="text-sm text-ink dark:text-bright">
              Offline weekly model ranking by task class (advisory for
              decision-tree — never auto-routes dispatch). Not a live multi-
              provider bench run.
            </p>
            {leaderboardError && (
              <p className="text-sm text-red-700 dark:text-red-300 font-mono">
                {leaderboardError}
              </p>
            )}
            <div className="flex flex-wrap gap-2 items-end">
              <label className="flex flex-col gap-1 font-mono text-[13px]">
                <span className="text-[11px] uppercase tracking-wider text-ink-soft dark:text-starlight">
                  Week id
                </span>
                <input
                  type="text"
                  data-testid="antiek-bench-leaderboard-week"
                  value={leaderboardWeek}
                  onChange={(e) => setLeaderboardWeek(e.target.value)}
                  className="border border-ink/20 dark:border-bright/20 bg-transparent px-2 py-1 rounded"
                />
              </label>
              <button
                type="button"
                data-testid="antiek-bench-leaderboard-refresh"
                onClick={() => void onRefreshLeaderboard()}
                disabled={leaderboardBusy || !leaderboardWeek.trim()}
                className="px-3 py-1.5 rounded border border-ink dark:border-bright text-sm font-mono hover:bg-ink/5 dark:hover:bg-bright/10 disabled:opacity-50"
              >
                {leaderboardBusy ? "Loading…" : "Refresh leaderboard"}
              </button>
              <button
                type="button"
                data-testid="antiek-bench-run-offline"
                onClick={() => void onRunOfflineDogfood()}
                disabled={
                  offlineRunBusy ||
                  leaderboardBusy ||
                  !leaderboardWeek.trim()
                }
                className="px-3 py-1.5 rounded border border-ink dark:border-bright text-sm font-mono hover:bg-ink/5 dark:hover:bg-bright/10 disabled:opacity-50"
              >
                {offlineRunBusy
                  ? "Running offline…"
                  : "Run offline dogfood suite"}
              </button>
            </div>
            {offlineRunError && (
              <p className="text-sm text-red-700 dark:text-red-300 font-mono">
                {offlineRunError}
              </p>
            )}
            {offlineRun ? (
              <div
                className="font-mono text-[13px] space-y-1 border border-ink/10 dark:border-bright/10 rounded p-2"
                data-testid="antiek-bench-run-offline-result"
                data-auto-promoted={String(Boolean(offlineRun.auto_promoted))}
                data-view-format={offlineRun.view_format || "html"}
              >
                <Row label="Offline runs" value={String(offlineRun.run_count)} />
                <Row
                  label="Models"
                  value={(offlineRun.models_run || []).join(", ") || "—"}
                />
                <Row
                  label="Suite"
                  value={offlineRun.suite_version || "—"}
                />
                <Row
                  label="Recommended"
                  value={
                    offlineRun.recommended_model_id
                      ? `${offlineRun.recommended_model_id} (${offlineRun.recommended_mean_score ?? "—"})`
                      : "—"
                  }
                />
                {/* Residual (dt): show usage feed into recursive suite rewrite. */}
                <Row
                  label="Usage events recorded"
                  value={
                    offlineRun.usage_events_recorded != null
                      ? String(offlineRun.usage_events_recorded)
                      : "—"
                  }
                />
                <Row
                  label="Auto-promoted"
                  value={offlineRun.auto_promoted ? "true (unexpected)" : "false"}
                />
                <p
                  className="text-[11px] text-ink-mute dark:text-moonlight"
                  data-testid="antiek-bench-weekly-agent-note"
                >
                  Weekly offline schedule (operator): LaunchAgent template under
                  docs/campaigns/2026-07-09-research-reading-spine/ — never
                  auto-promotes; use suite proposal approve below.
                </p>
                {offlineRun.html ? (
                  <div
                    className="prose border rounded p-2 text-sm max-h-40 overflow-auto"
                    data-testid="antiek-bench-run-offline-html"
                    dangerouslySetInnerHTML={{ __html: offlineRun.html }}
                  />
                ) : null}
              </div>
            ) : null}
            {leaderboard && (
              <div
                className="font-mono text-[13px] space-y-2"
                data-testid="antiek-bench-leaderboard-summary"
              >
                <Row label="Week" value={leaderboard.week_id} />
                <Row label="Runs" value={String(leaderboard.run_count)} />
                <Row
                  label="Recommended"
                  value={
                    leaderboard.recommended_model_id
                      ? `${leaderboard.recommended_model_id} (${leaderboard.recommended_mean_score ?? "—"})`
                      : "(none — no offline runs)"
                  }
                />
                <Row label="View" value={leaderboard.view_format} />
                {leaderboard.recommended_model_id ? (
                  <button
                    type="button"
                    data-testid="antiek-bench-leaderboard-install-recommended"
                    disabled={treeBusy || leaderboardBusy}
                    onClick={() => void onInstallRecommendedFromLeaderboard()}
                    className="px-3 py-1.5 rounded border border-ink dark:border-bright text-sm font-mono hover:bg-ink/5 dark:hover:bg-bright/10 disabled:opacity-50"
                  >
                    Install recommended as decision-tree driver
                  </button>
                ) : null}
                {/* Residual (adf): reciprocal ND vs bench delta (parity ade · both advisory). */}
                <div
                  className="rounded border border-ink/15 p-2 space-y-1 dark:border-bright/15"
                  data-testid="leaderboard-nd-delta"
                  data-delta-status={ndBenchDelta.status}
                  data-nd-suggested={ndBenchDelta.nd_suggested}
                  data-bench-recommended={ndBenchDelta.bench_recommended}
                  data-advisory-only="true"
                  data-is-dispatch-authority="false"
                  role="status"
                >
                  <p className="text-[11px] font-mono opacity-90">
                    NotDiamond advisory:{" "}
                    <code data-testid="leaderboard-nd-suggested">
                      {ndBenchDelta.nd_suggested || "(none)"}
                    </code>
                  </p>
                  <p className="text-[11px] font-mono opacity-90">
                    Antiek-bench weekly:{" "}
                    <code data-testid="leaderboard-bench-recommended">
                      {ndBenchDelta.bench_recommended || "(unset)"}
                    </code>
                  </p>
                  <p
                    className="text-[11px] font-mono"
                    data-testid="leaderboard-nd-delta-label"
                  >
                    {notDiamondBenchDeltaLabel(ndBenchDelta)}
                  </p>
                  <a
                    href="#notdiamond-advisory"
                    className="text-[11px] font-mono underline opacity-80 hover:opacity-100"
                    data-testid="leaderboard-nd-advisory-link"
                    title="Jump to NotDiamond weekly advisory (advisory only · never dispatch authority)"
                  >
                    Open NotDiamond advisory
                  </a>
                </div>
                {(leaderboard.models || []).length === 0 ? (
                  <p className="text-[11px] text-ink-soft dark:text-starlight">
                    No offline runs for this week yet.
                  </p>
                ) : (
                  <>
                    {/* Residual (adr): per-task weekly best (advisory · never auto-route). */}
                    {(() => {
                      const taskClasses =
                        (leaderboard.task_classes || []).length > 0
                          ? leaderboard.task_classes
                          : Array.from(
                              new Set(
                                (leaderboard.models || []).flatMap((m) =>
                                  Object.keys(m.by_task_class || {}),
                                ),
                              ),
                            ).sort();
                      if (taskClasses.length === 0) return null;
                      const bestByTask: Array<{
                        task_class: string;
                        model_id: string;
                        score: number;
                      }> = [];
                      for (const tc of taskClasses) {
                        let bestId = "";
                        let bestScore = -Infinity;
                        for (const m of leaderboard.models || []) {
                          const sc = (m.by_task_class || {})[tc];
                          if (typeof sc === "number" && sc > bestScore) {
                            bestScore = sc;
                            bestId = m.model_id;
                          }
                        }
                        if (bestId) {
                          bestByTask.push({
                            task_class: tc,
                            model_id: bestId,
                            score: bestScore,
                          });
                        }
                      }
                      if (bestByTask.length === 0) return null;
                      return (
                        <div
                          className="font-mono text-[11px] space-y-1 border border-ink/10 rounded p-2 dark:border-bright/10"
                          data-testid="antiek-bench-leaderboard-by-task"
                          data-task-class-count={String(bestByTask.length)}
                          data-advisory-only="true"
                          data-is-dispatch-authority="false"
                          role="status"
                        >
                          <p className="opacity-90">
                            Best model by task class (advisory · never
                            auto-routes):
                          </p>
                          <ul data-testid="antiek-bench-leaderboard-task-winners">
                            {bestByTask.map((row) => (
                              <li
                                key={row.task_class}
                                className="flex flex-wrap items-center gap-2"
                                data-task-class={row.task_class}
                                data-best-model-id={row.model_id}
                                data-best-score={String(row.score)}
                              >
                                <span>
                                  <strong>{row.task_class}</strong>:{" "}
                                  {row.model_id} (
                                  {Number.isFinite(row.score)
                                    ? row.score.toFixed(2)
                                    : "—"}
                                  )
                                </span>
                                {/* Residual (ads): install best-by-task as driver (advisory). */}
                                <button
                                  type="button"
                                  data-testid={`antiek-bench-leaderboard-install-task-${row.task_class}`}
                                  data-install-model-id={row.model_id}
                                  data-install-task-class={row.task_class}
                                  data-advisory-only="true"
                                  disabled={treeBusy || leaderboardBusy}
                                  onClick={() =>
                                    void onInstallLeaderboardModelAsDriver(
                                      row.model_id,
                                      { taskClass: row.task_class },
                                    )
                                  }
                                  className="px-2 py-0.5 rounded border border-ink/40 dark:border-bright/40 text-[10px] font-mono hover:bg-ink/5 dark:hover:bg-bright/10 disabled:opacity-50"
                                  title={`Install ${row.model_id} (best ${row.task_class}) as decision-tree driver — advisory only`}
                                >
                                  Install as driver
                                </button>
                              </li>
                            ))}
                          </ul>
                        </div>
                      );
                    })()}
                    <ul
                      data-testid="antiek-bench-leaderboard-models"
                      className="space-y-1"
                    >
                      {leaderboard.models.map((m) => {
                        const btc = m.by_task_class || {};
                        const taskParts = Object.entries(btc)
                          .sort(([a], [b]) => a.localeCompare(b))
                          .map(([tc, sc]) =>
                            typeof sc === "number"
                              ? `${tc}=${sc.toFixed(2)}`
                              : `${tc}=—`,
                          );
                        return (
                          <li
                            key={m.model_id}
                            data-model-id={m.model_id}
                            data-mean-score={
                              m.mean_score != null ? String(m.mean_score) : ""
                            }
                            data-task-class-count={String(taskParts.length)}
                            data-by-task-class={
                              taskParts.length > 0 ? taskParts.join("·") : ""
                            }
                          >
                            <strong>{m.model_id}</strong>: mean=
                            {m.mean_score ?? "—"}
                            {taskParts.length > 0 ? (
                              <span className="opacity-80">
                                {" "}
                                · {taskParts.join(" · ")}
                              </span>
                            ) : null}
                          </li>
                        );
                      })}
                    </ul>
                  </>
                )}
                {leaderboard.notes?.map((n) => (
                  <p
                    key={n}
                    className="text-[11px] text-ink-soft dark:text-starlight"
                  >
                    {n}
                  </p>
                ))}
                {leaderboard.html ? (
                  <div
                    className="prose border rounded p-2 text-sm max-h-48 overflow-auto"
                    data-testid="antiek-bench-leaderboard-html"
                    dangerouslySetInnerHTML={{ __html: leaderboard.html }}
                  />
                ) : null}
              </div>
            )}
          </div>
        </LemonCard>

        <LemonCard
          title="Antiek-bench competitive dogfood"
          elevation="z1"
          colour="glacial"
        >
          <div
            id="antiek-bench-dogfood"
            className="p-4 space-y-3"
            data-testid="antiek-bench-dogfood-panel"
            data-view-format="html"
            data-propose-not-promote="true"
            data-auto-promoted="false"
            data-suite-version={dogfood?.suite_version || ""}
            data-label={dogfood?.label || ""}
            data-source={dogfood?.source || ""}
            data-settings-panel={dogfood?.settings_panel || ""}
            data-item-count={
              dogfood ? String(dogfood.item_count ?? 0) : ""
            }
            data-book-qa-count={
              dogfood
                ? String((dogfood.by_task_class || {}).book_qa ?? 0)
                : ""
            }
            data-wrestle-count={
              dogfood
                ? String((dogfood.by_task_class || {}).wrestle ?? 0)
                : ""
            }
            data-distill-count={
              dogfood
                ? String((dogfood.by_task_class || {}).distill ?? 0)
                : ""
            }
            data-synthesize-count={
              dogfood
                ? String((dogfood.by_task_class || {}).synthesize ?? 0)
                : ""
            }
          >
            <p className="text-sm text-ink dark:text-bright">
              Offline multi-task-class fixtures (distill / synthesize / wrestle
              / book_qa) for weekly model comparison. Listing only — never
              auto-promotes the active suite.
            </p>
            {dogfoodError && (
              <p className="text-sm text-red-700 dark:text-red-300 font-mono">
                {dogfoodError}
              </p>
            )}
            <button
              type="button"
              data-testid="antiek-bench-dogfood-refresh"
              onClick={() => void onRefreshDogfood()}
              disabled={dogfoodBusy}
              className="px-3 py-1.5 rounded border border-ink dark:border-bright text-sm font-mono hover:bg-ink/5 dark:hover:bg-bright/10 disabled:opacity-50"
            >
              {dogfoodBusy ? "Loading…" : "Refresh dogfood fixtures"}
            </button>
            {dogfood && (
              <div
                className="font-mono text-[13px] space-y-2"
                data-testid="antiek-bench-dogfood-summary"
                data-suite-version={dogfood.suite_version || ""}
                data-label={dogfood.label || ""}
                data-item-count={String(dogfood.item_count ?? 0)}
                data-auto-promoted={String(dogfood.auto_promoted === true)}
                data-view-format={dogfood.view_format || "html"}
                data-source={dogfood.source || ""}
                data-settings-panel={dogfood.settings_panel || ""}
                data-book-qa-count={String(
                  (dogfood.by_task_class || {}).book_qa ?? 0,
                )}
                data-wrestle-count={String(
                  (dogfood.by_task_class || {}).wrestle ?? 0,
                )}
                data-distill-count={String(
                  (dogfood.by_task_class || {}).distill ?? 0,
                )}
                data-synthesize-count={String(
                  (dogfood.by_task_class || {}).synthesize ?? 0,
                )}
                data-has-write-seed-posture={String(
                  (dogfood.items || []).some(
                    (it) => it.item_id === "dogfood-wrestle-write-seed",
                  ),
                )}
                data-has-float-evidence-posture={String(
                  (dogfood.items || []).some(
                    (it) => it.item_id === "dogfood-synth-float-evidence",
                  ),
                )}
                data-has-budget-foresight-posture={String(
                  (dogfood.items || []).some(
                    (it) => it.item_id === "dogfood-distill-budget-foresight",
                  ),
                )}
                data-has-faraday-book-qa-posture={String(
                  (dogfood.items || []).some(
                    (it) => it.item_id === "dogfood-book-faraday-induction",
                  ),
                )}
                data-has-collective-unit-write-seed-posture={String(
                  (dogfood.items || []).some(
                    (it) =>
                      it.item_id ===
                      "dogfood-wrestle-collective-unit-write-seed",
                  ),
                )}
                data-has-boole-book-qa-posture={String(
                  (dogfood.items || []).some(
                    (it) => it.item_id === "dogfood-book-boole-laws-of-thought",
                  ),
                )}
                data-has-heaviside-book-qa-posture={String(
                  (dogfood.items || []).some(
                    (it) => it.item_id === "dogfood-book-heaviside-em",
                  ),
                )}
                data-has-shannon-book-qa-posture={String(
                  (dogfood.items || []).some(
                    (it) => it.item_id === "dogfood-book-shannon-communication",
                  ),
                )}
                data-has-turing-book-qa-posture={String(
                  (dogfood.items || []).some(
                    (it) =>
                      it.item_id === "dogfood-book-turing-computable-numbers",
                  ),
                )}
                data-has-lovelace-book-qa-posture={String(
                  (dogfood.items || []).some(
                    (it) =>
                      it.item_id === "dogfood-book-lovelace-analytical-engine",
                  ),
                )}
                data-has-godel-book-qa-posture={String(
                  (dogfood.items || []).some(
                    (it) =>
                      it.item_id === "dogfood-book-godel-incompleteness",
                  ),
                )}
                data-has-fourier-book-qa-posture={String(
                  (dogfood.items || []).some(
                    (it) => it.item_id === "dogfood-book-fourier-heat",
                  ),
                )}
                data-has-citation-trust-ungrounded-posture={String(
                  (dogfood.items || []).some(
                    (it) =>
                      it.item_id ===
                      "dogfood-wrestle-citation-trust-ungrounded",
                  ),
                )}
                data-has-twin-cross-asset-merge-write-seed-posture={String(
                  (dogfood.items || []).some(
                    (it) =>
                      it.item_id ===
                      "dogfood-wrestle-twin-cross-asset-merge-write-seed",
                  ),
                )}
                data-has-collective-written-analysis-write-seed-posture={String(
                  (dogfood.items || []).some(
                    (it) =>
                      it.item_id ===
                      "dogfood-wrestle-collective-written-analysis-write-seed",
                  ),
                )}
                data-has-write-seed-has-body-posture={String(
                  (dogfood.items || []).some(
                    (it) =>
                      it.item_id === "dogfood-wrestle-write-seed-has-body",
                  ),
                )}
                data-has-seamless-write-path-posture={String(
                  (dogfood.items || []).some(
                    (it) =>
                      it.item_id === "dogfood-wrestle-seamless-write-path",
                  ),
                )}
                data-has-intelligent-search-context-write-posture={String(
                  (dogfood.items || []).some(
                    (it) =>
                      it.item_id ===
                      "dogfood-wrestle-intelligent-search-context-write",
                  ),
                )}
                data-has-written-analysis-open-write-source-posture={String(
                  (dogfood.items || []).some(
                    (it) =>
                      it.item_id ===
                      "dogfood-wrestle-written-analysis-open-write-source",
                  ),
                )}
                data-has-continue-as-unit-path-posture={String(
                  (dogfood.items || []).some(
                    (it) =>
                      it.item_id === "dogfood-wrestle-continue-as-unit-path",
                  ),
                )}
                data-has-select-open-path-posture={String(
                  (dogfood.items || []).some(
                    (it) => it.item_id === "dogfood-wrestle-select-open-path",
                  ),
                )}
                data-has-unit-restore-path-posture={String(
                  (dogfood.items || []).some(
                    (it) => it.item_id === "dogfood-wrestle-unit-restore-path",
                  ),
                )}
                data-has-select-recent-path-posture={String(
                  (dogfood.items || []).some(
                    (it) =>
                      it.item_id === "dogfood-wrestle-select-recent-path",
                  ),
                )}
                data-has-research-workstation-spine-posture={String(
                  (dogfood.items || []).some(
                    (it) =>
                      it.item_id ===
                      "dogfood-wrestle-research-workstation-spine",
                  ),
                )}
                data-has-highlight-deep-research-path-posture={String(
                  (dogfood.items || []).some(
                    (it) =>
                      it.item_id ===
                      "dogfood-wrestle-highlight-deep-research-path",
                  ),
                )}
                data-has-talk-to-book-twins-posture={String(
                  (dogfood.items || []).some(
                    (it) =>
                      it.item_id === "dogfood-wrestle-talk-to-book-twins",
                  ),
                )}
                data-has-meta-reading-twins-posture={String(
                  (dogfood.items || []).some(
                    (it) =>
                      it.item_id === "dogfood-wrestle-meta-reading-twins",
                  ),
                )}
                data-has-research-this-twins-posture={String(
                  (dogfood.items || []).some(
                    (it) =>
                      it.item_id === "dogfood-wrestle-research-this-twins",
                  ),
                )}
                data-has-spawn-merge-path-posture={String(
                  (dogfood.items || []).some(
                    (it) => it.item_id === "dogfood-wrestle-spawn-merge-path",
                  ),
                )}
                data-has-collective-multi-spawn-merge-posture={String(
                  (dogfood.items || []).some(
                    (it) =>
                      it.item_id ===
                      "dogfood-wrestle-collective-multi-spawn-merge",
                  ),
                )}
                data-has-pub-quick-call-matrix-posture={String(
                  (dogfood.items || []).some(
                    (it) =>
                      it.item_id === "dogfood-wrestle-pub-quick-call-matrix",
                  ),
                )}
                data-has-budget-foresight-pub-refs-posture={String(
                  (dogfood.items || []).some(
                    (it) =>
                      it.item_id === "dogfood-wrestle-budget-foresight-pub-refs",
                  ),
                )}
                data-has-purchase-seamless-port-posture={String(
                  (dogfood.items || []).some(
                    (it) =>
                      it.item_id === "dogfood-wrestle-purchase-seamless-port",
                  ),
                )}
                data-has-domain-aware-twin-search-posture={String(
                  (dogfood.items || []).some(
                    (it) =>
                      it.item_id === "dogfood-wrestle-domain-aware-twin-search",
                  ),
                )}
                data-has-collective-unit-twin-seed-posture={String(
                  (dogfood.items || []).some(
                    (it) =>
                      it.item_id === "dogfood-wrestle-collective-unit-twin-seed",
                  ),
                )}
                data-has-moil-deposit-twin-honesty-posture={String(
                  (dogfood.items || []).some(
                    (it) =>
                      it.item_id === "dogfood-wrestle-moil-deposit-twin-honesty",
                  ),
                )}
                data-propose-not-promote="true"
              >
                <Row label="Suite" value={dogfood.suite_version} />
                <Row label="Label" value={dogfood.label} />
                <Row label="Items" value={String(dogfood.item_count)} />
                <Row
                  label="Auto-promoted"
                  value={String(dogfood.auto_promoted)}
                />
                <Row label="View" value={dogfood.view_format} />
                {/* Residual (su/tv/tz/ud/us/ve/vl/wd/ado): posture honesty for recursive rewrite. */}
                {(dogfood.items || []).some((it) =>
                  [
                    "dogfood-wrestle-write-seed",
                    "dogfood-synth-float-evidence",
                    "dogfood-distill-budget-foresight",
                    "dogfood-book-faraday-induction",
                    "dogfood-wrestle-collective-unit-write-seed",
                    "dogfood-book-boole-laws-of-thought",
                    "dogfood-book-heaviside-em",
                    "dogfood-book-shannon-communication",
                    "dogfood-book-turing-computable-numbers",
                    "dogfood-book-lovelace-analytical-engine",
                    "dogfood-book-godel-incompleteness",
                    "dogfood-book-fourier-heat",
                    "dogfood-wrestle-citation-trust-ungrounded",
                    "dogfood-wrestle-twin-cross-asset-merge-write-seed",
                    "dogfood-wrestle-collective-written-analysis-write-seed",
                    "dogfood-wrestle-write-seed-has-body",
                    "dogfood-wrestle-seamless-write-path",
                    "dogfood-wrestle-intelligent-search-context-write",
                    "dogfood-wrestle-written-analysis-open-write-source",
                    "dogfood-wrestle-continue-as-unit-path",
                    "dogfood-wrestle-select-open-path",
                    "dogfood-wrestle-unit-restore-path",
                    "dogfood-wrestle-select-recent-path",
                    "dogfood-wrestle-research-workstation-spine",
                    "dogfood-wrestle-highlight-deep-research-path",
                    "dogfood-wrestle-talk-to-book-twins",
                    "dogfood-wrestle-meta-reading-twins",
                    "dogfood-wrestle-research-this-twins",
                    "dogfood-wrestle-spawn-merge-path",
                    "dogfood-wrestle-collective-multi-spawn-merge",
                    "dogfood-wrestle-pub-quick-call-matrix",
                    "dogfood-wrestle-budget-foresight-pub-refs",
                    "dogfood-wrestle-purchase-seamless-port",
                  ].includes(it.item_id),
                ) ? (
                  <p
                    className="text-[11px] text-ink-soft dark:text-starlight"
                    data-testid="antiek-bench-dogfood-v2-postures"
                    role="status"
                  >
                    Spine postures (v26): write-seed · float evidence · budget
                    foresight · Faraday book_qa · collective unit write-seed ·
                    Boole book_qa · Heaviside book_qa · Shannon book_qa ·
                    Turing book_qa · Lovelace book_qa · citation-trust
                    ungrounded · twin cross-asset merge write-seed ·
                    collective written analysis write-seed · write-seed
                    has-body · seamless Write path · intelligent search
                    context Write · written analysis Open Write source ·
                    continue-as-unit path · Select open path · unit restore
                    path · Select recent path · ResearchWorkstation spine ·
                    highlight → DR path · Gödel book_qa · Fourier book_qa ·
                    TalkToBook twins · MetaReading twins · ResearchThis twins ·
                    spawn merge path · multi-spawn collective merge ·
                    knowledge-dense pub quick-call matrix · budget foresight with pubs ·
                    purchase seamless port · domain-aware twin search · collective unit twin seed · MO deposit twin honesty
                    (listing only · not auto-promoted)
                  </p>
                ) : null}
                {/* Residual (adw): has-body posture → rewrite + usage deep-links. */}
                {(dogfood.items || []).some(
                  (it) => it.item_id === "dogfood-wrestle-write-seed-has-body",
                ) ? (
                  <div
                    className="flex flex-wrap items-center gap-2 text-[11px]"
                    data-testid="antiek-bench-dogfood-has-body-links"
                    data-has-write-seed-has-body-posture="true"
                    data-propose-not-promote="true"
                    role="navigation"
                    aria-label="Write-seed has-body dogfood → recursive rewrite"
                  >
                    <a
                      href="#antiek-bench-suite-proposal"
                      className="underline opacity-80 hover:opacity-100"
                      data-testid="dogfood-has-body-suite-proposal-link"
                      title="Recursive suite rewrite proposal (body honesty matrix · never auto-promote)"
                    >
                      Body honesty → suite rewrite
                    </a>
                    <span className="opacity-40" aria-hidden>
                      ·
                    </span>
                    <a
                      href="#antiek-bench-usage"
                      className="underline opacity-80 hover:opacity-100"
                      data-testid="dogfood-has-body-usage-link"
                      title="Usage summary with with_body / title_only / unknown counts"
                    >
                      Usage body matrix
                    </a>
                  </div>
                ) : null}
                <ul data-testid="antiek-bench-dogfood-classes" className="space-y-1">
                  {Object.entries(dogfood.by_task_class || {}).map(
                    ([tc, n]) => (
                      <li key={tc}>
                        <strong>{tc}</strong>: {n}
                      </li>
                    ),
                  )}
                </ul>
                {/* Residual (we/ya): list all dogfood items; stamp count match honesty. */}
                <ul
                  data-testid="antiek-bench-dogfood-items"
                  className="space-y-1 text-[11px]"
                  data-listed-count={String((dogfood.items || []).length)}
                  data-item-count={String(dogfood.item_count ?? 0)}
                  data-item-count-matches-listed={String(
                    (dogfood.items || []).length ===
                      Number(dogfood.item_count ?? 0),
                  )}
                  data-view-format={dogfood.view_format || "html"}
                  data-truncated="false"
                >
                  {(dogfood.items || []).map((it) => (
                    <li
                      key={it.item_id}
                      data-item-id={it.item_id}
                      data-task-class={it.task_class}
                    >
                      [{it.task_class}] {it.item_id}
                    </li>
                  ))}
                </ul>
                {dogfood.notes?.map((n) => (
                  <p
                    key={n}
                    className="text-[11px] text-ink-soft dark:text-starlight"
                  >
                    {n}
                  </p>
                ))}
                {dogfood.html ? (
                  <div
                    className="prose border rounded p-2 text-sm max-h-48 overflow-auto"
                    data-testid="antiek-bench-dogfood-html"
                    dangerouslySetInnerHTML={{ __html: dogfood.html }}
                  />
                ) : null}
              </div>
            )}
          </div>
        </LemonCard>

        <LemonCard title="Antiek-bench usage" elevation="z1" colour="glacial">
          <div
            className="p-4 space-y-3"
            id="antiek-bench-usage"
            data-testid="antiek-bench-usage-panel"
            data-view-format="html"
          >
            <p className="text-sm text-ink dark:text-bright">
              Weekly usage patterns recorded from engagement flywheel outcomes
              (task classes that feed recursive suite rewrite proposals). Not a
              live multi-provider bench run.
            </p>
            {usageError && (
              <p className="text-sm text-red-700 dark:text-red-300 font-mono">
                {usageError}
              </p>
            )}
            <button
              type="button"
              data-testid="antiek-bench-usage-refresh"
              onClick={() => void onRefreshUsage()}
              disabled={usageBusy}
              className="px-3 py-1.5 rounded border border-ink dark:border-bright text-sm font-mono hover:bg-ink/5 dark:hover:bg-bright/10 disabled:opacity-50"
            >
              {usageBusy ? "Loading…" : "Refresh usage summary"}
            </button>
            {usage && (
              <div className="font-mono text-[13px] space-y-2" data-testid="antiek-bench-usage-summary">
                <Row label="Events" value={String(usage.event_count)} />
                <Row label="View" value={usage.view_format} />
                {/* Residual (rz): Write-seed weekly metrics from substrate SSOT (ry). */}
                {(usage.write_seed_event_count != null ||
                  usage.write_seed_source_count != null) && (
                  <p
                    className="text-[11px] text-ink-soft dark:text-starlight border border-ink/10 rounded p-2 dark:border-bright/10"
                    data-testid="antiek-bench-usage-write-seed-metrics"
                    data-write-seed-event-count={String(
                      usage.write_seed_event_count ?? 0,
                    )}
                    data-write-seed-source-count={String(
                      usage.write_seed_source_count ?? 0,
                    )}
                    data-write-seed-known-count={String(
                      usage.write_seed_known_count ?? writeSeedKnownCount,
                    )}
                    // Residual (acu): body honesty from substrate act aggregates.
                    data-write-seed-with-body-count={String(
                      usage.write_seed_with_body_count ?? 0,
                    )}
                    data-write-seed-title-only-count={String(
                      usage.write_seed_title_only_count ?? 0,
                    )}
                    data-write-seed-body-unknown-count={String(
                      usage.write_seed_body_unknown_count ?? 0,
                    )}
                    data-propose-not-promote="true"
                    role="status"
                  >
                    Write seed this week: events=
                    {usage.write_seed_event_count ?? 0} · sources=
                    {usage.write_seed_source_count ?? 0} · known_catalog=
                    {usage.write_seed_known_count ?? writeSeedKnownCount}{" "}
                    (recursive note-taker → Write · not auto-promoted)
                    {" · body honesty: with_body="}
                    {usage.write_seed_with_body_count ?? 0}
                    {" · title_only="}
                    {usage.write_seed_title_only_count ?? 0}
                    {" · unknown="}
                    {usage.write_seed_body_unknown_count ?? 0}
                    {" (title-only → failed for suite rewrite)"}
                    {" · "}
                    {/* Residual (sr): jump to suite proposal (propose≠promote). */}
                    <a
                      href="#antiek-bench-suite-proposal"
                      className="underline opacity-80 hover:opacity-100"
                      data-testid="antiek-bench-write-seed-suite-link"
                      title="Open suite rewrite proposal (not auto-promoted)"
                    >
                      View suite proposal
                    </a>
                  </p>
                )}
                {Object.keys(usage.by_task_class || {}).length === 0 ? (
                  <p className="text-[11px] text-ink-soft dark:text-starlight">
                    No usage events yet.
                  </p>
                ) : (
                  <ul className="space-y-1" data-testid="antiek-bench-usage-classes">
                    {Object.entries(usage.by_task_class).map(([tc, bucket]) => (
                      <li key={tc}>
                        <strong>{tc}</strong>: total={bucket.total ?? 0}{" "}
                        worked={bucket.worked ?? 0} failed={bucket.failed ?? 0}
                      </li>
                    ))}
                  </ul>
                )}
                {/* Residual (hb): source breakdown (interactive vs autonomous). */}
                {Object.keys(usage.by_source || {}).length > 0 ? (
                  <ul
                    className="space-y-1"
                    data-testid="antiek-bench-usage-sources"
                    data-write-seed-source-count={String(
                      usage.write_seed_source_count != null
                        ? usage.write_seed_source_count
                        : Object.keys(usage.by_source || {}).filter((s) =>
                            isWriteSeedFeedSource(s),
                          ).length,
                    )}
                  >
                    {Object.entries(usage.by_source || {}).map(([src, n]) => {
                      const writeSeed = isWriteSeedFeedSource(src);
                      return (
                        <li
                          key={src}
                          data-testid="antiek-bench-usage-source-row"
                          data-source={src}
                          data-write-seed-feed={String(writeSeed)}
                        >
                          <strong>{src}</strong>: {n}
                          {writeSeed ? (
                            <span data-testid="antiek-bench-usage-source-write-seed">
                              {" "}
                              [write seed]
                            </span>
                          ) : null}
                        </li>
                      );
                    })}
                  </ul>
                ) : null}
                {/* Residual (nx/os): known feed sources legend (chase/DR + MO/collective). */}
                {(usage.known_sources || []).length > 0 ? (
                  <p
                    className="text-[11px] font-mono opacity-80"
                    data-testid="antiek-bench-usage-known-sources"
                    data-source-count={String(
                      (usage.known_sources || []).length,
                    )}
                    data-has-twin-chase={String(
                      (usage.known_sources || []).includes("twin_chase"),
                    )}
                    data-has-floating-dr={String(
                      (usage.known_sources || []).includes(
                        "floating_deep_research",
                      ),
                    )}
                    data-has-midnight-oil={String(
                      (usage.known_sources || []).includes("midnight_oil"),
                    )}
                    data-has-collective-merge={String(
                      (usage.known_sources || []).includes("collective_merge"),
                    )}
                    data-has-deep-research-session={String(
                      (usage.known_sources || []).includes(
                        "deep_research_session",
                      ),
                    )}
                    data-has-research-progress-complete={String(
                      (usage.known_sources || []).includes(
                        "research_progress_complete",
                      ),
                    )}
                    data-has-midnight-oil-deposit={String(
                      (usage.known_sources || []).includes(
                        "midnight_oil_deposit",
                      ),
                    )}
                    data-has-hosted-html-document={String(
                      (usage.known_sources || []).includes(
                        "hosted_html_document",
                      ),
                    )}
                    data-has-evidence-pack={String(
                      (usage.known_sources || []).includes("evidence_pack"),
                    )}
                    data-has-publication-hydrate={String(
                      (usage.known_sources || []).includes(
                        "publication_hydrate",
                      ),
                    )}
                    data-has-session-flywheel-complete={String(
                      (usage.known_sources || []).includes(
                        "session_flywheel_complete",
                      ),
                    )}
                    data-has-context-search={String(
                      (usage.known_sources || []).includes("context_search"),
                    )}
                    data-has-research-context-pack={String(
                      (usage.known_sources || []).includes(
                        "research_context_pack",
                      ),
                    )}
                    data-has-research-progress-draft={String(
                      (usage.known_sources || []).includes(
                        "research_progress_draft",
                      ),
                    )}
                    data-has-research-progress-complete={String(
                      (usage.known_sources || []).includes(
                        "research_progress_complete",
                      ),
                    )}
                    data-has-twin-promote-context={String(
                      (usage.known_sources || []).includes(
                        "twin_promote_context",
                      ),
                    )}
                    data-write-seed-known-count={String(writeSeedKnownCount)}
                    role="status"
                  >
                    Known feed sources: {(usage.known_sources || []).join(", ")}
                    {writeSeedKnownCount > 0 ? (
                      <>
                        {" "}
                        ·{" "}
                        <span data-testid="antiek-bench-write-seed-known-count">
                          Write seed feeds: {writeSeedKnownCount}{" "}
                          (recursive note-taker → Write)
                        </span>
                      </>
                    ) : null}
                  </p>
                ) : null}
                {usage.notes?.map((n) => (
                  <p
                    key={n}
                    className="text-[11px] text-ink-soft dark:text-starlight"
                  >
                    {n}
                  </p>
                ))}
                {usage.html ? (
                  <div
                    className="prose border rounded p-2 text-sm max-h-48 overflow-auto"
                    data-testid="antiek-bench-usage-html"
                    dangerouslySetInnerHTML={{ __html: usage.html }}
                  />
                ) : null}
              </div>
            )}
          </div>
        </LemonCard>

        <LemonCard title="Antiek-bench suite proposal" elevation="z1" colour="glacial">
          <div
            id="antiek-bench-suite-proposal"
            className="p-4 space-y-3"
            data-testid="antiek-bench-suite-proposal-panel"
            data-view-format="html"
            data-propose-not-promote="true"
            data-auto-promoted={String(
              suiteProposal?.auto_promoted === true,
            )}
            data-has-proposal={String(Boolean(suiteProposal?.has_proposal))}
          >
            <p className="text-sm text-ink dark:text-bright">
              Recursive suite rewrite proposal derived from recorded usage
              events. Status is always <strong>proposed</strong> here —
              operator must explicitly approve/promote (not auto-active).
            </p>
            {/* Residual (fg): explicit propose≠promote honesty banner. */}
            <p
              className="text-[11px] font-mono text-aurora"
              data-testid="antiek-bench-propose-not-promote"
              role="status"
            >
              Invariant: propose ≠ auto-promote · auto_promoted=
              {String(suiteProposal?.auto_promoted ?? false)}
            </p>
            {/* Residual (nt/yj): dual-gate L7 Never-router checklist + ND panel. */}
            <p className="text-[11px] font-mono space-x-3">
              <a
                href="/docs/campaigns/2026-07-09-research-reading-spine/DUAL-GATE-L1-L4-OPERATOR-CHECKLIST.md#l7-notdiamond"
                data-testid="antiek-bench-dual-gate-checklist-link"
                className="underline opacity-80 hover:opacity-100"
                title="Dual-gate L7 NotDiamond never-router checklist (advisory only forever)"
              >
                Dual-gate L7 ND checklist
              </a>
              {/* Residual (ro): deep-link suite L7 banner → ND advisory panel. */}
              <a
                href="#notdiamond-advisory"
                data-testid="antiek-bench-notdiamond-advisory-only"
                data-notdiamond-authority="advisory_only"
                className="underline opacity-80 hover:opacity-100"
                title="Jump to NotDiamond weekly advisory vs installed driver (advisory only)"
              >
                NotDiamond: advisory only (L7 · never dispatch authority)
              </a>
            </p>
            {/* Residual (ht/pe/qa): recursive rewrite metrics + primary feed. */}
            {suiteProposal ? (
              <div
                className="font-mono text-[11px] text-ink-soft dark:text-starlight space-y-1"
                data-testid="antiek-bench-suite-proposal-metrics"
                data-has-proposal={String(Boolean(suiteProposal.has_proposal))}
                data-status={suiteProposal.status ?? ""}
                data-proposal-id={suiteProposal.proposal_id ?? ""}
                data-event-count={String(suiteProposal.event_count ?? 0)}
                data-proposed-task-count={String(
                  (suiteProposal.added_item_ids || []).length,
                )}
                data-auto-promoted={String(
                  suiteProposal.auto_promoted === true,
                )}
                data-feed-source-count={String(
                  Object.keys(usage?.by_source || {}).length,
                )}
                data-primary-feed-source={primaryRewriteFeed?.source ?? ""}
                data-primary-feed-count={String(primaryRewriteFeed?.count ?? 0)}
                data-has-rationale={String(
                  Boolean((suiteProposal.rationale || "").trim()),
                )}
                // Residual (acy/adp): full body honesty matrix for rewrite.
                data-title-only-write-seed-count={String(
                  suiteProposal.title_only_write_seed_count ?? 0,
                )}
                data-with-body-write-seed-count={String(
                  suiteProposal.with_body_write_seed_count ?? 0,
                )}
                data-body-unknown-write-seed-count={String(
                  suiteProposal.body_unknown_write_seed_count ?? 0,
                )}
                data-propose-not-promote="true"
                data-view-format="html"
                role="status"
              >
                Recursive rewrite · events={suiteProposal.event_count ?? 0} ·
                proposed_tasks=
                {(suiteProposal.added_item_ids || []).length} · status=
                {suiteProposal.status ?? "—"} · feed_sources=
                {Object.keys(usage?.by_source || {}).length}
                {" · body honesty: with_body="}
                {suiteProposal.with_body_write_seed_count ?? 0}
                {" · title_only="}
                {suiteProposal.title_only_write_seed_count ?? 0}
                {" · unknown="}
                {suiteProposal.body_unknown_write_seed_count ?? 0}
                {(suiteProposal.title_only_write_seed_count ?? 0) > 0 ? (
                  <>
                    {" "}
                    · title_only_write_seeds=
                    {suiteProposal.title_only_write_seed_count}
                  </>
                ) : null}
                {primaryRewriteFeed ? (
                  <>
                    {" "}
                    · primary_feed={primaryRewriteFeed.source}=
                    {primaryRewriteFeed.count}
                  </>
                ) : null}
              </div>
            ) : null}
            {/* Residual (hf/nz/os/qa): ranked feed sources + primary rewrite driver. */}
            {Object.keys(usage?.by_source || {}).length > 0 ? (
              <>
                {primaryRewriteFeed ? (
                  <p
                    className="text-[11px] font-mono text-ink-soft dark:text-starlight border border-ink/10 rounded p-2 dark:border-bright/10"
                    data-testid="antiek-bench-suite-proposal-primary-feed"
                    data-primary-feed-source={primaryRewriteFeed.source}
                    data-primary-feed-count={String(primaryRewriteFeed.count)}
                    data-write-seed-feed={String(
                      isWriteSeedFeedSource(primaryRewriteFeed.source),
                    )}
                    data-proposed-task-count={String(
                      (suiteProposal?.added_item_ids || []).length,
                    )}
                    data-propose-not-promote="true"
                    data-view-format="html"
                    role="status"
                  >
                    Primary rewrite feed (drove this week&apos;s proposal
                    delta):{" "}
                    <strong>{primaryRewriteFeed.source}</strong>=
                    {primaryRewriteFeed.count} event(s) · proposed_tasks=
                    {(suiteProposal?.added_item_ids || []).length} (not
                    auto-promoted)
                    {isWriteSeedFeedSource(primaryRewriteFeed.source) ? (
                      <>
                        {" "}
                        ·{" "}
                        <span data-testid="antiek-bench-primary-feed-write-seed">
                          Write seed feed (recursive note-taker → Write)
                        </span>
                      </>
                    ) : null}
                  </p>
                ) : null}
                <p
                  className="text-[11px] font-mono text-ink-soft dark:text-starlight"
                  data-testid="antiek-bench-suite-proposal-feed-sources"
                  data-has-twin-chase={String(
                    Boolean((usage?.by_source || {}).twin_chase),
                  )}
                  data-has-floating-dr={String(
                    Boolean((usage?.by_source || {}).floating_deep_research),
                  )}
                  data-has-midnight-oil={String(
                    Boolean((usage?.by_source || {}).midnight_oil),
                  )}
                  data-has-collective-merge={String(
                    Boolean((usage?.by_source || {}).collective_merge),
                  )}
                  data-primary-feed-source={primaryRewriteFeed?.source ?? ""}
                  data-write-seed-ranked-count={String(
                    rankedRewriteFeeds.filter((x) =>
                      isWriteSeedFeedSource(x.source),
                    ).length,
                  )}
                  role="status"
                >
                  Feed sources (ranked):{" "}
                  {rankedRewriteFeeds.map((x, i) => {
                    const writeSeed = isWriteSeedFeedSource(x.source);
                    return (
                      <span key={x.source}>
                        {i > 0 ? " · " : null}
                        <span
                          data-testid="antiek-bench-ranked-feed-row"
                          data-feed-source={x.source}
                          data-feed-count={String(x.count)}
                          data-write-seed-feed={String(writeSeed)}
                        >
                          {x.source}={x.count}
                          {writeSeed ? " [write seed]" : ""}
                        </span>
                      </span>
                    );
                  })}
                </p>
              </>
            ) : (
              <p
                className="text-[11px] font-mono text-ink-soft dark:text-starlight"
                data-testid="antiek-bench-suite-proposal-feed-sources"
                data-has-twin-chase="false"
                data-has-floating-dr="false"
                data-has-midnight-oil="false"
                data-has-collective-merge="false"
                data-primary-feed-source=""
                role="status"
              >
                Feed sources: (none yet — investigation starts, floating DR /
                twin chase opens, engagement flywheel, marketplace host,
                Midnight Oil, and collective merge populate usage)
              </p>
            )}
            {suiteProposalError && (
              <p className="text-sm text-red-700 dark:text-red-300 font-mono">
                {suiteProposalError}
              </p>
            )}
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                data-testid="antiek-bench-suite-proposal-refresh"
                onClick={() => void onRefreshSuiteProposal()}
                disabled={suiteProposalBusy || suiteApproveBusy}
                className="px-3 py-1.5 rounded border border-ink dark:border-bright text-sm font-mono hover:bg-ink/5 dark:hover:bg-bright/10 disabled:opacity-50"
              >
                {suiteProposalBusy ? "Loading…" : "Refresh suite proposal"}
              </button>
              <button
                type="button"
                data-testid="antiek-bench-suite-approve"
                onClick={() => void onApproveSuiteProposal(true)}
                disabled={
                  suiteApproveBusy ||
                  !suiteProposal?.has_proposal ||
                  !suiteProposal?.proposal_id ||
                  suiteProposal.status !== "proposed"
                }
                className="px-3 py-1.5 rounded border border-ink dark:border-bright text-sm font-mono hover:bg-ink/5 dark:hover:bg-bright/10 disabled:opacity-50"
              >
                {suiteApproveBusy ? "Working…" : "Approve & promote"}
              </button>
              <button
                type="button"
                data-testid="antiek-bench-suite-reject"
                onClick={() => void onApproveSuiteProposal(false)}
                disabled={
                  suiteApproveBusy ||
                  !suiteProposal?.has_proposal ||
                  !suiteProposal?.proposal_id ||
                  suiteProposal.status !== "proposed"
                }
                className="px-3 py-1.5 rounded border border-ink dark:border-bright text-sm font-mono hover:bg-ink/5 dark:hover:bg-bright/10 disabled:opacity-50"
              >
                Reject proposal
              </button>
            </div>
            {suiteApprove && (
              <div
                className="font-mono text-[13px] space-y-1 border-t border-ink/10 dark:border-bright/10 pt-2"
                data-testid="antiek-bench-suite-approve-result"
              >
                <Row label="Gate ok" value={String(suiteApprove.ok)} />
                <Row
                  label="Gate status"
                  value={suiteApprove.status ?? "—"}
                />
                <Row
                  label="Promoted"
                  value={String(suiteApprove.promoted)}
                />
                <Row
                  label="Active after"
                  value={suiteApprove.active_suite_version ?? "—"}
                />
                {suiteApprove.notes?.map((n) => (
                  <p
                    key={n}
                    className="text-[11px] text-ink-soft dark:text-starlight"
                  >
                    {n}
                  </p>
                ))}
              </div>
            )}
            {suiteProposal && (
              <div
                className="font-mono text-[13px] space-y-2"
                data-testid="antiek-bench-suite-proposal-summary"
              >
                <Row
                  label="Has proposal"
                  value={String(suiteProposal.has_proposal)}
                />
                <Row
                  label="Status"
                  value={suiteProposal.status ?? "(none)"}
                />
                <Row
                  label="Proposal id"
                  value={suiteProposal.proposal_id ?? "—"}
                />
                <Row
                  label="Base suite"
                  value={suiteProposal.base_suite_version ?? "—"}
                />
                <Row
                  label="Proposed suite"
                  value={suiteProposal.proposed_suite_version ?? "—"}
                />
                <Row
                  label="Active suite"
                  value={suiteProposal.active_suite_version ?? "—"}
                />
                <Row
                  label="Active unchanged"
                  value={String(suiteProposal.active_suite_unchanged)}
                />
                <Row
                  label="Auto-promoted"
                  value={String(suiteProposal.auto_promoted)}
                />
                <Row label="Events" value={String(suiteProposal.event_count)} />
                <Row label="View" value={suiteProposal.view_format} />
                {/* Residual (fg): proposed sub-benchmark / task item ids. */}
                {suiteProposal.added_item_ids?.length ? (
                  <div
                    className="space-y-1"
                    data-testid="antiek-bench-proposed-tasks"
                    data-task-count={String(suiteProposal.added_item_ids.length)}
                  >
                    <p className="text-[11px] font-mono text-ink-soft dark:text-starlight">
                      Proposed sub-benchmark tasks (
                      {suiteProposal.added_item_ids.length}) — not active until
                      Approve & promote
                    </p>
                    {/* Residual (hg): task-class breakdown of proposed items. */}
                    {(() => {
                      const byClass = groupProposedTasksByClass(
                        suiteProposal.added_item_ids,
                      );
                      const entries = Object.entries(byClass);
                      if (entries.length === 0) return null;
                      return (
                        <ul
                          className="space-y-0.5 text-[12px] font-mono"
                          data-testid="antiek-bench-proposed-task-classes"
                          data-class-count={String(entries.length)}
                        >
                          {entries.map(([tc, n]) => (
                            <li key={tc}>
                              <strong>{tc}</strong>: {n} proposed
                            </li>
                          ))}
                        </ul>
                      );
                    })()}
                    <ul className="list-disc pl-4 text-[12px] font-mono">
                      {suiteProposal.added_item_ids.map((id) => (
                        <li key={id} data-testid="antiek-bench-proposed-task-id">
                          {id}
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : suiteProposal.has_proposal ? (
                  <p
                    className="text-[11px] font-mono text-ink-soft dark:text-starlight"
                    data-testid="antiek-bench-proposed-tasks-empty"
                  >
                    Proposal has no added_item_ids yet (rewrite may be
                    rationale-only).
                  </p>
                ) : null}
                {/* Residual (pe/qa): rewrite rationale + primary feed driver. */}
                {suiteProposal.rationale ? (
                  <p
                    className="text-[11px] font-mono text-ink-soft dark:text-starlight border border-ink/10 rounded p-2 dark:border-bright/10"
                    data-testid="antiek-bench-suite-proposal-rationale"
                    data-proposal-id={suiteProposal.proposal_id ?? ""}
                    data-proposed-task-count={String(
                      (suiteProposal.added_item_ids || []).length,
                    )}
                    data-feed-source-count={String(
                      Object.keys(usage?.by_source || {}).length,
                    )}
                    data-primary-feed-source={primaryRewriteFeed?.source ?? ""}
                    data-primary-feed-count={String(
                      primaryRewriteFeed?.count ?? 0,
                    )}
                    data-propose-not-promote="true"
                    data-view-format="html"
                    role="status"
                  >
                    Rewrite rationale (proposed, not auto-promoted):{" "}
                    {suiteProposal.rationale}
                    {primaryRewriteFeed ? (
                      <>
                        {" "}
                        · primary feed {primaryRewriteFeed.source}=
                        {primaryRewriteFeed.count}
                      </>
                    ) : null}
                  </p>
                ) : null}
                {suiteProposal.notes?.map((n) => (
                  <p
                    key={n}
                    className="text-[11px] text-ink-soft dark:text-starlight"
                  >
                    {n}
                  </p>
                ))}
                {suiteProposal.html ? (
                  <div
                    className="prose border rounded p-2 text-sm max-h-48 overflow-auto"
                    data-testid="antiek-bench-suite-proposal-html"
                    dangerouslySetInnerHTML={{ __html: suiteProposal.html }}
                  />
                ) : null}
              </div>
            )}
          </div>
        </LemonCard>

        <LemonCard title="Budget" elevation="z1">
          <div className="p-4 space-y-3">
            {budgetError && (
              <p className="text-sm text-red-700 dark:text-red-300 font-mono">
                {budgetError}
              </p>
            )}
            {budget && (
              <>
                <div className="font-mono text-[13px] space-y-2">
                  <Row
                    label="Daily cap"
                    value={
                      budget.daily_cap_usd == null
                        ? "unset"
                        : `$${budget.daily_cap_usd.toFixed(2)}`
                    }
                  />
                  <Row
                    label="Spent today"
                    value={
                      budget.spent_status === "known" && budget.spent_usd != null
                        ? `$${budget.spent_usd.toFixed(4)}`
                        : "unknown (ledger not inventing $0)"
                    }
                  />
                  <Row
                    label="Remaining"
                    value={
                      budget.remaining_usd == null
                        ? "unknown"
                        : `$${budget.remaining_usd.toFixed(4)}`
                    }
                  />
                  {budget.cap_env && (
                    <Row label="Cap source" value={budget.cap_env} />
                  )}
                </div>
                <div
                  className="h-2 w-full rounded-full bg-ink/10 dark:bg-bright/10 overflow-hidden"
                  role="progressbar"
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-valuenow={spendPct ?? 0}
                  aria-label="Budget usage"
                >
                  {spendPct != null ? (
                    <div
                      className="h-full bg-ink dark:bg-bright transition-all"
                      style={{ width: `${spendPct}%` }}
                    />
                  ) : (
                    <div className="h-full w-full bg-dashed opacity-30" />
                  )}
                </div>
                {spendPct == null && (
                  <p className="text-[11px] text-ink-soft dark:text-starlight">
                    Usage bar empty when spend is unknown or cap is unset.
                  </p>
                )}
                {budget.notes.length > 0 && (
                  <ul className="text-[11px] text-ink-soft dark:text-starlight list-disc list-inside space-y-1">
                    {budget.notes.map((n) => (
                      <li key={n}>{n}</li>
                    ))}
                  </ul>
                )}
              </>
            )}
          </div>
        </LemonCard>

        <LemonCard title="Prompt cost projection" elevation="z1" colour="glacial">
          <div
            id="prompt-cost-projection"
            className="p-4 space-y-3"
            data-testid="prompt-cost-projection-panel"
          >
            <p className="text-sm text-ink dark:text-bright">
              Estimate how a proposed pro-tier prompt would hit today&apos;s
              remaining budget. Projection uses dispatch config rates —
              placeholder 0.0 rates yield an honest null, not a fake price.
            </p>
            <div className="grid grid-cols-2 gap-3 font-mono text-[13px]">
              <label className="flex flex-col gap-1">
                <span className="text-[11px] uppercase tracking-wider text-ink-soft dark:text-starlight">
                  Input chars
                </span>
                <input
                  type="number"
                  min={0}
                  value={inputChars}
                  onChange={(e) => setInputChars(Number(e.target.value) || 0)}
                  className="border border-ink/20 dark:border-bright/20 bg-transparent px-2 py-1 rounded"
                />
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-[11px] uppercase tracking-wider text-ink-soft dark:text-starlight">
                  Expected output tokens
                </span>
                <input
                  type="number"
                  min={0}
                  value={outTokens}
                  onChange={(e) => setOutTokens(Number(e.target.value) || 0)}
                  className="border border-ink/20 dark:border-bright/20 bg-transparent px-2 py-1 rounded"
                />
              </label>
            </div>
            <button
              type="button"
              onClick={onEstimate}
              disabled={estimating}
              className="px-3 py-1.5 rounded border border-ink dark:border-bright text-sm font-mono hover:bg-ink/5 dark:hover:bg-bright/10 disabled:opacity-50"
            >
              {estimating ? "Estimating…" : "Project cost"}
            </button>
            {estimateError && (
              <p className="text-sm text-red-700 dark:text-red-300 font-mono">
                {estimateError}
              </p>
            )}
            {estimate && (
              <div
                className="font-mono text-[13px] space-y-1"
                data-testid="prompt-cost-estimate-result"
                data-remaining-after-usd={
                  budget?.remaining_usd != null &&
                  estimate.estimated_usd_high != null
                    ? String(budget.remaining_usd - estimate.estimated_usd_high)
                    : ""
                }
              >
                <Row
                  label="Pricing known"
                  value={estimate.pricing_known ? "yes" : "no"}
                />
                <Row
                  label="Estimate low"
                  value={
                    estimate.estimated_usd_low == null
                      ? "—"
                      : `$${estimate.estimated_usd_low.toFixed(6)}`
                  }
                />
                <Row
                  label="Estimate high"
                  value={
                    estimate.estimated_usd_high == null
                      ? "—"
                      : `$${estimate.estimated_usd_high.toFixed(6)}`
                  }
                />
                <Row
                  label="Would exceed budget"
                  value={
                    estimate.would_exceed_budget == null
                      ? "unknown"
                      : estimate.would_exceed_budget
                        ? "yes"
                        : "no"
                  }
                />
                {/* Residual (wb/aej): remaining after high-band fire + goes-negative (parity aeb). */}
                <div
                  data-testid="prompt-cost-remaining-after"
                  data-remaining-after-usd={
                    budget?.remaining_usd != null &&
                    estimate.estimated_usd_high != null
                      ? String(
                          budget.remaining_usd - estimate.estimated_usd_high,
                        )
                      : ""
                  }
                  data-goes-negative={
                    budget?.remaining_usd != null &&
                    estimate.estimated_usd_high != null
                      ? String(
                          budget.remaining_usd - estimate.estimated_usd_high <
                            0,
                        )
                      : "unknown"
                  }
                  role="status"
                >
                  <Row
                    label="Remaining after prompt"
                    value={
                      budget?.remaining_usd != null &&
                      estimate.estimated_usd_high != null
                        ? `$${(budget.remaining_usd - estimate.estimated_usd_high).toFixed(6)}${
                            budget.remaining_usd - estimate.estimated_usd_high <
                            0
                              ? " · over remaining (soft foresight)"
                              : ""
                          }`
                        : "—"
                    }
                  />
                </div>
                {estimate.notes.map((n) => (
                  <p
                    key={n}
                    className="text-[11px] text-ink-soft dark:text-starlight"
                  >
                    {n}
                  </p>
                ))}
              </div>
            )}
          </div>
        </LemonCard>

        {/* Residual (wc): honest deferred map — never list shipped spine as "coming later". */}
        <LemonCard title="Deferred (honest)" elevation="z1">
          <div
            className="p-4 space-y-2 text-sm text-ink dark:text-bright"
            data-testid="settings-deferred-honest"
            data-view-format="html"
            role="status"
          >
            <p className="text-[11px] font-mono text-ink-soft dark:text-starlight">
              Offline product spine is live on this branch. Items below are
              truly deferred or operator dual-gate — never silent live.
            </p>
            <ul className="space-y-2 list-disc list-inside">
              <li data-deferred="l1-l4-live" data-testid="settings-deferred-l1-l4">
                Live L1–L4 injectors (arxiv/substack hydrate · twin seed · MO
                step) — dual-gate only · offline default ·{" "}
                <a
                  href="/docs/campaigns/2026-07-09-research-reading-spine/DUAL-GATE-L1-L4-OPERATOR-CHECKLIST.md"
                  data-testid="settings-deferred-l1-l4-checklist-link"
                  className="underline opacity-90 hover:opacity-100"
                >
                  checklist
                </a>
              </li>
              <li data-deferred="l5-payment" data-testid="settings-deferred-l5">
                L5 marketplace payment rails — manual receipt only today ·{" "}
                <a
                  href="/docs/campaigns/2026-07-09-research-reading-spine/DUAL-GATE-L1-L4-OPERATOR-CHECKLIST.md#l5-payment"
                  data-testid="settings-deferred-l5-checklist-link"
                  className="underline opacity-90 hover:opacity-100"
                >
                  L5 checklist
                </a>
                {" · "}
                {/* Residual (ahz): FUTURE-AGENT L5 digital book port brief. */}
                <a
                  href="/docs/campaigns/2026-07-09-research-reading-spine/FUTURE-AGENT-SPEC-l5-digital-book-seamless-port.md"
                  data-testid="settings-deferred-l5-future-agent-link"
                  className="underline opacity-90 hover:opacity-100"
                  title="Future-agent executable brief for L5 digital book seamless port"
                >
                  FUTURE-AGENT L5 port
                </a>
              </li>
              <li data-deferred="l6-collective" data-testid="settings-deferred-l6">
                L6 live multi-agent council — offline merge unit only today ·{" "}
                <a
                  href="/docs/campaigns/2026-07-09-research-reading-spine/DUAL-GATE-L1-L4-OPERATOR-CHECKLIST.md#l6-collective"
                  data-testid="settings-deferred-l6-checklist-link"
                  className="underline opacity-90 hover:opacity-100"
                >
                  L6 checklist
                </a>
                {" · "}
                {/* Residual (ahz): FUTURE-AGENT L6 live multi-agent brief. */}
                <a
                  href="/docs/campaigns/2026-07-09-research-reading-spine/FUTURE-AGENT-SPEC-l6-live-multiagent-collective.md"
                  data-testid="settings-deferred-l6-future-agent-link"
                  className="underline opacity-90 hover:opacity-100"
                  title="Future-agent executable brief for L6 live multi-agent collective"
                >
                  FUTURE-AGENT L6 council
                </a>
              </li>
              <li data-deferred="l7-nd" data-testid="settings-deferred-l7">
                L7 NotDiamond as router — never · advisory only (correct) ·{" "}
                <a
                  href="/docs/campaigns/2026-07-09-research-reading-spine/DUAL-GATE-L1-L4-OPERATOR-CHECKLIST.md#l7-notdiamond"
                  data-testid="settings-deferred-l7-checklist-link"
                  className="underline opacity-90 hover:opacity-100"
                >
                  L7 checklist
                </a>{" "}
                ·{" "}
                {/* Residual (wo): in-app ND advisory panel (never-router honesty). */}
                <a
                  href="#notdiamond-advisory"
                  data-testid="settings-deferred-l7-panel-link"
                  className="underline opacity-90 hover:opacity-100"
                  title="NotDiamond advisory panel — never dispatch authority"
                >
                  ND advisory panel
                </a>
              </li>
              {/* Residual (aia): twin note-taker completeness FUTURE brief (ahq). */}
              <li
                data-deferred="twin-completeness"
                data-testid="settings-deferred-twin-completeness"
              >
                L3 twin live seed deferred · offline twin mounts shipped ·{" "}
                <a
                  href="/docs/campaigns/2026-07-09-research-reading-spine/FUTURE-AGENT-SPEC-twin-note-taker-completeness-matrix.md"
                  data-testid="settings-deferred-twin-future-agent-link"
                  className="underline opacity-90 hover:opacity-100"
                  title="Future-agent twin note-taker completeness matrix"
                >
                  FUTURE-AGENT twin matrix
                </a>
              </li>
              <li data-deferred="secret-vault" data-testid="settings-deferred-vault">
                Multi-provider secret vault polish (SPR-02) beyond register model
              </li>
              <li data-deferred="keyboard-map" data-testid="settings-deferred-keyboard">
                Keyboard map customisation + layout export
              </li>
            </ul>
            <p
              className="text-[11px] font-mono text-ink-soft dark:text-starlight"
              data-testid="settings-deferred-shipped-spine"
            >
              Shipped offline spine (not a backlog item): Midnight Oil
              create→approve→run·deposit · Antiek-bench propose/approve + dogfood ·
              free PD marketplace host · launch remaining-after budget.
            </p>
          </div>
        </LemonCard>
      </div>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="text-ink-soft dark:text-starlight uppercase tracking-wider text-[11px]">
        {label}
      </span>
      <span className="text-ink dark:text-bright">{value}</span>
    </div>
  );
}
