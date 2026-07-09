import { useEffect, useMemo, useState } from "react";
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

/**
 * Operator Settings — model inventory + budget + prompt projection (SPR-01)
 * + decision-tree driver install (process-local registry)
 * + Antiek-bench weekly usage summary (recorded engagement outcomes)
 * + Antiek-bench suite rewrite proposal (proposed only; not auto-promoted)
 * + competitive dogfood fixtures listing (never auto-promoted)
 * + offline dogfood suite run → populate weekly leaderboard (residual bo).
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
    } catch (e) {
      setOfflineRunError(e instanceof Error ? e.message : String(e));
    } finally {
      setOfflineRunBusy(false);
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

        <LemonCard title="NotDiamond advisory" elevation="z1" colour="glacial">
          <div
            className="p-4 space-y-3"
            data-testid="notdiamond-advisory-panel"
            data-view-format="html"
          >
            <p className="text-sm text-ink dark:text-bright">
              Campaign verdict: advisory GO (measured wedge only); authoritative
              dispatch REJECT under §16. NotDiamond is never the dispatch owner
              — decision-tree + Hermes remain primary.
            </p>
            {ndError && (
              <p className="text-sm text-red-700 dark:text-red-300 font-mono">
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
                <Row label="View" value={nd.view_format} />
                {nd.suggested_model_id && nd.installable !== false ? (
                  <button
                    type="button"
                    data-testid="notdiamond-install-advisory"
                    disabled={treeBusy || nd.notdiamond_is_dispatch_authority}
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
          >
            <p className="text-sm text-ink dark:text-bright">
              Recursive suite rewrite proposal derived from recorded usage
              events. Status is always <strong>proposed</strong> here —
              operator must explicitly approve/promote (not auto-active).
            </p>
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
                {suiteProposal.rationale ? (
                  <p
                    className="text-[11px] text-ink-soft dark:text-starlight"
                    data-testid="antiek-bench-suite-proposal-rationale"
                  >
                    {suiteProposal.rationale}
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
