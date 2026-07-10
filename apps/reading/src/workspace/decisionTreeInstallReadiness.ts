/**
 * Residual (aun): pure decision-tree Install driver CTA readiness.
 *
 * Manual model choice for any prompt — never auto-route · NotDiamond advisory
 * only (L7 never router). Install requires non-empty model id; provider is
 * optional identity chrome (server may resolve).
 *
 * Parity asd install gate · never invents model id.
 */

export type DecisionTreeInstallReadiness = {
  has_model_id: boolean;
  has_provider_id: boolean;
  model_id: string;
  provider_id: string;
  install_ready: boolean;
  never_auto_route: true;
  notdiamond_authority: "advisory_only";
  summary: string;
  install_title: string;
};

/**
 * Install driver CTA readiness from form fields.
 * install_ready only when model_id is non-empty after trim.
 */
export function decisionTreeInstallReadiness(opts: {
  model_id?: string | null;
  provider_id?: string | null;
}): DecisionTreeInstallReadiness {
  const model_id = String(opts.model_id || "").trim();
  const provider_id = String(opts.provider_id || "").trim();
  const has_model_id = Boolean(model_id);
  const has_provider_id = Boolean(provider_id);
  const install_ready = has_model_id;

  let summary: string;
  let install_title: string;
  if (install_ready) {
    summary = has_provider_id
      ? `install ready · ${provider_id}/${model_id}`
      : `install ready · model=${model_id}`;
    install_title =
      "Install process-local decision-tree driver (manual · never auto-route · ND advisory only)";
  } else {
    summary = "model id empty · enter model before install";
    install_title =
      "Enter a model id before installing the decision-tree driver";
  }

  return {
    has_model_id,
    has_provider_id,
    model_id,
    provider_id,
    install_ready,
    never_auto_route: true,
    notdiamond_authority: "advisory_only",
    summary,
    install_title,
  };
}
