/**
 * DecisionTreeDriverBadge — show installed decision-tree driver (residual cw).
 *
 * Read-only advisory surface: model choice is Settings-owned; this badge
 * makes the active driver visible on research/reading hosts without implying
 * NotDiamond authority.
 *
 * Residual (eq): compact daily budget usage bar next to the driver so every
 * surface that mounts the badge also shows spend vs cap / remaining (honest
 * unknown when spent_status is unknown). Not a launch soft-gate — that stays
 * on ResearchLaunchBudgetPanel.
 * Residual (fd): manual refresh of driver + budget without remounting the host.
 * Residual (fj): deep-link to Settings decision-tree / model budget controls.
 * Residual (oa): dual-gate L1–L4 checklist deep-link on shared driver badge
 * (prep only; every host that mounts the badge can reach live-enable prep).
 * Residual (ku): optional researchTier chrome so model driver + depth posture
 * share one decision-tree surface (not NotDiamond authority).
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  fetchDecisionTreeSelection,
  fetchSettingsBudget,
  type BudgetResponse,
  type DecisionTreeSelectionResponse,
} from "../../api/settings";

function formatUsd(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return "—";
  return `$${n.toFixed(2)}`;
}

/** Pure helper for tests: spent fraction of daily cap (0–100), or null if unknown. */
export function budgetUsagePct(budget: BudgetResponse | null): number | null {
  if (
    !budget ||
    budget.daily_cap_usd == null ||
    budget.spent_usd == null ||
    budget.daily_cap_usd <= 0 ||
    budget.spent_status === "unknown" ||
    budget.spent_status === "no_cap"
  ) {
    return null;
  }
  return Math.min(100, (budget.spent_usd / budget.daily_cap_usd) * 100);
}

export type DecisionTreeDriverBadgeProps = {
  /**
   * Residual (ku): closed research tier for depth posture chrome when host
   * knows workstation depth (fast|deep|wrestle). Advisory only.
   */
  researchTier?: "fast" | "deep" | "wrestle" | string | null;
};

export function DecisionTreeDriverBadge({
  researchTier = null,
}: DecisionTreeDriverBadgeProps = {}) {
  const [tree, setTree] = useState<DecisionTreeSelectionResponse | null>(null);
  const [budget, setBudget] = useState<BudgetResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshTick, setRefreshTick] = useState(0);
  const [refreshing, setRefreshing] = useState(false);
  const normalizedTier = (researchTier || "").trim().toLowerCase() || "";

  const load = useCallback(async () => {
    setRefreshing(true);
    setError(null);
    try {
      const [t, b] = await Promise.all([
        fetchDecisionTreeSelection(),
        fetchSettingsBudget().catch(() => null),
      ]);
      setTree(t);
      setBudget(b);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load, refreshTick]);

  const pct = useMemo(() => budgetUsagePct(budget), [budget]);

  return (
    <div
      className="space-y-1 text-[11px] font-mono text-shadow-1 dark:text-moonlight"
      data-testid="decision-tree-driver-badge"
      data-view-format="html"
      data-refresh-tick={String(refreshTick)}
      data-research-tier={normalizedTier}
    >
      <div className="flex flex-wrap items-center gap-2">
        {error ? (
          <span data-testid="decision-tree-driver-error">Driver unknown</span>
        ) : tree?.installed && tree.model_id ? (
          <span data-testid="decision-tree-driver-active">
            Driver: {tree.provider_id ?? "?"} / {tree.model_id}
          </span>
        ) : (
          <span data-testid="decision-tree-driver-none">
            Driver: (none — Settings → decision tree)
          </span>
        )}
        {/* Residual (fd): re-fetch driver + budget after Settings changes. */}
        <button
          type="button"
          data-testid="decision-tree-driver-refresh"
          className="underline opacity-80 hover:opacity-100"
          disabled={refreshing}
          onClick={() => setRefreshTick((n) => n + 1)}
        >
          {refreshing ? "Refreshing…" : "Refresh"}
        </button>
        {/* Residual (fj): open Settings for model install + daily budget. */}
        <a
          href="/settings"
          data-testid="decision-tree-settings-link"
          className="underline opacity-80 hover:opacity-100"
          title="Open Settings to install decision-tree driver and set daily budget"
        >
          Settings
        </a>
        {/* Residual (oa): dual-gate prep on shared driver+budget chokepoint. */}
        <a
          href="/docs/campaigns/2026-07-09-research-reading-spine/DUAL-GATE-L1-L4-OPERATOR-CHECKLIST.md"
          data-testid="decision-tree-dual-gate-checklist-link"
          className="underline opacity-80 hover:opacity-100"
          title="Dual-gate L1–L4 checklist (prep only; offline default)"
        >
          Dual-gate
        </a>
      </div>

      {/* Residual (ku): depth posture next to model driver (advisory). */}
      {normalizedTier ? (
        <p
          className="opacity-90"
          data-testid="decision-tree-research-tier"
          data-research-tier={normalizedTier}
          role="status"
        >
          Research tier: <strong>{normalizedTier}</strong>
          {normalizedTier === "wrestle"
            ? " · multi-minute long-horizon depth"
            : normalizedTier === "fast"
              ? " · flash / distill depth"
              : " · deep / synthesize depth"}
        </p>
      ) : null}

      {/* Residual (hv/ku): machine-readable driver + budget + depth metrics. */}
      <div
        data-testid="decision-tree-driver-metrics"
        data-installed={String(Boolean(tree?.installed && tree.model_id))}
        data-model-id={tree?.model_id ?? ""}
        data-provider-id={tree?.provider_id ?? ""}
        data-research-tier={normalizedTier}
        data-spent-status={budget?.spent_status ?? "unknown"}
        data-spent-usd={
          budget?.spent_usd != null ? String(budget.spent_usd) : ""
        }
        data-cap-usd={
          budget?.daily_cap_usd != null ? String(budget.daily_cap_usd) : ""
        }
        data-remaining-usd={
          budget?.remaining_usd != null ? String(budget.remaining_usd) : ""
        }
        data-usage-pct={pct != null ? String(Math.round(pct)) : ""}
        data-view-format="html"
        role="status"
      >
        Driver metrics · installed=
        {String(Boolean(tree?.installed && tree.model_id))} · model=
        {tree?.model_id || "(none)"} · usage_pct=
        {pct != null ? `${Math.round(pct)}%` : "unknown"}
        {normalizedTier ? ` · tier=${normalizedTier}` : ""}
      </div>

      {/* Residual (eq): compact usage bar for the operator's daily API budget. */}
      <div
        className="space-y-0.5"
        data-testid="decision-tree-budget-usage"
        data-spent-status={budget?.spent_status ?? "unknown"}
      >
        <div className="flex justify-between gap-2">
          <span data-testid="decision-tree-budget-spent">
            Spent{" "}
            {budget?.spent_status === "known" && budget.spent_usd != null
              ? formatUsd(budget.spent_usd)
              : budget?.spent_status === "unknown"
                ? "unknown"
                : "—"}
          </span>
          <span data-testid="decision-tree-budget-cap">
            /{" "}
            {budget?.daily_cap_usd != null
              ? formatUsd(budget.daily_cap_usd)
              : "no cap"}
          </span>
        </div>
        <div
          className="h-1.5 w-full overflow-hidden rounded bg-ink/10 dark:bg-bright/10"
          data-testid="decision-tree-budget-bar-track"
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={pct != null ? Math.round(pct) : undefined}
          aria-label="Daily API budget usage"
        >
          {pct != null ? (
            <div
              className="h-full bg-aurora/80"
              data-testid="decision-tree-budget-bar-fill"
              style={{ width: `${pct}%` }}
            />
          ) : (
            <div
              className="h-full w-full bg-ink/5 dark:bg-bright/5"
              data-testid="decision-tree-budget-bar-unknown"
            />
          )}
        </div>
        <p data-testid="decision-tree-budget-remaining">
          Remaining{" "}
          {budget?.remaining_usd != null
            ? formatUsd(budget.remaining_usd)
            : budget?.spent_status === "unknown"
              ? "unknown"
              : "—"}
        </p>
      </div>
    </div>
  );
}

export default DecisionTreeDriverBadge;
