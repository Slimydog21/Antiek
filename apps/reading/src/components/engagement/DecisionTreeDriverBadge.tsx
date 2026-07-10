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
 * Residual (pg): optional promptText projects estimated cost impact on remaining
 * daily budget (operator foresight before send; not a hard gate).
 * Residual (rm): Settings deep-link anchors to #notdiamond-advisory so operators
 * can compare weekly ND suggestion vs installed driver (advisory only).
 * Residual (afc): when researchTier is set, surface Antiek-bench weekly
 * best-by-task for mapped task_class (parity launch budget afb · never auto-route).
 * Residual (afe): explicit Install best-for-task button when best differs from
 * installed driver (operator click only · never auto-route).
 * Residual (aoz): install status records previous driver; already-best chrome
 * when installed matches weekly best; never-router honesty on install path.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  estimatePromptCost,
  fetchAntiekBenchLeaderboard,
  fetchDecisionTreeSelection,
  fetchSettingsBudget,
  installDecisionTreeSelection,
  type AntiekBenchLeaderboardResponse,
  type BudgetResponse,
  type DecisionTreeSelectionResponse,
  type PromptCostEstimateResponse,
} from "../../api/settings";
import {
  bestModelForTaskClass,
  researchTierToBenchTaskClass,
  type ResearchLaunchTier,
} from "./ResearchLaunchBudgetPanel";

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
  /**
   * Residual (pg): live prompt text for cost projection vs remaining budget.
   * When empty, projection strip is omitted (badge stays read-only advisory).
   */
  promptText?: string | null;
};

export function DecisionTreeDriverBadge({
  researchTier = null,
  promptText = null,
}: DecisionTreeDriverBadgeProps = {}) {
  const [tree, setTree] = useState<DecisionTreeSelectionResponse | null>(null);
  const [budget, setBudget] = useState<BudgetResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshTick, setRefreshTick] = useState(0);
  const [refreshing, setRefreshing] = useState(false);
  const [projection, setProjection] =
    useState<PromptCostEstimateResponse | null>(null);
  const [leaderboard, setLeaderboard] =
    useState<AntiekBenchLeaderboardResponse | null>(null);
  const [installBusy, setInstallBusy] = useState(false);
  const [installStatus, setInstallStatus] = useState<string | null>(null);
  const normalizedTier = (researchTier || "").trim().toLowerCase() || "";
  const promptChars = (promptText || "").length;
  const benchTaskClass =
    normalizedTier === "fast" ||
    normalizedTier === "deep" ||
    normalizedTier === "wrestle"
      ? researchTierToBenchTaskClass(normalizedTier as ResearchLaunchTier)
      : null;
  const bestByTask = useMemo(
    () =>
      benchTaskClass
        ? bestModelForTaskClass(leaderboard, benchTaskClass)
        : null,
    [leaderboard, benchTaskClass],
  );
  const bestDiffers = Boolean(
    bestByTask?.model_id &&
      (!tree?.model_id || bestByTask.model_id !== tree.model_id),
  );

  const onInstallBestForTask = useCallback(async () => {
    if (!bestByTask?.model_id || !benchTaskClass) return;
    setInstallBusy(true);
    setInstallStatus(null);
    setError(null);
    // Residual (aoz): capture previous driver for install audit trail.
    const previousModel = (tree?.model_id || "").trim() || "none";
    try {
      const result = await installDecisionTreeSelection({
        model_id: bestByTask.model_id,
        provider_id: tree?.provider_id ?? null,
      });
      setTree(result);
      setInstallStatus(
        `Installed ${bestByTask.model_id} for ${benchTaskClass}` +
          ` (was ${previousModel} · advisory · explicit · never auto-route)`,
      );
      setRefreshTick((n) => n + 1);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setInstallBusy(false);
    }
  }, [bestByTask?.model_id, benchTaskClass, tree?.model_id, tree?.provider_id]);

  const load = useCallback(async () => {
    setRefreshing(true);
    setError(null);
    try {
      const d = new Date();
      const onejan = new Date(d.getFullYear(), 0, 1);
      const week = Math.ceil(
        ((d.getTime() - onejan.getTime()) / 86400000 + onejan.getDay() + 1) / 7,
      );
      const weekId = `${d.getFullYear()}-W${String(week).padStart(2, "0")}`;
      const [t, b, lb] = await Promise.all([
        fetchDecisionTreeSelection(),
        fetchSettingsBudget().catch(() => null),
        fetchAntiekBenchLeaderboard({ weekId }).catch(() => null),
      ]);
      setTree(t);
      setBudget(b);
      setLeaderboard(lb);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load, refreshTick]);

  // Residual (pg): project prompt cost impact when host provides promptText.
  useEffect(() => {
    const text = (promptText || "").trim();
    if (!text) {
      setProjection(null);
      return;
    }
    let cancelled = false;
    const tier =
      normalizedTier === "fast" ||
      normalizedTier === "deep" ||
      normalizedTier === "wrestle"
        ? normalizedTier
        : "deep";
    void estimatePromptCost({
      input_chars: text.length,
      expected_output_tokens: tier === "wrestle" ? 8000 : tier === "fast" ? 1200 : 2500,
      tier,
      model: tree?.model_id ?? null,
      provider: tree?.provider_id ?? null,
    })
      .then((p) => {
        if (!cancelled) setProjection(p);
      })
      .catch(() => {
        if (!cancelled) setProjection(null);
      });
    return () => {
      cancelled = true;
    };
  }, [promptText, normalizedTier, tree?.model_id, tree?.provider_id, refreshTick]);

  const pct = useMemo(() => budgetUsagePct(budget), [budget]);
  const projectedHigh = projection?.estimated_usd_high ?? null;
  const remainingAfter =
    budget?.remaining_usd != null && projectedHigh != null
      ? budget.remaining_usd - projectedHigh
      : null;

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
          href="/settings#decision-tree-panel"
          data-testid="decision-tree-settings-link"
          className="underline opacity-80 hover:opacity-100"
          title="Open Settings decision-tree: install driver, budget bar, sample cost projection"
        >
          Settings
        </a>
        {/* Residual (rm): NotDiamond weekly advisory delta (never auto-route). */}
        <a
          href="/settings#notdiamond-advisory"
          data-testid="decision-tree-notdiamond-advisory-link"
          data-notdiamond-authority="advisory_only"
          className="underline opacity-80 hover:opacity-100"
          title="Open Settings → NotDiamond weekly advisory vs installed driver (advisory only · never dispatch authority)"
        >
          ND advisory
        </a>
        {/* Residual (oa/yl): dual-gate prep on shared driver+budget chokepoint. */}
        {/* Residual (aaz): deep-link #l7-notdiamond — badge stamps advisory_only L7;
            root checklist alone did not land operators on ND-never-router doctrine. */}
        <a
          href="/docs/campaigns/2026-07-09-research-reading-spine/DUAL-GATE-L1-L4-OPERATOR-CHECKLIST.md#l7-notdiamond"
          data-testid="decision-tree-dual-gate-checklist-link"
          data-offline-default="true"
          data-l7-notdiamond="advisory_only"
          className="underline opacity-80 hover:opacity-100"
          title="Dual-gate L7 NotDiamond advisory-only checklist (offline default · never dispatch authority)"
        >
          Dual-gate L7 ND advisory
        </a>
        {/* Residual (aje): shared driver chokepoint → competitive DR honesty map. */}
        <a
          href="/settings#settings-competitive-dr-scorecard"
          data-testid="decision-tree-competitive-scorecard-link"
          className="underline opacity-80 hover:opacity-100"
          title="Settings competitive deep-research scorecard (model choice · ND never router · shipped vs deferred)"
        >
          Competitive DR scorecard
        </a>
        {/* Residual (akx): FUTURE competitive DR quality + prompt-cost at driver chokepoint. */}
        <a
          href="/docs/campaigns/2026-07-09-research-reading-spine/FUTURE-AGENT-SPEC-competitive-deep-research-quality.md"
          data-testid="decision-tree-competitive-dr-future-agent-link"
          className="underline opacity-80 hover:opacity-100"
          title="FUTURE-AGENT competitive deep-research quality brief (model choice · ND advisory only · budget-before-fire)"
        >
          FUTURE · competitive DR quality
        </a>
        <a
          href="/settings#prompt-cost-projection"
          data-testid="decision-tree-prompt-cost-projection-link"
          className="underline opacity-80 hover:opacity-100"
          title="Settings prompt-cost projection: estimate how this driver+prompt hits remaining daily budget"
        >
          Settings · prompt-cost projection
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

      {/* Residual (afc/afe): best-by-task + explicit install when differs. */}
      {benchTaskClass ? (
        <div
          className="opacity-90 space-y-0.5"
          data-testid="decision-tree-bench-best-by-task"
          data-task-class={benchTaskClass}
          data-best-model={bestByTask?.model_id ?? ""}
          data-best-score={
            bestByTask != null ? String(bestByTask.score) : ""
          }
          data-week-id={leaderboard?.week_id ?? ""}
          data-advisory-only="true"
          data-matches-installed={String(
            Boolean(
              bestByTask?.model_id &&
                tree?.model_id &&
                bestByTask.model_id === tree.model_id,
            ),
          )}
          data-install-available={String(bestDiffers)}
          role="status"
        >
          <p>
            Bench best for {benchTaskClass}
            {bestByTask ? (
              <>
                :{" "}
                <code data-testid="decision-tree-bench-best-model">
                  {bestByTask.model_id}
                </code>{" "}
                ({bestByTask.score.toFixed(2)})
                {tree?.model_id && bestByTask.model_id === tree.model_id
                  ? " · matches installed"
                  : " · advisory only"}
              </>
            ) : (
              <>: (no weekly scores)</>
            )}{" "}
            ·{" "}
            <a
              href="/settings#antiek-bench-leaderboard"
              className="underline opacity-80 hover:opacity-100"
              data-testid="decision-tree-bench-leaderboard-link"
              title="Open Settings weekly leaderboard (install best-by-task explicitly)"
            >
              leaderboard
            </a>
          </p>
          {bestDiffers ? (
            <button
              type="button"
              data-testid="decision-tree-install-best-for-task"
              data-install-model-id={bestByTask?.model_id ?? ""}
              data-install-task-class={benchTaskClass}
              data-previous-model-id={tree?.model_id ?? "none"}
              data-advisory-only="true"
              data-never-auto-route="true"
              disabled={installBusy || refreshing}
              onClick={() => void onInstallBestForTask()}
              className="underline opacity-80 hover:opacity-100 disabled:opacity-50"
              title={`Install ${bestByTask?.model_id} (best ${benchTaskClass}) as decision-tree driver — was ${tree?.model_id || "none"} · explicit operator action · never auto-route`}
            >
              {installBusy
                ? "Installing…"
                : `Install best for ${benchTaskClass}`}
            </button>
          ) : bestByTask?.model_id ? (
            // Residual (aoz): already-best honesty when installed matches weekly best.
            <p
              className="text-[10px] font-mono opacity-80"
              data-testid="decision-tree-already-best-for-task"
              data-already-best="true"
              data-task-class={benchTaskClass}
              data-model-id={bestByTask.model_id}
              data-advisory-only="true"
              data-never-auto-route="true"
              role="status"
            >
              Already best for {benchTaskClass}:{" "}
              <code>{bestByTask.model_id}</code> · advisory only · never
              auto-route ·{" "}
              <a
                href="/settings#antiek-bench-suite-proposal"
                className="underline opacity-80 hover:opacity-100"
                data-testid="decision-tree-suite-proposal-link"
                title="Antiek-bench recursive suite rewrite proposal (propose≠promote)"
              >
                suite rewrite
              </a>
            </p>
          ) : null}
          {installStatus ? (
            <p
              className="text-[10px] font-mono opacity-80"
              data-testid="decision-tree-install-best-status"
              data-never-auto-route="true"
              data-advisory-only="true"
              role="status"
            >
              {installStatus}
            </p>
          ) : null}
        </div>
      ) : null}

      {/* Residual (hv/ku): machine-readable driver + budget + depth metrics. */}
      <div
        data-testid="decision-tree-driver-metrics"
        data-installed={String(Boolean(tree?.installed && tree.model_id))}
        data-model-id={tree?.model_id ?? ""}
        data-provider-id={tree?.provider_id ?? ""}
        data-research-tier={normalizedTier}
        data-bench-task-class={benchTaskClass ?? ""}
        data-bench-best-model={bestByTask?.model_id ?? ""}
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

      {/* Residual (pg): prompt cost projection vs remaining daily budget. */}
      {promptChars > 0 ? (
        <div
          className="space-y-0.5 border-t border-ink/10 pt-1 dark:border-bright/10"
          data-testid="decision-tree-prompt-projection"
          data-prompt-chars={String(promptChars)}
          data-pricing-known={String(Boolean(projection?.pricing_known))}
          data-would-exceed={String(
            projection?.would_exceed_budget == null
              ? "unknown"
              : String(projection.would_exceed_budget),
          )}
          data-estimated-usd-high={
            projectedHigh != null ? String(projectedHigh) : ""
          }
          data-remaining-after-usd={
            remainingAfter != null ? String(remainingAfter) : ""
          }
          // Residual (aeb): machine-readable when projected high burns past remaining.
          data-goes-negative={
            remainingAfter != null ? String(remainingAfter < 0) : "unknown"
          }
          data-view-format="html"
          role="status"
        >
          <p className="opacity-90">
            Prompt projection ({promptChars} chars):{" "}
            {projection?.pricing_known && projectedHigh != null
              ? `est. ≤ ${formatUsd(projectedHigh)}`
              : "pricing unknown"}
            {projection?.would_exceed_budget === true
              ? " · may exceed remaining budget"
              : projection?.would_exceed_budget === false
                ? " · within remaining budget"
                : ""}
          </p>
          {remainingAfter != null ? (
            <p
              className={remainingAfter < 0 ? "font-semibold opacity-100" : "opacity-80"}
              data-testid="decision-tree-prompt-remaining-after"
              data-remaining-after-usd={String(remainingAfter)}
              // Residual (aeb): soft foresight when remaining goes negative.
              data-goes-negative={String(remainingAfter < 0)}
              role="status"
            >
              Remaining after prompt ≈ {formatUsd(remainingAfter)}
              {remainingAfter < 0
                ? " · over remaining high-band (soft foresight · not a hard block)"
                : ""}
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

export default DecisionTreeDriverBadge;
