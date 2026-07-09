/**
 * ResearchLaunchBudgetPanel — budget bar + prompt cost projection at launch.
 *
 * Residual (bp): operators see daily spend vs cap and how the *current* prompt
 * would affect remaining budget before Ask. Reuses Settings #440 estimate +
 * decision-tree read surfaces — never invents $0 when unknown.
 *
 * Research tier maps to dispatch tier for projection only:
 *   fast → flash · deep → pro
 * Decision-tree driver is advisory display (Hermes still owns dispatch).
 */

import { useCallback, useEffect, useMemo, useState } from "react";

import {
  estimatePromptCost,
  fetchDecisionTreeSelection,
  fetchSettingsBudget,
  type BudgetResponse,
  type DecisionTreeSelectionResponse,
  type PromptCostEstimateResponse,
} from "../../api/settings";

export type ResearchLaunchBudgetProjection = {
  wouldExceedBudget: boolean | null;
  pricingKnown: boolean;
  estimatedUsdHigh: number | null;
  remainingUsd: number | null;
  modelId: string | null;
};

export type ResearchLaunchBudgetPanelProps = {
  /** Live composer text used for input_chars projection. */
  promptText: string;
  /** Curated research entry tier (not a raw model id). */
  researchTier: "fast" | "deep";
  /** Debounce ms for estimate calls (default 350). */
  debounceMs?: number;
  /**
   * Residual (de): notify parent when projection updates so launch surfaces
   * can soft-warn / disable before fire without re-fetching Settings.
   */
  onProjectionChange?: (projection: ResearchLaunchBudgetProjection) => void;
};

function dispatchTierFor(researchTier: "fast" | "deep"): {
  tier: string;
  expected_output_tokens: number;
} {
  if (researchTier === "fast") {
    return { tier: "flash", expected_output_tokens: 800 };
  }
  return { tier: "pro", expected_output_tokens: 2500 };
}

function formatUsd(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return "—";
  if (n < 0.01 && n > 0) return `$${n.toFixed(4)}`;
  return `$${n.toFixed(2)}`;
}

export function ResearchLaunchBudgetPanel({
  promptText,
  researchTier,
  debounceMs = 350,
  onProjectionChange,
}: ResearchLaunchBudgetPanelProps) {
  const [budget, setBudget] = useState<BudgetResponse | null>(null);
  const [tree, setTree] = useState<DecisionTreeSelectionResponse | null>(null);
  const [estimate, setEstimate] = useState<PromptCostEstimateResponse | null>(
    null,
  );
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Residual (de): surface projection to parent for launch gating honesty.
  useEffect(() => {
    if (!onProjectionChange) return;
    onProjectionChange({
      wouldExceedBudget:
        estimate?.would_exceed_budget === true
          ? true
          : estimate?.would_exceed_budget === false
            ? false
            : null,
      pricingKnown: Boolean(estimate?.pricing_known),
      estimatedUsdHigh: estimate?.estimated_usd_high ?? null,
      remainingUsd: budget?.remaining_usd ?? null,
      modelId: tree?.model_id ?? null,
    });
  }, [estimate, budget?.remaining_usd, tree?.model_id, onProjectionChange]);

  const mapping = useMemo(
    () => dispatchTierFor(researchTier),
    [researchTier],
  );

  const barPct = useMemo(() => {
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

  const loadStatic = useCallback(async () => {
    try {
      const [b, t] = await Promise.all([
        fetchSettingsBudget(),
        fetchDecisionTreeSelection(),
      ]);
      setBudget(b);
      setTree(t);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    void loadStatic();
  }, [loadStatic]);

  useEffect(() => {
    const chars = promptText.length;
    // Empty / tiny prompt: clear estimate honestly rather than projecting noise.
    if (chars < 3) {
      setEstimate(null);
      return;
    }
    let cancelled = false;
    const handle = window.setTimeout(() => {
      setBusy(true);
      void estimatePromptCost({
        tier: mapping.tier,
        input_chars: chars,
        expected_output_tokens: mapping.expected_output_tokens,
        model: tree?.model_id ?? null,
        provider: tree?.provider_id ?? null,
      })
        .then((res) => {
          if (!cancelled) setEstimate(res);
        })
        .catch((e) => {
          if (!cancelled) {
            setError(e instanceof Error ? e.message : String(e));
          }
        })
        .finally(() => {
          if (!cancelled) setBusy(false);
        });
    }, debounceMs);
    return () => {
      cancelled = true;
      window.clearTimeout(handle);
    };
  }, [
    promptText,
    mapping.tier,
    mapping.expected_output_tokens,
    tree?.model_id,
    tree?.provider_id,
    debounceMs,
  ]);

  return (
    <div
      className="rounded-hog border border-rule dark:border-charcoal-1 bg-ice-0/80 dark:bg-charcoal-2/80 px-3 py-2 space-y-2"
      data-testid="research-launch-budget-panel"
      data-view-format="html"
      data-research-tier={researchTier}
      data-dispatch-tier={mapping.tier}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
          Budget & projection
        </span>
        {busy ? (
          <span className="text-[10px] font-mono text-ink-mute">projecting…</span>
        ) : null}
      </div>

      {error ? (
        <p
          className="text-[11px] font-mono text-emperor"
          data-testid="research-launch-budget-error"
        >
          {error}
        </p>
      ) : null}

      {/* Daily budget bar — never invent $0 when spent unknown */}
      <div data-testid="research-launch-budget-bar" className="space-y-1">
        <div className="flex justify-between text-[11px] font-mono text-ink dark:text-bright">
          <span>
            Spent{" "}
            {budget?.spent_status === "known" && budget.spent_usd != null
              ? formatUsd(budget.spent_usd)
              : budget?.spent_status === "unknown"
                ? "unknown"
                : "—"}
          </span>
          <span>
            Cap{" "}
            {budget?.daily_cap_usd != null
              ? formatUsd(budget.daily_cap_usd)
              : "—"}
          </span>
        </div>
        <div
          className="h-1.5 w-full rounded-full bg-rule/40 dark:bg-charcoal-1 overflow-hidden"
          role="progressbar"
          aria-valuenow={barPct ?? undefined}
          aria-valuemin={0}
          aria-valuemax={100}
          data-testid="research-launch-budget-bar-track"
        >
          {barPct != null ? (
            <div
              className={
                "h-full rounded-full transition-all " +
                (barPct >= 90
                  ? "bg-emperor"
                  : barPct >= 70
                    ? "bg-sun"
                    : "bg-aurora")
              }
              style={{ width: `${barPct}%` }}
              data-testid="research-launch-budget-bar-fill"
            />
          ) : (
            <div
              className="h-full w-0"
              data-testid="research-launch-budget-bar-unknown"
            />
          )}
        </div>
        <p className="text-[10px] font-mono text-ink-mute dark:text-moonlight">
          Remaining{" "}
          {budget?.remaining_usd != null
            ? formatUsd(budget.remaining_usd)
            : budget?.spent_status === "unknown"
              ? "unknown (ledger not wired)"
              : "—"}
        </p>
      </div>

      {/* Decision-tree driver (advisory) */}
      <p
        className="text-[11px] font-mono text-ink dark:text-bright"
        data-testid="research-launch-decision-tree"
      >
        Driver:{" "}
        {tree?.installed && tree.model_id
          ? `${tree.provider_id ?? "?"} / ${tree.model_id}`
          : "(none installed — Settings → decision tree)"}
      </p>

      {/* Prompt cost projection */}
      <div data-testid="research-launch-projection" className="space-y-0.5">
        {promptText.trim().length < 3 ? (
          <p className="text-[11px] font-mono text-ink-mute dark:text-moonlight">
            Type ≥3 chars to project this prompt against your cap.
          </p>
        ) : estimate ? (
          <>
            <p className="text-[11px] font-mono text-ink dark:text-bright">
              Projected ({mapping.tier}):{" "}
              {estimate.pricing_known &&
              estimate.estimated_usd_low != null &&
              estimate.estimated_usd_high != null
                ? `${formatUsd(estimate.estimated_usd_low)}–${formatUsd(estimate.estimated_usd_high)}`
                : "unknown (rates unset)"}
            </p>
            <p
              className={
                "text-[11px] font-mono " +
                (estimate.would_exceed_budget === true
                  ? "text-emperor font-semibold"
                  : "text-ink-mute dark:text-moonlight")
              }
              data-testid="research-launch-would-exceed"
              data-would-exceed={
                estimate.would_exceed_budget == null
                  ? "unknown"
                  : estimate.would_exceed_budget
                    ? "true"
                    : "false"
              }
            >
              {estimate.would_exceed_budget === true
                ? "⚠ High band may exceed remaining daily budget"
                : estimate.would_exceed_budget === false
                  ? "Within remaining budget (high band)"
                  : "Cannot assert budget impact (remaining unknown or rates unset)"}
            </p>
          </>
        ) : (
          <p className="text-[11px] font-mono text-ink-mute">…</p>
        )}
      </div>
    </div>
  );
}

export default ResearchLaunchBudgetPanel;
