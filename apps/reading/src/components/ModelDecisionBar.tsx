/**
 * ModelDecisionBar — the per-prompt model decision + budget projection surface.
 *
 * The operator's vision (asks #8/#10): pick the AI model FOR THIS PROMPT, see a
 * budget bar (spent/cap), and a projection of how the proposed prompt affects the
 * limit. This component renders the ComposerModelProjection from
 * fetchComposerProjection (PR 2058 Slice B route / PR 2057 Slice A resolver).
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
  type ComposerFallbackRouteProjection,
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
  if (!Number.isFinite(value) || value < 0) {
    return "unknown";
  }
  return `$${value.toFixed(2)}`;
}

function formatReservationCents(value: number): string | null {
  if (!Number.isSafeInteger(value) || value < 0) {
    return null;
  }
  return `$${(value / 100).toFixed(2)}`;
}

function pricingLabel(c: ComposerCandidateView): string {
  if (
    c.pricing_status === "unknown" ||
    c.estimated_usd_low == null ||
    c.estimated_usd_high == null ||
    !Number.isFinite(c.estimated_usd_low) ||
    !Number.isFinite(c.estimated_usd_high) ||
    c.estimated_usd_low < 0 ||
    c.estimated_usd_high < c.estimated_usd_low
  ) {
    return "pricing unknown";
  }
  return `${formatUsd(c.estimated_usd_low)}–${formatUsd(c.estimated_usd_high)}`;
}

function budgetPercent(projection: ComposerModelProjection): number | null {
  const { daily_cap_usd: cap, spent_usd: spent } = projection.budget;
  if (
    cap == null ||
    spent == null ||
    !Number.isFinite(cap) ||
    !Number.isFinite(spent) ||
    cap <= 0 ||
    spent < 0
  ) {
    return null;
  }
  return Math.min(100, (spent / cap) * 100);
}

function projectionSummary(projection: ComposerModelProjection): string {
  const cp = projection.chosen_projection;
  if (cp == null) {
    return "no projection for the chosen model";
  }
  if (cp.disposition === "ineligible") {
    return "projection ineligible";
  }
  if (cp.disposition === "zero_cost_receipt") {
    return "zero-cost route";
  }
  const reservation = formatReservationCents(cp.reservation_cents);
  if (reservation == null) {
    return "projection unavailable";
  }
  return `${reservation} maximum reservation`;
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

function fallbackProjectionLabel(
  projection: ComposerFallbackRouteProjection,
): string {
  if (projection.disposition === "ineligible") {
    return projection.ineligibility?.replaceAll("_", " ") ?? "ineligible";
  }
  if (projection.disposition === "zero_cost_receipt") return "zero-cost route";
  return (
    formatReservationCents(projection.reservation_cents) ?? "cost unavailable"
  );
}

function executionLabel(value: string): string {
  return value.replace(/^blocked_/, "blocked: ").replaceAll("_", " ");
}

function fallbackExposureLabel(projection: ComposerModelProjection): string {
  const plan = projection.fallback_plan;
  if (plan == null || plan.maximum_chain_exposure_cents == null) {
    return "execution blocked";
  }
  const exposure = formatReservationCents(plan.maximum_chain_exposure_cents);
  if (exposure == null) return "exposure unavailable";
  const budget =
    plan.would_exceed_budget === true
      ? "over budget"
      : plan.would_exceed_budget === false
        ? "within budget"
        : "budget unknown";
  return `${exposure} peak · ${budget}`;
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

  const options = projection.ranked_candidates.map((c, index) => ({
    value: String(index),
    candidate: c,
    label: `${c.tier} · ${c.provider}/${c.model} · ${pricingLabel(c)} · ${
      c.quality_basis === "measured" ? "measured" : "prior"
    }${c.eligible ? "" : " · ineligible"}`,
  }));
  const selectedChoice =
    selected ??
    (projection.chosen_provider && projection.chosen_model
      ? { provider: projection.chosen_provider, model: projection.chosen_model }
      : null);
  const selectedIndex =
    selectedChoice == null
      ? -1
      : projection.ranked_candidates.findIndex(
          (candidate) =>
            candidate.provider === selectedChoice.provider &&
            candidate.model === selectedChoice.model,
        );
  const selectedValue = selectedIndex >= 0 ? String(selectedIndex) : "";

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
            const index = Number(e.target.value);
            const candidate = Number.isSafeInteger(index)
              ? projection.ranked_candidates[index]
              : undefined;
            if (candidate?.eligible && onSelect) {
              onSelect(candidate.provider, candidate.model);
            }
          }}
          data-testid="model-decision-select"
          aria-label="model choice"
          className="rounded border border-border bg-surface px-2 py-1 text-sm text-ink dark:text-bright"
        >
          {selectedValue === "" && <option value="">choose a model</option>}
          {options.map((opt) => (
            <option
              key={JSON.stringify([
                opt.candidate.provider,
                opt.candidate.model,
              ])}
              value={opt.value}
              disabled={!opt.candidate.eligible}
            >
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
                budgetPct >= 100
                  ? "bg-emperor"
                  : budgetPct >= 80
                    ? "bg-sun"
                    : "bg-aurora"
              }`}
              style={{ width: `${budgetPct.toFixed(1)}%` }}
            />
          </div>
        )}
      </div>

      <div className="flex items-center gap-2 text-xs">
        <span
          data-testid="projection-summary"
          className="text-ink dark:text-bright"
        >
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

      {projection.fallback_plan && (
        <div
          data-testid="fallback-plan"
          className="border-t border-border pt-2"
          aria-label="fallback plan"
        >
          <div className="mb-1 flex items-baseline justify-between gap-3">
            <span className="text-[11px] uppercase tracking-[0.14em] text-shadow-1 dark:text-moonlight">
              fallback plan
            </span>
            <span
              data-testid="fallback-plan-exposure"
              className={`font-mono text-xs ${
                projection.fallback_plan.would_exceed_budget === true
                  ? "text-danger"
                  : "text-ink dark:text-bright"
              }`}
            >
              {fallbackExposureLabel(projection)}
            </span>
          </div>
          <ol className="divide-y divide-border">
            {projection.fallback_plan.routes.map((route) => (
              <li
                key={JSON.stringify([route.provider, route.model])}
                data-testid={`fallback-route-${route.fallback_index}`}
                className="grid grid-cols-[minmax(0,1fr)_auto] gap-x-3 py-2 text-xs"
              >
                <span className="min-w-0 text-ink dark:text-bright">
                  <span className="mr-2 font-mono text-shadow-1 dark:text-moonlight">
                    {route.fallback_index === 0
                      ? "Primary"
                      : `Fallback ${route.fallback_index}`}
                  </span>
                  {route.provider}/{route.model}
                </span>
                <span className="font-mono text-ink dark:text-bright">
                  {fallbackProjectionLabel(route.projection)}
                </span>
                <span className="col-span-2 mt-0.5 text-[11px] text-shadow-1 dark:text-moonlight">
                  {route.registered ? "registered" : "not registered"} ·{" "}
                  {executionLabel(route.execution_status)}
                </span>
              </li>
            ))}
          </ol>
        </div>
      )}

      {projection.notes.length > 0 && (
        <ul
          data-testid="projection-notes"
          className="text-[11px] text-shadow-1 dark:text-moonlight"
        >
          {projection.notes.slice(0, 2).map((note, index) => (
            <li key={`${index}:${note}`}>{note}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
