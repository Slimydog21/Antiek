/**
 * ModelDecisionTree — the decision-tree TAB (Slice D, G3).
 *
 * The operator's vision (ask #10): "a decision tree tab where the model should be
 * selected." Where `<ModelDecisionBar>` is the compact per-prompt selector, this is
 * the explainable, navigable view of WHY — the ranked candidates organized as a
 * task-anchored tree (task → tier → provider/model · quality basis · cost ·
 * eligibility) so a recommendation is never a black box.
 *
 * Honesty rules (load-bearing — each a test):
 *   * READ-ONLY + advisory. The tree never dispatches and exposes no selection
 *     callback; it only renders the advisory ranking the server already resolved.
 *     Re-rendering a "recommended" node authorizes nothing — the server re-validates
 *     at execution (composer model-decision spec §3 invariant 1).
 *   * quality_basis "measured" vs "static_prior" are distinct visible badges — a
 *     static prior is never mistaken for an Antiek-bench measurement (invariant 4).
 *   * Unknown pricing (`estimated_usd_low/high == null` or `pricing_status ==
 *     "unknown"`) renders "pricing unknown", never a fabricated range or "$0.00"
 *     (invariant 2).
 *   * Ineligible candidates are rendered distinctly, never collapsed with eligible.
 *   * `would_exceed_budget` three-state verdict carried at the task root — true/
 *     false/null never collapse (invariant 3).
 */

import { useMemo, useState } from "react";
import { type ComposerModelProjection } from "../api/composerProjection";

export interface ModelDecisionTreeProps {
  projection: ComposerModelProjection | null;
  loading?: boolean;
  error?: string | null;
}

function formatUsd(value: number): string {
  return `$${value.toFixed(2)}`;
}

type Tone = "ok" | "over" | "unknown" | "prior";

function qualityBadge(basis: string): { label: string; tone: Tone } {
  return basis === "measured"
    ? { label: "measured", tone: "ok" }
    : { label: "prior", tone: "prior" };
}

function pricingText(
  status: string,
  low: number | null,
  high: number | null,
): string {
  if (status === "unknown" || low == null || high == null) {
    return "pricing unknown";
  }
  return `${formatUsd(low)}–${formatUsd(high)}`;
}

function exceedVerdict(
  wouldExceed: boolean | null,
): { text: string; tone: Tone } {
  if (wouldExceed === true) {
    return { text: "over budget — would exceed the ceiling", tone: "over" };
  }
  if (wouldExceed === false) {
    return { text: "within the ceiling (server re-validates)", tone: "ok" };
  }
  return { text: "budget or projection unmeasurable", tone: "unknown" };
}

const TONE_CLASS: Record<Tone, string> = {
  ok: "text-aurora",
  over: "text-danger",
  unknown: "text-shadow-1 dark:text-moonlight",
  prior: "text-shadow-1 dark:text-moonlight",
};

export default function ModelDecisionTree({
  projection,
  loading = false,
  error = null,
}: ModelDecisionTreeProps) {
  // Tiers collapsed by the operator. Default: every tier expanded so the ranked
  // candidates are visible (the point of an explainable tree).
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());

  const tiers = useMemo(() => {
    if (!projection) return [];
    // Candidates arrive rank-sorted; group by tier preserving that order.
    const byTier = new Map<string, typeof projection.ranked_candidates>();
    for (const candidate of projection.ranked_candidates) {
      const bucket = byTier.get(candidate.tier);
      if (bucket) {
        bucket.push(candidate);
      } else {
        byTier.set(candidate.tier, [candidate]);
      }
    }
    return Array.from(byTier.entries());
  }, [projection]);

  const verdict = projection ? exceedVerdict(projection.would_exceed_budget) : null;

  if (loading) {
    return (
      <div
        data-testid="model-decision-tree-loading"
        className="text-xs text-shadow-1 dark:text-moonlight"
      >
        resolving model decision tree…
      </div>
    );
  }
  if (error) {
    return (
      <div
        data-testid="model-decision-tree-error"
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

  function toggleTier(tier: string): void {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(tier)) {
        next.delete(tier);
      } else {
        next.add(tier);
      }
      return next;
    });
  }

  return (
    <div
      data-testid="model-decision-tree"
      className="flex flex-col gap-2 rounded-lg border border-border p-3"
      aria-label="model decision tree"
      role="tree"
    >
      {/* Task root — anchors every candidate to the decision context. */}
      <div
        data-testid="decision-tree-task"
        className="flex flex-wrap items-center gap-2 border-b border-border pb-2"
        role="treeitem"
        aria-level={1}
      >
        <span className="text-[11px] uppercase tracking-[0.14em] text-shadow-1 dark:text-moonlight">
          task
        </span>
        <span className="font-mono text-sm text-ink dark:text-bright">
          {projection.task}
        </span>
        {projection.recommended_tier && (
          <span className="text-[11px] text-shadow-1 dark:text-moonlight">
            · recommended tier{" "}
            <span className="font-mono text-ink dark:text-bright">
              {projection.recommended_tier}
            </span>
          </span>
        )}
        {verdict && (
          <span
            data-testid="decision-tree-verdict"
            className={`text-[11px] ${TONE_CLASS[verdict.tone]}`}
          >
            · {verdict.text}
          </span>
        )}
      </div>

      {tiers.map(([tier, candidates]) => {
        const isCollapsed = collapsed.has(tier);
        return (
          <div
            key={tier}
            data-testid={`decision-tree-tier-${tier}`}
            role="treeitem"
            aria-level={2}
            aria-expanded={!isCollapsed}
            className="flex flex-col gap-1"
          >
            <button
              type="button"
              data-testid={`decision-tree-tier-${tier}-toggle`}
              onClick={() => toggleTier(tier)}
              className="flex items-center gap-2 text-left"
              aria-expanded={!isCollapsed}
              aria-controls={`decision-tree-tier-${tier}-group`}
            >
              <span className="text-shadow-1 dark:text-moonlight">
                {isCollapsed ? "▸" : "▾"}
              </span>
              <span className="text-[11px] uppercase tracking-[0.14em] text-shadow-1 dark:text-moonlight">
                tier
              </span>
              <span className="font-mono text-sm text-ink dark:text-bright">
                {tier}
              </span>
              <span className="text-[11px] text-shadow-1 dark:text-moonlight">
                ({candidates.length})
              </span>
            </button>

            {!isCollapsed && (
              <ul
                id={`decision-tree-tier-${tier}-group`}
                role="group"
                className="ml-4 flex flex-col gap-1 border-l border-border pl-3"
              >
                {candidates.map((candidate) => {
                  const quality = qualityBadge(candidate.quality_basis);
                  const pricing = pricingText(
                    candidate.pricing_status,
                    candidate.estimated_usd_low,
                    candidate.estimated_usd_high,
                  );
                  return (
                    <li
                      key={`${candidate.provider}::${candidate.model}`}
                      data-testid={`decision-tree-candidate-${candidate.rank}`}
                      role="treeitem"
                      aria-level={3}
                      className="flex flex-wrap items-center gap-2 text-xs"
                    >
                      <span className="font-mono w-6 text-shadow-1 dark:text-moonlight">
                        #{candidate.rank}
                      </span>
                      <span className="text-ink dark:text-bright">
                        {candidate.provider}/{candidate.model}
                      </span>
                      <span
                        data-testid={`candidate-${candidate.rank}-quality`}
                        className={`text-[11px] ${TONE_CLASS[quality.tone]}`}
                      >
                        {candidate.quality_score.toFixed(2)} · {quality.label}
                      </span>
                      <span
                        data-testid={`candidate-${candidate.rank}-pricing`}
                        className="text-[11px] text-shadow-1 dark:text-moonlight"
                      >
                        {pricing}
                      </span>
                      <span
                        data-testid={`candidate-${candidate.rank}-eligibility`}
                        className={`text-[11px] ${
                          candidate.eligible ? "text-aurora" : "text-danger line-through"
                        }`}
                      >
                        {candidate.eligible ? "eligible" : "ineligible"}
                      </span>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        );
      })}
    </div>
  );
}
