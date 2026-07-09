import { useEffect, useMemo, useState } from "react";
import { useViewportTier } from "../../workspace/useViewportTier";
import LemonCard from "../../components/lemon/LemonCard";
import {
  estimateNotDiamondAdvisor,
  estimatePromptCost,
  fetchLatestAntiekBench,
  fetchSettingsBudget,
  fetchSettingsModels,
  type AntiekBenchLatestResponse,
  type BudgetResponse,
  type ModelRow,
  type NotDiamondAdvisorResponse,
  type PromptCostEstimateRequest,
  type PromptCostEstimateResponse,
} from "../../api/settings";

/**
 * Operator Settings — model inventory + budget + prompt projection.
 *
 * Honesty: spent/pricing may be unknown; UI never invents $0.00 when the
 * ledger or rate table is unset.
 */
type TaskKind = NonNullable<PromptCostEstimateRequest["task_kind"]>;
type RouteMode = NonNullable<PromptCostEstimateRequest["route_mode"]>;

const TASK_KINDS: Array<{ value: TaskKind; label: string }> = [
  { value: "research_question", label: "Research question" },
  { value: "reading_highlight", label: "Reading highlight" },
  { value: "midnight_oil", label: "Midnight oil" },
  { value: "synthesis", label: "Synthesis" },
  { value: "verification", label: "Verification" },
];

const ROUTE_MODES: Array<{ value: RouteMode; label: string }> = [
  { value: "auto_balanced", label: "Balanced" },
  { value: "auto_quality", label: "Quality" },
  { value: "auto_cost", label: "Cost" },
  { value: "auto_latency", label: "Latency" },
  { value: "manual", label: "Manual" },
];

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
  const [bench, setBench] = useState<AntiekBenchLatestResponse | null>(null);
  const [benchError, setBenchError] = useState<string | null>(null);
  const [promptText, setPromptText] = useState("");
  const [outTokens, setOutTokens] = useState(500);
  const [taskKind, setTaskKind] = useState<TaskKind>("research_question");
  const [routeMode, setRouteMode] = useState<RouteMode>("auto_balanced");
  const [manualRoute, setManualRoute] = useState("");
  const [sessionCacheKey, setSessionCacheKey] = useState("");
  const [estimate, setEstimate] = useState<PromptCostEstimateResponse | null>(
    null,
  );
  const [estimateError, setEstimateError] = useState<string | null>(null);
  const [estimating, setEstimating] = useState(false);
  const [advisor, setAdvisor] = useState<NotDiamondAdvisorResponse | null>(null);
  const [advisorError, setAdvisorError] = useState<string | null>(null);
  const [advising, setAdvising] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const m = await fetchSettingsModels();
        if (!cancelled) setModels(m.models);
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
        const latestBench = await fetchLatestAntiekBench();
        if (!cancelled) setBench(latestBench);
      } catch (e) {
        if (!cancelled)
          setBenchError(e instanceof Error ? e.message : String(e));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

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

  const modelOptions = useMemo(() => {
    return (models ?? [])
      .filter((m) => m.primary_model)
      .map((m) => ({
        value: `${m.provider_id}::${m.primary_model}`,
        label: `${m.provider_id} / ${m.primary_model}`,
        provider: m.provider_id,
        model: m.primary_model as string,
      }));
  }, [models]);

  const promptChars = promptText.length;
  const effectiveManualRoute =
    manualRoute || (modelOptions.length > 0 ? modelOptions[0].value : "");
  const [manualProvider, manualModel] = effectiveManualRoute.split("::");
  const selectedLabel = estimate?.selected_candidate
    ? `${estimate.selected_candidate.provider} / ${estimate.selected_candidate.model} (${estimate.selected_candidate.tier})`
    : "not projected";
  const budgetStatus =
    budget?.daily_cap_usd == null
      ? "no cap configured"
      : budget.spent_status !== "known"
        ? "spend unknown"
        : budget.remaining_usd != null && budget.remaining_usd < 0
          ? "cap exceeded"
          : "within cap";

  function promptEstimateRequest(): PromptCostEstimateRequest {
    return {
      task_kind: taskKind,
      role:
        taskKind === "verification"
          ? "verifier"
          : taskKind === "research_question" || taskKind === "synthesis"
            ? "synthesizer"
            : "decomposer",
      route_mode: routeMode,
      manual_provider: routeMode === "manual" ? manualProvider || null : null,
      manual_model: routeMode === "manual" ? manualModel || null : null,
      session_cache_key: sessionCacheKey.trim() || null,
      tier: "pro",
      prompt_chars: promptChars,
      input_chars: promptChars,
      expected_output_tokens: outTokens,
    };
  }

  async function onEstimate() {
    setEstimating(true);
    setEstimateError(null);
    try {
      const res = await estimatePromptCost(promptEstimateRequest());
      setEstimate(res);
    } catch (e) {
      setEstimateError(e instanceof Error ? e.message : String(e));
    } finally {
      setEstimating(false);
    }
  }

  async function onAdvisor() {
    setAdvising(true);
    setAdvisorError(null);
    try {
      const res = await estimateNotDiamondAdvisor(promptEstimateRequest());
      setAdvisor(res);
      setEstimate(res.estimate);
    } catch (e) {
      setAdvisorError(e instanceof Error ? e.message : String(e));
    } finally {
      setAdvising(false);
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
                  aria-label={`Budget usage: ${budgetStatus}`}
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
                <p
                  className="text-[11px] text-ink-soft dark:text-starlight"
                  aria-live="polite"
                >
                  Budget status: {budgetStatus}.
                </p>
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

        <LemonCard title="Antiek-bench" elevation="z1">
          <div className="p-4 space-y-3">
            {benchError && (
              <p className="text-sm text-red-700 dark:text-red-300 font-mono">
                {benchError}
              </p>
            )}
            {bench === null && !benchError && (
              <p className="text-sm text-ink-soft dark:text-starlight">
                Loading scorecard…
              </p>
            )}
            {bench && !bench.available && (
              <div className="space-y-2">
                <p className="text-sm text-ink-soft dark:text-starlight">
                  No Antiek-bench scorecard available yet.
                </p>
                {bench.notes.map((note) => (
                  <p
                    key={note}
                    className="text-[11px] text-ink-soft dark:text-starlight"
                  >
                    {note}
                  </p>
                ))}
              </div>
            )}
            {bench && bench.available && (
              <div className="space-y-3 font-mono text-[13px]">
                <Row label="Week" value={bench.week_id ?? "unknown"} />
                <Row
                  label="Run"
                  value={bench.mock_run ? "mock scorecard" : "ratified scorecard"}
                />
                <ul className="space-y-2" aria-label="Best model by task class">
                  {bench.best_by_task_class.map((row) => (
                    <li
                      key={row.task_class}
                      className="border-t border-ink/10 dark:border-bright/10 pt-2"
                    >
                      <div className="flex flex-wrap justify-between gap-2">
                        <span className="font-semibold text-ink dark:text-bright">
                          {row.task_class}
                        </span>
                        <span>
                          {row.provider} / {row.model}
                        </span>
                      </div>
                      <div className="mt-1 grid grid-cols-1 sm:grid-cols-3 gap-1 text-[11px] text-ink-soft dark:text-starlight">
                        <span>quality {row.quality_score.toFixed(2)}</span>
                        <span>
                          cost{" "}
                          {row.cost_per_acceptable_answer == null
                            ? "unknown"
                            : `$${row.cost_per_acceptable_answer.toFixed(6)}`}
                        </span>
                        <span>
                          latency{" "}
                          {row.latency_ms == null ? "unknown" : `${row.latency_ms} ms`}
                        </span>
                      </div>
                    </li>
                  ))}
                </ul>
                {bench.notes.map((note) => (
                  <p
                    key={note}
                    className="text-[11px] text-ink-soft dark:text-starlight"
                  >
                    {note}
                  </p>
                ))}
              </div>
            )}
          </div>
        </LemonCard>

        <LemonCard title="Prompt cost projection" elevation="z1" colour="glacial">
          <div className="p-4 space-y-3">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 font-mono text-[13px]">
              <label className="flex flex-col gap-1">
                <span className="text-[11px] uppercase tracking-wider text-ink-soft dark:text-starlight">
                  Task kind
                </span>
                <select
                  value={taskKind}
                  onChange={(e) => setTaskKind(e.target.value as TaskKind)}
                  className="border border-ink/20 dark:border-bright/20 bg-transparent px-2 py-1 rounded"
                >
                  {TASK_KINDS.map((item) => (
                    <option key={item.value} value={item.value}>
                      {item.label}
                    </option>
                  ))}
                </select>
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
            <label className="flex flex-col gap-1 font-mono text-[13px]">
              <span className="text-[11px] uppercase tracking-wider text-ink-soft dark:text-starlight">
                Prompt
              </span>
              <textarea
                value={promptText}
                onChange={(e) => setPromptText(e.target.value)}
                rows={5}
                className="border border-ink/20 dark:border-bright/20 bg-transparent px-2 py-1 rounded resize-y min-h-28"
                placeholder="Paste the prompt or question to project."
              />
              <span className="text-[11px] text-ink-soft dark:text-starlight">
                {promptChars} characters
              </span>
            </label>
            <fieldset className="space-y-2">
              <legend className="text-[11px] uppercase tracking-wider text-ink-soft dark:text-starlight font-mono">
                Route mode
              </legend>
              <div className="grid grid-cols-2 sm:grid-cols-5 gap-2" role="radiogroup">
                {ROUTE_MODES.map((item) => (
                  <button
                    key={item.value}
                    type="button"
                    role="radio"
                    aria-checked={routeMode === item.value}
                    onClick={() => setRouteMode(item.value)}
                    className={
                      "min-h-9 rounded border px-2 py-1 text-xs font-mono " +
                      (routeMode === item.value
                        ? "border-ink bg-ink text-white dark:border-bright dark:bg-bright dark:text-space"
                        : "border-ink/20 dark:border-bright/20 text-ink dark:text-bright")
                    }
                  >
                    {item.label}
                  </button>
                ))}
              </div>
            </fieldset>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3 font-mono text-[13px]">
              <label className="flex flex-col gap-1">
                <span className="text-[11px] uppercase tracking-wider text-ink-soft dark:text-starlight">
                  Manual model
                </span>
                <select
                  value={effectiveManualRoute}
                  disabled={routeMode !== "manual" || modelOptions.length === 0}
                  onChange={(e) => setManualRoute(e.target.value)}
                  className="border border-ink/20 dark:border-bright/20 bg-transparent px-2 py-1 rounded disabled:opacity-50"
                  aria-label="Manual provider and model override"
                >
                  {modelOptions.length === 0 ? (
                    <option value="">No configured model</option>
                  ) : (
                    modelOptions.map((item) => (
                      <option key={item.value} value={item.value}>
                        {item.label}
                      </option>
                    ))
                  )}
                </select>
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-[11px] uppercase tracking-wider text-ink-soft dark:text-starlight">
                  Cache key
                </span>
                <input
                  type="text"
                  value={sessionCacheKey}
                  onChange={(e) => setSessionCacheKey(e.target.value)}
                  className="border border-ink/20 dark:border-bright/20 bg-transparent px-2 py-1 rounded"
                />
              </label>
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={onEstimate}
                disabled={estimating}
                className="px-3 py-1.5 rounded border border-ink dark:border-bright text-sm font-mono hover:bg-ink/5 dark:hover:bg-bright/10 disabled:opacity-50"
              >
                {estimating ? "Estimating…" : "Project cost"}
              </button>
              <button
                type="button"
                onClick={onAdvisor}
                disabled={advising}
                className="px-3 py-1.5 rounded border border-ink/30 dark:border-bright/30 text-sm font-mono hover:bg-ink/5 dark:hover:bg-bright/10 disabled:opacity-50"
              >
                {advising ? "Checking…" : "Check NotDiamond"}
              </button>
            </div>
            {estimateError && (
              <p className="text-sm text-red-700 dark:text-red-300 font-mono">
                {estimateError}
              </p>
            )}
            {advisorError && (
              <p className="text-sm text-red-700 dark:text-red-300 font-mono">
                {advisorError}
              </p>
            )}
            {estimate && (
              <div
                className="font-mono text-[13px] space-y-1"
                aria-live="polite"
                aria-label={`Selected route: ${selectedLabel}`}
              >
                <Row
                  label={routeMode === "manual" ? "Manual override" : "Selected route"}
                  value={selectedLabel}
                />
                {estimate.selected_candidate && routeMode !== "manual" && (
                  <Row
                    label="Recommendation"
                    value={estimate.selected_candidate.selection_reason}
                  />
                )}
                {estimate.selected_candidate && (
                  <Row
                    label="Cache"
                    value={estimate.selected_candidate.cache_status}
                  />
                )}
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
                {estimate.candidates.length > 0 && (
                  <div className="pt-2">
                    <p className="text-[11px] uppercase tracking-wider text-ink-soft dark:text-starlight">
                      Candidates
                    </p>
                    <ul className="mt-1 space-y-1">
                      {estimate.candidates.map((candidate) => (
                        <li
                          key={`${candidate.provider}-${candidate.model}-${candidate.fallback_chain_index}`}
                          className="flex flex-wrap justify-between gap-2 border-t border-ink/10 dark:border-bright/10 pt-1"
                        >
                          <span>
                            {candidate.provider} / {candidate.model}
                          </span>
                          <span>
                            {candidate.estimated_usd_high == null
                              ? "unknown"
                              : `$${candidate.estimated_usd_high.toFixed(6)}`}
                          </span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
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
            {advisor && (
              <div
                className="font-mono text-[13px] space-y-1 border-t border-ink/10 dark:border-bright/10 pt-3"
                aria-live="polite"
                aria-label={`NotDiamond advisor: ${advisor.recommendation.provider ?? "none"} / ${
                  advisor.recommendation.model ?? "none"
                }`}
              >
                <Row label="Advisor mode" value={advisor.recommendation.mode} />
                <Row label="Advisor source" value={advisor.recommendation.source} />
                <Row
                  label="Advisor route"
                  value={
                    advisor.recommendation.provider && advisor.recommendation.model
                      ? `${advisor.recommendation.provider} / ${advisor.recommendation.model}`
                      : "none"
                  }
                />
                <Row
                  label="External call"
                  value={advisor.recommendation.external_call_performed ? "yes" : "no"}
                />
                <Row
                  label="Would call"
                  value={advisor.recommendation.notdiamond_would_call ? "yes" : "no"}
                />
                <Row
                  label="Promotion eligible"
                  value={advisor.recommendation.promotion_gate.eligible ? "yes" : "no"}
                />
                <p className="text-[11px] text-ink-soft dark:text-starlight">
                  {advisor.recommendation.reason}
                </p>
                {advisor.recommendation.cache_caveat && (
                  <p className="text-[11px] text-ink-soft dark:text-starlight">
                    {advisor.recommendation.cache_caveat}
                  </p>
                )}
                <p className="text-[11px] text-ink-soft dark:text-starlight">
                  {advisor.recommendation.promotion_gate.reason}
                </p>
                {advisor.recommendation.notes.map((n) => (
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
