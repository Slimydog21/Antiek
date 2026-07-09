import { useEffect, useMemo, useState } from "react";
import { useViewportTier } from "../../workspace/useViewportTier";
import LemonCard from "../../components/lemon/LemonCard";
import {
  applyDepthTier,
  approveAntiekBenchSuiteProposal,
  clearDecisionTreeSelection,
  estimatePromptCost,
  fetchAntiekBenchSuiteProposal,
  fetchAntiekBenchUsageSummary,
  fetchDecisionTreeSelection,
  fetchDepthTiers,
  fetchNotDiamondAdvisory,
  fetchSettingsBudget,
  fetchSettingsModels,
  installDecisionTreeSelection,
  type AntiekBenchSuiteApproveResponse,
  type AntiekBenchSuiteProposalResponse,
  type AntiekBenchUsageSummaryResponse,
  type BudgetResponse,
  type DecisionTreeSelectionResponse,
  type DepthTierResponse,
  type ModelRow,
  type NotDiamondAdvisoryResponse,
  type PromptCostEstimateResponse,
} from "../../api/settings";

/**
 * Operator Settings — model inventory + budget + prompt projection (SPR-01)
 * + decision-tree driver install (process-local registry)
 * + Antiek-bench weekly usage summary (recorded engagement outcomes)
 * + Antiek-bench suite rewrite proposal (proposed only; not auto-promoted).
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
        const n = await fetchNotDiamondAdvisory({ includeHtml: true });
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
    })();
    return () => {
      cancelled = true;
    };
  }, []);

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
      if (hints?.input_chars != null) setInputChars(hints.input_chars);
      if (hints?.expected_output_tokens != null)
        setOutTokens(hints.expected_output_tokens);
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

  async function onEstimate() {
    setEstimating(true);
    setEstimateError(null);
    try {
      const res = await estimatePromptCost({
        tier: "pro",
        provider: selectedProvider || null,
        model: selectedModel || null,
        input_chars: inputChars,
        expected_output_tokens: outTokens,
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
                <Row label="View" value={nd.view_format} />
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
