/**
 * Residual (avc): pure Settings depth-tier Apply CTA readiness.
 *
 * Depth tiers prefill research intensity (input/output projection hints) and
 * may install driver when model selected. Apply requires non-empty depth_tier.
 * Never auto-routes dispatch — install_driver is opt-in when model_id present.
 *
 * Outside pure install thrash (aut–auy) · week-gate thrash (ava–avb).
 */

export type DepthTierApplyBlockReason = "ok" | "no_tier";

export type DepthTierApplyReadiness = {
  has_depth_tier: boolean;
  depth_tier: string;
  has_model_id: boolean;
  model_id: string;
  provider_id: string;
  will_install_driver: boolean;
  apply_ready: boolean;
  block_reason: DepthTierApplyBlockReason;
  never_auto_route: true;
  html_first: true;
  summary: string;
  apply_title: string;
};

/**
 * Depth-tier apply CTA readiness.
 * apply_ready when depth_tier is non-empty after trim.
 */
export function depthTierApplyReadiness(opts: {
  depth_tier?: string | null;
  model_id?: string | null;
  provider_id?: string | null;
}): DepthTierApplyReadiness {
  const depth_tier = String(opts.depth_tier || "").trim();
  const model_id = String(opts.model_id || "").trim();
  const provider_id = String(opts.provider_id || "").trim();
  const has_depth_tier = Boolean(depth_tier);
  const has_model_id = Boolean(model_id);
  const will_install_driver = has_model_id;
  const apply_ready = has_depth_tier;
  const block_reason: DepthTierApplyBlockReason = apply_ready
    ? "ok"
    : "no_tier";

  let summary: string;
  let apply_title: string;
  if (apply_ready) {
    summary = will_install_driver
      ? `apply ready · tier=${depth_tier} · will install driver ${provider_id ? `${provider_id}/` : ""}${model_id} (explicit · never auto-route)`
      : `apply ready · tier=${depth_tier} · projection hints only (no driver install)`;
    apply_title = will_install_driver
      ? `Apply depth tier ${depth_tier} and install selected model as decision-tree driver (manual · never auto-route)`
      : `Apply depth tier ${depth_tier} (projection hints · HTML · never auto-route)`;
  } else {
    summary = "depth tier empty · select a tier to apply";
    apply_title = "Select a depth tier before applying";
  }

  return {
    has_depth_tier,
    depth_tier,
    has_model_id,
    model_id,
    provider_id,
    will_install_driver,
    apply_ready,
    block_reason,
    never_auto_route: true,
    html_first: true,
    summary,
    apply_title,
  };
}
