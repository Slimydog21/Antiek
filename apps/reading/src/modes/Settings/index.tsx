import { useEffect, useMemo, useState } from "react";
import { useViewportTier } from "../../workspace/useViewportTier";
import LemonCard from "../../components/lemon/LemonCard";
import {
  estimatePromptCost,
  fetchSettingsBudget,
  fetchSettingsModels,
  type BudgetResponse,
  type ModelRow,
  type PromptCostEstimateResponse,
} from "../../api/settings";

/**
 * Operator Settings — model inventory + budget + prompt projection (SPR-01).
 *
 * Honesty: spent/pricing may be unknown; UI never invents $0.00 when the
 * ledger or rate table is unset. Full "add model" + decision-tree override
 * land in later sprints.
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
  const [decision, setDecision] = useState<DecisionTreeState>({
    task: "source-heavy",
    priority: "quality",
    budget: "known",
  });

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

  async function onEstimate() {
    setEstimating(true);
    setEstimateError(null);
    try {
      const res = await estimatePromptCost({
        tier: "pro",
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
              Adding API keys / new models lands in SPR-02. Decision-tree
              recommendations stay in the closed Fast/Deep set below.
            </p>
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

        <LemonCard title="Decision tree" elevation="z1">
          <DecisionTreePanel
            value={decision}
            onChange={setDecision}
            budget={budget}
          />
        </LemonCard>

        <LemonCard title="Coming later" elevation="z1">
          <ul className="p-4 space-y-2 text-sm text-ink dark:text-bright list-disc list-inside">
            <li>Add model + multi-provider secret vault (SPR-02)</li>
            <li>Persist decision-tree choice into new research defaults</li>
            <li>Antiek-bench weekly model quality report</li>
            <li>Midnight oil: time + goals + price-ceiling approve UI</li>
            <li>Keyboard map customisation + layout export</li>
          </ul>
        </LemonCard>
      </div>
    </div>
  );
}

type DecisionTask = "quick" | "source-heavy" | "synthesis";
type DecisionPriority = "cost" | "balanced" | "quality";
type DecisionBudget = "known" | "tight" | "unknown";

interface DecisionTreeState {
  task: DecisionTask;
  priority: DecisionPriority;
  budget: DecisionBudget;
}

function DecisionTreePanel({
  value,
  onChange,
  budget,
}: {
  value: DecisionTreeState;
  onChange: (next: DecisionTreeState) => void;
  budget: BudgetResponse | null;
}) {
  const recommendation = recommendDecision(value, budget);
  return (
    <div className="p-4 space-y-4">
      <div className="grid gap-4 md:grid-cols-3">
        <OptionGroup
          label="Task"
          value={value.task}
          options={[
            ["quick", "Quick scan"],
            ["source-heavy", "Source chase"],
            ["synthesis", "Deep synthesis"],
          ]}
          onChange={(task) => onChange({ ...value, task })}
        />
        <OptionGroup
          label="Priority"
          value={value.priority}
          options={[
            ["cost", "Cheapest"],
            ["balanced", "Balanced"],
            ["quality", "Quality"],
          ]}
          onChange={(priority) => onChange({ ...value, priority })}
        />
        <OptionGroup
          label="Budget"
          value={value.budget}
          options={[
            ["known", "Known"],
            ["tight", "Tight"],
            ["unknown", "Unknown"],
          ]}
          onChange={(nextBudget) => onChange({ ...value, budget: nextBudget })}
        />
      </div>
      <div
        className="border border-ink/10 dark:border-bright/10 rounded p-3 font-mono text-[13px] space-y-2"
        aria-live="polite"
      >
        <Row label="Recommended depth" value={recommendation.tierLabel} />
        <Row label="Route posture" value={recommendation.routePosture} />
        <p className="text-[11px] text-ink-soft dark:text-starlight">
          {recommendation.reason}
        </p>
        <p className="text-[11px] text-ink-soft dark:text-starlight">
          Apply this explicitly in the Research home depth selector. Settings
          does not mutate provider registration, store secrets, or silently
          reroute existing prompts.
        </p>
      </div>
    </div>
  );
}

function OptionGroup<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: [T, string][];
  onChange: (value: T) => void;
}) {
  return (
    <div className="space-y-2">
      <p className="text-[11px] uppercase tracking-wider text-ink-soft dark:text-starlight font-mono">
        {label}
      </p>
      <div className="inline-flex max-w-full flex-wrap rounded border border-ink/20 dark:border-bright/20 overflow-hidden">
        {options.map(([optionValue, optionLabel]) => {
          const active = optionValue === value;
          return (
            <button
              key={optionValue}
              type="button"
              aria-pressed={active}
              onClick={() => onChange(optionValue)}
              className={
                "px-2.5 py-1.5 text-[12px] font-mono border-r last:border-r-0 border-ink/10 dark:border-bright/10 " +
                (active
                  ? "bg-ink text-ice-0 dark:bg-bright dark:text-space-2"
                  : "bg-transparent text-ink dark:text-bright hover:bg-ink/5 dark:hover:bg-bright/10")
              }
            >
              {optionLabel}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function recommendDecision(
  value: DecisionTreeState,
  budget: BudgetResponse | null,
): { tierLabel: string; routePosture: string; reason: string } {
  const remaining = budget?.remaining_usd ?? null;
  const budgetLooksTight =
    value.budget === "tight" ||
    (budget?.spent_status === "known" && remaining != null && remaining < 1);

  if (value.task === "quick" || value.priority === "cost" || budgetLooksTight) {
    return {
      tierLabel: "Fast",
      routePosture: "minimise latency and spend",
      reason:
        "Use Fast when the prompt needs a quick scan, budget is tight, or you want the cheapest acceptable answer.",
    };
  }
  if (value.task === "synthesis" || value.priority === "quality") {
    return {
      tierLabel: "Deep",
      routePosture: "maximise synthesis quality",
      reason:
        "Use Deep when the prompt needs cross-source reasoning, careful synthesis, or a defensible answer over lowest cost.",
    };
  }
  return {
    tierLabel: "Deep",
    routePosture: "balanced default",
    reason:
      "Balanced source-chasing defaults to Deep because missing evidence is more expensive than a slower first pass.",
  };
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
