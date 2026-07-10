/**
 * Residual (aut): pure NotDiamond advisory-install CTA readiness.
 *
 * Installs the weekly advisory pick into the decision-tree only.
 * Never grants NotDiamond dispatch authority (L7 · advisory forever).
 * Requires non-empty suggested_model_id and notdiamond_is_dispatch_authority
 * must be false. installable defaults true when unset.
 *
 * Parity aun decisionTreeInstallReadiness · never invents model id.
 */

export type NotDiamondAdvisoryInstallBlockReason =
  | "ok"
  | "no_suggestion"
  | "dispatch_authority_refused"
  | "not_installable";

export type NotDiamondAdvisoryInstallReadiness = {
  has_suggested_model: boolean;
  has_suggested_provider: boolean;
  suggested_model_id: string;
  suggested_provider_id: string;
  /** Server flag — if true, install_ready is always false. */
  notdiamond_is_dispatch_authority: boolean;
  /** When false, install_ready is false. Undefined/null → treat as installable. */
  installable: boolean;
  install_ready: boolean;
  block_reason: NotDiamondAdvisoryInstallBlockReason;
  /** Doctrine constants — hard to vary. */
  never_auto_route: true;
  notdiamond_authority: "advisory_only";
  install_is_decision_tree_only: true;
  never_dispatch_authority: true;
  summary: string;
  install_title: string;
};

/**
 * NotDiamond "Install advisory pick as decision-tree driver" CTA readiness.
 * install_ready only when suggestion present, not dispatch authority, and installable.
 */
export function notDiamondAdvisoryInstallReadiness(opts: {
  suggested_model_id?: string | null;
  suggested_provider_id?: string | null;
  notdiamond_is_dispatch_authority?: boolean | null;
  installable?: boolean | null;
}): NotDiamondAdvisoryInstallReadiness {
  const suggested_model_id = String(opts.suggested_model_id || "").trim();
  const suggested_provider_id = String(opts.suggested_provider_id || "").trim();
  const has_suggested_model = Boolean(suggested_model_id);
  const has_suggested_provider = Boolean(suggested_provider_id);
  const notdiamond_is_dispatch_authority =
    opts.notdiamond_is_dispatch_authority === true;
  // installable defaults true when unset (server may omit the field).
  const installable = opts.installable !== false;

  let block_reason: NotDiamondAdvisoryInstallBlockReason = "ok";
  if (notdiamond_is_dispatch_authority) {
    block_reason = "dispatch_authority_refused";
  } else if (!has_suggested_model) {
    block_reason = "no_suggestion";
  } else if (!installable) {
    block_reason = "not_installable";
  }

  const install_ready = block_reason === "ok";

  let summary: string;
  let install_title: string;
  if (install_ready) {
    summary = has_suggested_provider
      ? `install ready · advisory ${suggested_provider_id}/${suggested_model_id} → decision-tree only`
      : `install ready · advisory model=${suggested_model_id} → decision-tree only`;
    install_title =
      "Install suggested model into decision-tree only — NotDiamond is never dispatch authority";
  } else if (block_reason === "dispatch_authority_refused") {
    summary =
      "refused · NotDiamond reported dispatch authority (L7 never router)";
    install_title =
      "Refusing install: NotDiamond must never be dispatch authority";
  } else if (block_reason === "no_suggestion") {
    summary = "no advisory suggestion · refresh weekly advisory first";
    install_title = "No advisory suggestion to install";
  } else {
    summary = "not installable · advisory marked non-installable this week";
    install_title = "Advisory pick not installable this week";
  }

  return {
    has_suggested_model,
    has_suggested_provider,
    suggested_model_id,
    suggested_provider_id,
    notdiamond_is_dispatch_authority,
    installable,
    install_ready,
    block_reason,
    never_auto_route: true,
    notdiamond_authority: "advisory_only",
    install_is_decision_tree_only: true,
    never_dispatch_authority: true,
    summary,
    install_title,
  };
}
