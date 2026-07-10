/**
 * Residual (auq): pure twin multi-select chase CTA readiness.
 *
 * Recursive note-taker: chase selected insights/questions as floating|full
 * deep research. Requires ≥1 selected note. Soft budget-before-fire:
 * would_exceed blocks unless force_over_budget (parity marketplace/collective).
 *
 * Never invents selection · never auto-fires over budget · HTML-first DR.
 */

export type TwinChaseSelectionReadiness = {
  selected_count: number;
  has_selection: boolean;
  budget_would_exceed: boolean;
  force_over_budget: boolean;
  /** Soft budget soft-gate active (would exceed and not forced). */
  budget_blocks: boolean;
  /** True when Chase selected float|full should be enabled (ignoring busy). */
  chase_ready: boolean;
  html_first: true;
  never_pdf_view: true;
  summary: string;
  chase_title: string;
};

/**
 * Chase selected twin notes CTA readiness.
 * selected_count < 1 → not ready; budget would exceed without force → blocked.
 */
export function twinChaseSelectionReadiness(opts: {
  selected_count?: number | null;
  budget_would_exceed?: boolean | null;
  force_over_budget?: boolean | null;
}): TwinChaseSelectionReadiness {
  const selected_count =
    typeof opts.selected_count === "number" &&
    Number.isFinite(opts.selected_count) &&
    opts.selected_count > 0
      ? Math.floor(opts.selected_count)
      : 0;
  const has_selection = selected_count >= 1;
  const budget_would_exceed = Boolean(opts.budget_would_exceed);
  const force_over_budget = Boolean(opts.force_over_budget);
  const budget_blocks = budget_would_exceed && !force_over_budget;
  const chase_ready = has_selection && !budget_blocks;

  let summary: string;
  let chase_title: string;
  if (!has_selection) {
    summary = "no twin notes selected · multi-select to chase";
    chase_title =
      "Select twin notes (insights/questions) before chase as deep research";
  } else if (budget_blocks) {
    summary = `${selected_count} selected · budget may exceed · force or lower tier`;
    chase_title =
      "Chase budget soft-gate: projection may exceed remaining daily budget — enable force override or lower depth";
  } else if (budget_would_exceed && force_over_budget) {
    summary = `${selected_count} selected · force chase despite budget projection`;
    chase_title = `Chase ${selected_count} selected twin notes as HTML deep research (forced over soft budget · never PDF)`;
  } else {
    summary = `${selected_count} selected · chase float|full ready`;
    chase_title = `Chase ${selected_count} selected twin notes as HTML deep research (recursive note-taker · never PDF)`;
  }

  return {
    selected_count,
    has_selection,
    budget_would_exceed,
    force_over_budget,
    budget_blocks,
    chase_ready,
    html_first: true,
    never_pdf_view: true,
    summary,
    chase_title,
  };
}
