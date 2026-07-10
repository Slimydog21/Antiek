/**
 * Residual (auv): pure Settings Add-model Register CTA readiness.
 *
 * Operator can add models in settings for any prompt path. Both model_id and
 * provider_id required (register identity). Optional select-as-driver never
 * auto-routes — only installs decision-tree when operator checks the box.
 *
 * Parity aun decisionTreeInstall · aut ND install · auu leaderboard install.
 * Soft budget foresight remains separate (auc usage bar).
 */

export type RegisterModelBlockReason =
  | "ok"
  | "no_model"
  | "no_provider"
  | "missing_both";

export type RegisterModelReadiness = {
  has_model_id: boolean;
  has_provider_id: boolean;
  model_id: string;
  provider_id: string;
  /** Operator-checked: install as decision-tree after register (never auto). */
  select_as_driver: boolean;
  register_ready: boolean;
  block_reason: RegisterModelBlockReason;
  never_auto_route: true;
  install_is_decision_tree_only: true;
  summary: string;
  register_title: string;
};

/**
 * Register model CTA readiness from Add model form fields.
 * register_ready only when both model_id and provider_id are non-empty.
 */
export function registerModelReadiness(opts: {
  model_id?: string | null;
  provider_id?: string | null;
  select_as_driver?: boolean | null;
}): RegisterModelReadiness {
  const model_id = String(opts.model_id || "").trim();
  const provider_id = String(opts.provider_id || "").trim();
  const has_model_id = Boolean(model_id);
  const has_provider_id = Boolean(provider_id);
  const select_as_driver = opts.select_as_driver === true;

  let block_reason: RegisterModelBlockReason = "ok";
  if (!has_model_id && !has_provider_id) {
    block_reason = "missing_both";
  } else if (!has_model_id) {
    block_reason = "no_model";
  } else if (!has_provider_id) {
    block_reason = "no_provider";
  }

  const register_ready = block_reason === "ok";

  let summary: string;
  let register_title: string;
  if (register_ready) {
    summary = select_as_driver
      ? `register ready · ${provider_id}/${model_id} · will install as decision-tree driver (explicit · never auto-route)`
      : `register ready · ${provider_id}/${model_id} · registry only (no driver install)`;
    register_title = select_as_driver
      ? `Register ${provider_id}/${model_id} and install as decision-tree driver (manual · never auto-route)`
      : `Register ${provider_id}/${model_id} into process-local model registry`;
  } else if (block_reason === "missing_both") {
    summary = "model id and provider id empty · enter both before register";
    register_title = "Enter model id and provider id before registering";
  } else if (block_reason === "no_model") {
    summary = "model id empty · enter model before register";
    register_title = "Enter a model id before registering";
  } else {
    summary = "provider id empty · enter provider before register";
    register_title = "Enter a provider id before registering";
  }

  return {
    has_model_id,
    has_provider_id,
    model_id,
    provider_id,
    select_as_driver,
    register_ready,
    block_reason,
    never_auto_route: true,
    install_is_decision_tree_only: true,
    summary,
    register_title,
  };
}
