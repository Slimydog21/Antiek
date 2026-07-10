/**
 * Residual (auw): pure decision-tree Clear CTA readiness.
 *
 * Clear is only meaningful when a process-local driver is installed.
 * Clearing does not auto-route; it restores empty selection so the next
 * prompt requires explicit Install (manual / ND advisory / bench advisory).
 *
 * Parity aun install · aut ND · auu leaderboard · auv register.
 */

export type ClearDecisionTreeBlockReason = "ok" | "not_installed";

export type ClearDecisionTreeReadiness = {
  is_installed: boolean;
  model_id: string;
  provider_id: string;
  clear_ready: boolean;
  block_reason: ClearDecisionTreeBlockReason;
  never_auto_route: true;
  notdiamond_authority: "advisory_only";
  summary: string;
  clear_title: string;
};

/**
 * Clear driver CTA readiness from decision-tree selection state.
 * clear_ready only when installed (installed flag or non-empty model_id).
 */
export function clearDecisionTreeReadiness(opts: {
  installed?: boolean | null;
  model_id?: string | null;
  provider_id?: string | null;
}): ClearDecisionTreeReadiness {
  const model_id = String(opts.model_id || "").trim();
  const provider_id = String(opts.provider_id || "").trim();
  const is_installed = opts.installed === true || Boolean(model_id);
  const clear_ready = is_installed;
  const block_reason: ClearDecisionTreeBlockReason = clear_ready
    ? "ok"
    : "not_installed";

  let summary: string;
  let clear_title: string;
  if (clear_ready) {
    summary = provider_id
      ? `clear ready · remove ${provider_id}/${model_id} from decision-tree (explicit · never auto-route)`
      : model_id
        ? `clear ready · remove model=${model_id} from decision-tree (explicit · never auto-route)`
        : "clear ready · remove installed decision-tree driver (explicit · never auto-route)";
    clear_title =
      "Clear process-local decision-tree driver (manual · never auto-route · ND advisory only)";
  } else {
    summary = "no driver installed · nothing to clear";
    clear_title = "No decision-tree driver installed to clear";
  }

  return {
    is_installed,
    model_id,
    provider_id,
    clear_ready,
    block_reason,
    never_auto_route: true,
    notdiamond_authority: "advisory_only",
    summary,
    clear_title,
  };
}
