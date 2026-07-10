import { useEffect, useMemo, useState } from "react";
import {
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
  /** Residual (ru): known feed sources that are Write twin_seed paths. */
  const writeSeedKnownCount = useMemo(
    () => countWriteSeedKnownSources(usage?.known_sources),
    [usage?.known_sources],
  );

  /** Residual (rl): advisory suggestion vs installed driver (never auto-route). */
  const ndDriverDelta = useMemo(
    () =>
      notDiamondDriverDelta({
        suggestedModelId: nd?.suggested_model_id,
        installedModelId: tree?.model_id,
      }),
    [nd?.suggested_model_id, tree?.model_id],
  );

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
    } catch (e) {
      setNdError(e instanceof Error ? e.message : String(e));
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
          "Select a provider (or ensure models inventory has one) before installing recommended driver",
        );
      }
      const mid = leaderboard.recommended_model_id;
      const result = await installDecisionTreeSelection({
        model_id: mid,
        provider_id: provider,
      });
      setTree(result);
      setSelectedModel(mid);
      setSelectedProvider(provider);
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
          <div className="p-4 space-y-3" data-testid="decision-tree-panel">
            <p className="text-sm text-ink dark:text-bright">
              Select the model driver for this process. Install writes the
              choice into the decision-tree registry so research dispatch can
              apply provider+model overrides. Cost projection still uses the
              #440 settings estimate API (never invents $0).
            </p>
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
            <div className="font-mono text-[13px] space-y-1" data-testid="decision-tree-status">
              <Row
                label="Installed"
                value={
                  tree?.installed
                    ? `${tree.provider_id ?? "?"} / ${tree.model_id ?? "?"}`
                    : "none"
                }
              />
              {tree?.notes?.map((n) => (
                <p
                  key={n}
                  className="text-[11px] text-ink-soft dark:text-starlight"
                >
                  {n}
                </p>
              ))}
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
          >
            <p className="text-sm text-ink dark:text-bright">
              Recursive note-taker UI always force_offline seeds. Live
              note_taker requires dual env gate + boot install — never silent
              LLM from this panel.
            </p>
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
                {twinSeedLive.notes.map((n) => (
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
            data-testid="hydrate-live-status-panel"
            data-view-format="html"
            data-offline-honest={
              hydrateLive ? String(hydrateLive.offline_honest) : undefined
            }
            data-any-live-injector={
              hydrateLive ? String(hydrateLive.any_live_injector) : undefined
            }
          >
            <p className="text-sm text-ink dark:text-bright">
              Knowledge-dense refs hydrate offline-honest by default (identity
              only). Live arXiv/Substack injectors are env-gated process
              installs — never silent network from this UI.
            </p>
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
          >
            <p className="text-sm text-ink dark:text-bright">
              Campaign verdict: advisory GO (measured wedge only); authoritative
              dispatch REJECT under §16. NotDiamond is never the dispatch owner
              — decision-tree + Hermes remain primary.
            </p>
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
                {(leaderboard.models || []).length === 0 ? (
                  <p className="text-[11px] text-ink-soft dark:text-starlight">
                    No offline runs for this week yet.
                  </p>
                ) : (
                  <ul data-testid="antiek-bench-leaderboard-models" className="space-y-1">
                    {leaderboard.models.map((m) => (
                      <li key={m.model_id}>
                        <strong>{m.model_id}</strong>: mean=
                        {m.mean_score ?? "—"}
                      </li>
                    ))}
                  </ul>
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
            className="p-4 space-y-3"
            data-testid="antiek-bench-dogfood-panel"
            data-view-format="html"
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
              >
                <Row label="Suite" value={dogfood.suite_version} />
                <Row label="Label" value={dogfood.label} />
                <Row label="Items" value={String(dogfood.item_count)} />
                <Row
                  label="Auto-promoted"
                  value={String(dogfood.auto_promoted)}
                />
                <Row label="View" value={dogfood.view_format} />
                <ul data-testid="antiek-bench-dogfood-classes" className="space-y-1">
                  {Object.entries(dogfood.by_task_class || {}).map(
                    ([tc, n]) => (
                      <li key={tc}>
                        <strong>{tc}</strong>: {n}
                      </li>
                    ),
                  )}
                </ul>
                <ul data-testid="antiek-bench-dogfood-items" className="space-y-1 text-[11px]">
                  {(dogfood.items || []).slice(0, 8).map((it) => (
                    <li key={it.item_id}>
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
                      Object.keys(usage.by_source || {}).filter((s) =>
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
            {/* Residual (nt): dual-gate prep + L7 NotDiamond never-router reminder. */}
            <p className="text-[11px] font-mono space-x-3">
              <a
                href="/docs/campaigns/2026-07-09-research-reading-spine/DUAL-GATE-L1-L4-OPERATOR-CHECKLIST.md"
                data-testid="antiek-bench-dual-gate-checklist-link"
                className="underline opacity-80 hover:opacity-100"
                title="Dual-gate L1–L4 checklist (prep only; L7 NotDiamond never router)"
              >
                Dual-gate L1–L4 checklist
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
                data-propose-not-promote="true"
                data-view-format="html"
                role="status"
              >
                Recursive rewrite · events={suiteProposal.event_count ?? 0} ·
                proposed_tasks=
                {(suiteProposal.added_item_ids || []).length} · status=
                {suiteProposal.status ?? "—"} · feed_sources=
                {Object.keys(usage?.by_source || {}).length}
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
          <div className="p-4 space-y-3">
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
              <div className="font-mono text-[13px] space-y-1">
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

        <LemonCard title="Coming later" elevation="z1">
          <ul className="p-4 space-y-2 text-sm text-ink dark:text-bright list-disc list-inside">
            <li>Add model + multi-provider secret vault (SPR-02)</li>
            <li>Antiek-bench weekly model quality report (UI polish)</li>
            <li>Midnight oil: time + goals + price-ceiling approve UI</li>
            <li>Keyboard map customisation + layout export</li>
          </ul>
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
