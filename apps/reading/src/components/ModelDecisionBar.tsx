/**
 * ModelDecisionBar — the per-prompt model decision + budget projection surface.
 *
 * The operator's vision (asks #8/#10): pick the AI model FOR THIS PROMPT, see a
 * budget bar (spent/cap), and a projection of how the proposed prompt affects the
 * limit. This component renders the ComposerModelProjection from
 * fetchComposerProjection (#2058 Slice B route / #2057 Slice A resolver).
 *
 * Honesty rules (load-bearing — each a test):
 *   * Unknown pricing renders "unknown", never "$0.00".
 *   * would_exceed_budget null (unmeasurable) is distinct from false (within) and
 *     true (over) — never collapses the three states.
 *   * quality_basis measured vs static_prior is a visible badge — a prior is never
 *     mistaken for a measurement.
 *   * Budget bar only renders when cap+spent are both present; null on either → an
 *     honest "budget unknown" label, never a fabricated 0%.
 *   * Pure + advisory: the bar never dispatches; onSelect reports the choice up.
 */

import { type ChangeEvent, useMemo } from "react";
import {
  type ComposerCandidateView,
  type ComposerModelProjection,
} from "../api/composerProjection";

export interface ModelDecisionBarProps {
  projection: ComposerModelProjection | null;
  loading?: boolean;
  error?: string | null;
  /** Called when the operator picks a candidate (advisory; the parent submits). */
  onSelect?: (provider: string, model: string) => void;
  /** The currently selected provider+model, if any (curated default when null). */
  selected?: { provider: string; model: string } | null;
}

function formatUsd(value: number): string {
  return `$${value.toFixed(2)}`;
}

function pricingLabel(c: ComposerCandidateView): string {
  if (c.pricing_status === "unknown" || c.estimated_usd_low == null || c.estimated_usd_high == null) {
    return "pricing unknown";
  }
  return `${formatUsd(c.estimated_usd_low)}–${formatUsd(c.estimated_usd_high)}`;
}

function budgetPercent(projection: ComposerModelProjection): number | null {
  const { daily_cap_usd: cap, spent_usd: spent } = projection.budget;
  if (cap == null || spent == null || cap <= 0) {
    return null;
  }
  return Math.min(100, (spent / cap) * 100);
}

function projectionSummary(projection: ComposerModelProjection): string {
  const cp = projection.chosen_projection;
  if (cp == null) {
    return "no projection for the chosen model";
  }
  return `${formatUsd(cp.maximum_cost_usd)} projected`;
}

function exceedLabel(projection: ComposerModelProjection): {
  text: string;
  tone: "ok" | "over" | "unknown";
} {
  const verdict = projection.would_exceed_budget;
  if (verdict === true) {
    return { text: "over budget — would exceed the ceiling", tone: "over" };
  }
  if (verdict === false) {
    return { text: "within the ceiling (server re-validates)", tone: "ok" };
  }
  return { text: "budget or projection unmeasurable", tone: "unknown" };
}

export default function ModelDecisionBar({
  projection,
  loading = false,
  error = null,
  onSelect,
  selected = null,
}: ModelDecisionBarProps) {
  const budgetPct = useMemo(
    () => (projection ? budgetPercent(projection) : null),
    [projection],
  );
  const exceed = useMemo(
    () => (projection ? exceedLabel(projection) : null),
    [projection],
  );

  if (loading) {
    return (
      <div
        data-testid="model-decision-bar-loading"
        className="text-xs text-shadow-1 dark:text-moonlight"
      >
        resolving model projection…
      </div>
    );
  }
  if (error) {
    return (
      <div
        data-testid="model-decision-bar-error"
        className="text-xs text-danger"
        role="alert"
      >
        {error}
      </div>
    );
  }
  if (!projection) {
    return null;
  }

  const options = projection.ranked_candidates.map((c) => ({
    value: `${c.provider}::${c.model}`,
    label: `${c.tier} · ${c.provider}/${c.model} · ${pricingLabel(c)} · ${
      c.quality_basis === "measured" ? "measured" : "prior"
    }${c.eligible ? "" : " · ineligible"}`,
  }));
  const selectedValue = selected
    ? `${selected.provider}::${selected.model}`
    : projection.chosen_provider && projection.chosen_model
      ? `${projection.chosen_provider}::${projection.chosen_model}`
      : "";

  return (
    <div
      data-testid="model-decision-bar"
      className="flex flex-col gap-2 rounded-lg border border-border p-3"
      aria-label="per-prompt model decision"
    >
      <div className="flex items-center gap-2">
        <span className="text-[11px] uppercase tracking-[0.14em] text-shadow-1 dark:text-moonlight">
          model
        </span>
        <select
          value={selectedValue}
          onChange={(e: ChangeEvent<HTMLSelectElement>) => {
            const [provider, model] = e.target.value.split("::");
            if (provider && model && onSelect) {
              onSelect(provider, model);
            }
          }}
          data-testid="model-decision-select"
          aria-label="model choice"
          className="rounded border border-border bg-surface px-2 py-1 text-sm text-ink dark:text-bright"
        >
          {options.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>

      {projection.pricing_status === "unknown" && (
        <span
          data-testid="pricing-unknown"
          className="text-[11px] text-sun"
          role="status"
        >
          pricing unknown for the chosen model
        </span>
      )}

      <div
        data-testid="budget-bar"
        className="flex flex-col gap-1"
        aria-label="budget bar"
      >
        <div className="flex items-baseline justify-between gap-3">
          <span className="text-[11px] uppercase tracking-[0.14em] text-shadow-1 dark:text-moonlight">
            budget
          </span>
          {budgetPct == null ? (
            <span className="text-xs text-shadow-1 dark:text-moonlight">
              budget unknown
            </span>
          ) : (
            <span className="font-mono text-sm text-ink dark:text-bright">
              {projection.budget.spent_usd != null
                ? formatUsd(projection.budget.spent_usd)
                : "?"}
              <span className="text-shadow-1 dark:text-moonlight">
                {" / "}
                {projection.budget.daily_cap_usd != null
                  ? formatUsd(projection.budget.daily_cap_usd)
                  : "?"}
              </span>
            </span>
          )}
        </div>
        {budgetPct != null && (
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-ice-3 dark:bg-charcoal-1">
            <div
              data-testid="budget-bar-fill"
              className={`h-full transition-[width] duration-300 ${
                budgetPct >= 100 ? "bg-emperor" : budgetPct >= 80 ? "bg-sun" : "bg-aurora"
              }`}
              style={{ width: `${budgetPct.toFixed(1)}%` }}
            />
          </div>
        )}
      </div>

      <div className="flex items-center gap-2 text-xs">
        <span data-testid="projection-summary" className="text-ink dark:text-bright">
          {projectionSummary(projection)}
        </span>
        {exceed && (
          <span
            data-testid="exceed-verdict"
            className={
              exceed.tone === "over"
                ? "text-danger"
                : exceed.tone === "unknown"
                  ? "text-shadow-1 dark:text-moonlight"
                  : "text-aurora"
            }
          >
            · {exceed.text}
          </span>
        )}
      </div>

      {projection.notes.length > 0 && (
        <ul
          data-testid="projection-notes"
          className="text-[11px] text-shadow-1 dark:text-moonlight"
        >
          {projection.notes.slice(0, 2).map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
