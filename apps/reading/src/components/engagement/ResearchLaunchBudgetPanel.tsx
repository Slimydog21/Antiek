/**
 * ResearchLaunchBudgetPanel — budget bar + prompt cost projection at launch.
 *
 * Residual (bp): operators see daily spend vs cap and how the *current* prompt
 * would affect remaining budget before Ask. Reuses Settings #440 estimate +
 * decision-tree read surfaces — never invents $0 when unknown.
 *
 * Research tier maps to dispatch tier for projection only:
 *   fast → flash · deep → pro · wrestle → wrestle (competitive depth preset)
 * Decision-tree driver is advisory display (Hermes still owns dispatch).
 *
 * Residual (gm): optional in-panel depth-tier picker (flash|pro|wrestle) so
 * launch surfaces can project Perplexity-speed vs OpenAI-depth without
 * leaving the research flywheel.
 * Residual (hp): research-launch-projection-metrics machine attrs (usd band,
 * would_exceed, chars, tier) for competitive budget-before-fire audit.
 * Residual (jw): intensity factor chrome (MO ceiling multipliers shared map)
 * so launch surfaces show wrestle/fast cost posture next to projection.
 * Residual (wa): remaining-after-prompt projection (remaining − high band)
 * parity DecisionTree badge (pg) + Midnight Oil ceiling (um) — operator sees
 * how fire would affect daily cap before Ask.
 * Residual (afb): Antiek-bench weekly best-by-task advisory for mapped task
 * class (fast→distill · deep→synthesize · wrestle→wrestle) — never auto-routes.
 * Residual (aff): explicit Install best for {task} when best differs (parity
 * driver badge afe · never auto-route).
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
  formatResearchTierCeilingFactor,
  mapResearchTierToCeilingMultiplier,
} from "../../lib/researchTier";

export type ResearchLaunchBudgetProjection = {
  wouldExceedBudget: boolean | null;
  pricingKnown: boolean;
  estimatedUsdHigh: number | null;
  remainingUsd: number | null;
  modelId: string | null;
};

/** Curated research entry tiers (not raw model ids). */
export type ResearchLaunchTier = "fast" | "deep" | "wrestle";

export type ResearchLaunchBudgetPanelProps = {
  /** Live composer text used for input_chars projection. */
  promptText: string;
  /** Curated research entry tier (not a raw model id). */
  researchTier: ResearchLaunchTier;
  /** Debounce ms for estimate calls (default 350). */
  debounceMs?: number;
  /**
   * Residual (de): notify parent when projection updates so launch surfaces
   * can soft-warn / disable before fire without re-fetching Settings.
   */
  onProjectionChange?: (projection: ResearchLaunchBudgetProjection) => void;
  /**
   * Residual (gm): show flash|pro|wrestle picker; local override of
   * researchTier for projection only.
   */
  allowTierPick?: boolean;
  /** Notify parent when operator picks a depth tier (optional). */
  onResearchTierChange?: (tier: ResearchLaunchTier) => void;
};

/** Map curated research depth to Antiek-bench task_class for model quality. */
export function researchTierToBenchTaskClass(
  tier: ResearchLaunchTier,
): "distill" | "synthesize" | "wrestle" {
  if (tier === "fast") return "distill";
  if (tier === "wrestle") return "wrestle";
  return "synthesize";
}

function isoWeekId(d = new Date()): string {
  const onejan = new Date(d.getFullYear(), 0, 1);
  const week = Math.ceil(
    ((d.getTime() - onejan.getTime()) / 86400000 + onejan.getDay() + 1) / 7,
  );
  return `${d.getFullYear()}-W${String(week).padStart(2, "0")}`;
}

/** Best model_id for task_class from weekly leaderboard rows (advisory). */
export function bestModelForTaskClass(
  board: AntiekBenchLeaderboardResponse | null | undefined,
  taskClass: string,
): { model_id: string; score: number } | null {
  if (!board?.models?.length) return null;
  let best: { model_id: string; score: number } | null = null;
  for (const row of board.models) {
    const score = row.by_task_class?.[taskClass];
    if (typeof score !== "number" || Number.isNaN(score)) continue;
    if (!best || score > best.score) {
      best = { model_id: row.model_id, score };
    }
  }
  return best;
}

function dispatchTierFor(researchTier: ResearchLaunchTier): {
  tier: string;
  expected_output_tokens: number;
} {
  if (researchTier === "fast") {
    return { tier: "flash", expected_output_tokens: 800 };
  }
  if (researchTier === "wrestle") {
    // Competitive depth / long-horizon synthesis (OpenAI Deep Research posture).
    return { tier: "wrestle", expected_output_tokens: 4000 };
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
  allowTierPick = false,
  onResearchTierChange,
}: ResearchLaunchBudgetPanelProps) {
  const [budget, setBudget] = useState<BudgetResponse | null>(null);
  const [tree, setTree] = useState<DecisionTreeSelectionResponse | null>(null);
  const [estimate, setEstimate] = useState<PromptCostEstimateResponse | null>(
    null,
  );
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // Residual (afb): weekly leaderboard for best-by-task advisory (never auto-route).
  const [leaderboard, setLeaderboard] =
    useState<AntiekBenchLeaderboardResponse | null>(null);
  const [installBusy, setInstallBusy] = useState(false);
  const [installStatus, setInstallStatus] = useState<string | null>(null);
  // Residual (gm): local tier override when picker is enabled.
  // Residual (gr): when parent drives researchTier (e.g. StartResearch radios
  // or onResearchTierChange), clear override so prop and projection stay aligned.
  const [pickedTier, setPickedTier] = useState<ResearchLaunchTier | null>(
    null,
  );
  useEffect(() => {
    setPickedTier(null);
  }, [researchTier]);
  const activeTier: ResearchLaunchTier = pickedTier ?? researchTier;
  const benchTaskClass = researchTierToBenchTaskClass(activeTier);
  const bestByTask = useMemo(
    () => bestModelForTaskClass(leaderboard, benchTaskClass),
    [leaderboard, benchTaskClass],
  );
  const bestDiffers = Boolean(
    bestByTask?.model_id &&
      (!tree?.model_id || bestByTask.model_id !== tree.model_id),
  );

  const onInstallBestForTask = useCallback(async () => {
    if (!bestByTask?.model_id) return;
    setInstallBusy(true);
    setInstallStatus(null);
    setError(null);
    try {
      const result = await installDecisionTreeSelection({
        model_id: bestByTask.model_id,
        provider_id: tree?.provider_id ?? null,
      });
      setTree(result);
      setInstallStatus(
        `Installed ${bestByTask.model_id} for ${benchTaskClass} (advisory · explicit)`,
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setInstallBusy(false);
    }
  }, [bestByTask?.model_id, benchTaskClass, tree?.provider_id]);

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
    () => dispatchTierFor(activeTier),
    [activeTier],
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

  // Residual (wa): remaining after high-band fire (soft foresight, never invent $0).
  const remainingAfterUsd = useMemo(() => {
    const remaining = budget?.remaining_usd;
    const high = estimate?.estimated_usd_high;
    if (remaining == null || high == null || Number.isNaN(remaining) || Number.isNaN(high)) {
      return null;
    }
    return remaining - high;
  }, [budget?.remaining_usd, estimate?.estimated_usd_high]);

  const loadStatic = useCallback(async () => {
    try {
      const weekId = isoWeekId();
      const [b, t, lb] = await Promise.all([
        fetchSettingsBudget(),
        fetchDecisionTreeSelection(),
        fetchAntiekBenchLeaderboard({ weekId }).catch(() => null),
      ]);
      setBudget(b);
      setTree(t);
      setLeaderboard(lb);
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
      data-research-tier={activeTier}
      data-dispatch-tier={mapping.tier}
      data-allow-tier-pick={allowTierPick ? "true" : "false"}
      data-bench-task-class={benchTaskClass}
      data-bench-best-model={bestByTask?.model_id ?? ""}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
          Budget & projection
        </span>
        <div className="flex items-center gap-2">
          {/* Residual (fr): jump to Settings for daily cap + decision-tree. */}
          {/* Residual (sc): deep-link to decision-tree + budget foresight (sa/sb). */}
          <a
            href="/settings#decision-tree-panel"
            data-testid="research-launch-budget-settings-link"
            className="text-[10px] font-mono underline opacity-80 hover:opacity-100"
            title="Open Settings decision-tree: model driver, budget bar, sample cost projection"
          >
            Settings · driver
          </a>
          {/* Residual (nu/ym): dual-gate prep on shared launch budget chokepoint. */}
          {/* Residual (aaz): deep-link #l7-notdiamond (parity DecisionTreeDriverBadge). */}
          <a
            href="/docs/campaigns/2026-07-09-research-reading-spine/DUAL-GATE-L1-L4-OPERATOR-CHECKLIST.md#l7-notdiamond"
            data-testid="research-launch-budget-dual-gate-checklist-link"
            data-offline-default="true"
            data-l7-notdiamond="advisory_only"
            className="text-[10px] font-mono underline opacity-80 hover:opacity-100"
            title="Dual-gate L7 NotDiamond advisory-only checklist (offline default · never dispatch authority)"
          >
            Dual-gate L7 ND advisory
          </a>
          {busy ? (
            <span className="text-[10px] font-mono text-ink-mute">projecting…</span>
          ) : null}
        </div>
      </div>

      {/* Residual (gm): flash | pro | wrestle depth picker for projection. */}
      {allowTierPick ? (
        <div
          className="flex flex-wrap items-center gap-1"
          data-testid="research-launch-tier-picker"
          role="group"
          aria-label="Research depth tier"
        >
          {(
            [
              { id: "fast" as const, label: "flash", title: "Fast / flash projection" },
              { id: "deep" as const, label: "pro", title: "Deep / pro projection" },
              {
                id: "wrestle" as const,
                label: "wrestle",
                title: "Wrestle / long-horizon depth projection",
              },
            ] as const
          ).map((t) => {
            const selected = activeTier === t.id;
            return (
              <button
                key={t.id}
                type="button"
                data-testid={`research-launch-tier-${t.id}`}
                data-selected={selected ? "true" : "false"}
                title={t.title}
                onClick={() => {
                  setPickedTier(t.id);
                  onResearchTierChange?.(t.id);
                }}
                className={
                  "rounded border px-2 py-0.5 text-[10px] font-mono " +
                  (selected
                    ? "border-aurora bg-aurora/10 text-ink dark:text-bright"
                    : "border-ink/20 text-ink-mute hover:bg-ink/5 dark:border-bright/20")
                }
              >
                {t.label}
              </button>
            );
          })}
        </div>
      ) : null}

      {/* Residual (jw): intensity factor from shared MO ceiling multipliers. */}
      <p
        className="text-[10px] font-mono opacity-70"
        data-testid="research-launch-tier-intensity"
        data-research-tier={activeTier}
        data-intensity-multiplier={String(
          mapResearchTierToCeilingMultiplier(activeTier),
        )}
        data-expected-output-tokens={String(mapping.expected_output_tokens)}
        role="status"
      >
        Intensity:{" "}
        <strong>{formatResearchTierCeilingFactor(activeTier)}</strong>
        {" · "}
        project ~{mapping.expected_output_tokens} out tokens (
        {mapping.tier})
      </p>

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
      {/* Residual (afb): weekly best-by-task for this depth (never auto-routes). */}
      <p
        className="text-[10px] font-mono opacity-80"
        data-testid="research-launch-bench-best-by-task"
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
        Antiek-bench best for{" "}
        <strong data-testid="research-launch-bench-task-class">
          {benchTaskClass}
        </strong>
        {bestByTask ? (
          <>
            :{" "}
            <code data-testid="research-launch-bench-best-model">
              {bestByTask.model_id}
            </code>{" "}
            ({bestByTask.score.toFixed(2)})
            {tree?.model_id && bestByTask.model_id === tree.model_id
              ? " · matches installed"
              : tree?.model_id
                ? " · differs from installed (advisory)"
                : " · advisory only"}
          </>
        ) : (
          <>: (no weekly scores for task · run offline dogfood)</>
        )}{" "}
        ·{" "}
        <a
          href="/settings#antiek-bench-leaderboard"
          className="underline opacity-80 hover:opacity-100"
          data-testid="research-launch-bench-leaderboard-link"
          title="Open Settings weekly leaderboard (install best-by-task explicitly)"
        >
          Settings · leaderboard
        </a>
        {bestDiffers ? (
          <>
            {" "}
            ·{" "}
            <button
              type="button"
              data-testid="research-launch-install-best-for-task"
              data-install-model-id={bestByTask?.model_id ?? ""}
              data-install-task-class={benchTaskClass}
              data-advisory-only="true"
              disabled={installBusy}
              onClick={() => void onInstallBestForTask()}
              className="underline opacity-80 hover:opacity-100 disabled:opacity-50 bg-transparent border-0 p-0 cursor-pointer font-mono text-[10px]"
              title={`Install ${bestByTask?.model_id} (best ${benchTaskClass}) as decision-tree driver — explicit · never auto-route`}
            >
              {installBusy
                ? "Installing…"
                : `Install best for ${benchTaskClass}`}
            </button>
          </>
        ) : null}
        {installStatus ? (
          <span
            className="block mt-0.5"
            data-testid="research-launch-install-best-status"
            role="status"
          >
            {installStatus}
          </span>
        ) : null}
      </p>

      {/* Prompt cost projection — residual (hp): machine-readable metrics. */}
      <div data-testid="research-launch-projection" className="space-y-0.5">
        {promptText.trim().length < 3 ? (
          <p className="text-[11px] font-mono text-ink-mute dark:text-moonlight">
            Type ≥3 chars to project this prompt against your cap.
          </p>
        ) : estimate ? (
          <>
            <div
              data-testid="research-launch-projection-metrics"
              data-dispatch-tier={mapping.tier}
              data-research-tier={activeTier}
              data-prompt-chars={String(promptText.trim().length)}
              data-pricing-known={String(Boolean(estimate.pricing_known))}
              data-usd-low={
                estimate.estimated_usd_low != null
                  ? String(estimate.estimated_usd_low)
                  : ""
              }
              data-usd-high={
                estimate.estimated_usd_high != null
                  ? String(estimate.estimated_usd_high)
                  : ""
              }
              data-would-exceed={
                estimate.would_exceed_budget == null
                  ? "unknown"
                  : estimate.would_exceed_budget
                    ? "true"
                    : "false"
              }
              data-remaining-after-usd={
                remainingAfterUsd != null ? String(remainingAfterUsd) : ""
              }
              // Residual (aeb): machine-readable foresight when high band burns past remaining.
              data-goes-negative={
                remainingAfterUsd != null
                  ? String(remainingAfterUsd < 0)
                  : "unknown"
              }
              data-view-format="html"
              role="status"
            >
              Projection metrics · tier={mapping.tier} · chars=
              {promptText.trim().length} · would_exceed=
              {estimate.would_exceed_budget == null
                ? "unknown"
                : String(estimate.would_exceed_budget)}
            </div>
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
            {/* Residual (wa): remaining after high-band prompt (parity badge pg / MO um). */}
            {remainingAfterUsd != null ? (
              <p
                className={
                  "text-[11px] font-mono " +
                  (remainingAfterUsd < 0
                    ? "text-emperor font-semibold"
                    : "text-ink-mute dark:text-moonlight")
                }
                data-testid="research-launch-remaining-after"
                data-remaining-after-usd={String(remainingAfterUsd)}
                // Residual (aeb): soft foresight — negative remaining is machine-readable.
                data-goes-negative={String(remainingAfterUsd < 0)}
                role="status"
              >
                Remaining after prompt ≈ {formatUsd(remainingAfterUsd)}
                {remainingAfterUsd < 0
                  ? " · over remaining high-band (soft foresight · not a hard block)"
                  : ""}
              </p>
            ) : null}
          </>
        ) : (
          <p className="text-[11px] font-mono text-ink-mute">…</p>
        )}
      </div>
    </div>
  );
}

export default ResearchLaunchBudgetPanel;
