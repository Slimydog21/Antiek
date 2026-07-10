/**
 * Residual (avg): pure L4 Midnight Oil live-step dual-gate readiness.
 *
 * Live worker step requires: live_env · injector · offline_honest=false.
 * Offline-honest when any gate is off. Settings never enables live injectors.
 *
 * Parity ave L1/L2 · avf L3 · completes dual-gate pure matrix L1–L4.
 */

export type MoilLiveStepGateReadiness = {
  live_env: boolean;
  injector_installed: boolean;
  server_offline_honest: boolean;
  live_env_flag: string;
  live_ready: boolean;
  offline_honest: boolean;
  never_enables_live: true;
  html_first: true;
  dual_gate: "L4";
  summary: string;
};

/**
 * L4 Midnight Oil live-step readiness from status payload fields.
 * Pure — never mutates injectors · never invents live readiness.
 */
export function moilLiveStepGateReadiness(opts: {
  live_env?: boolean | null;
  injector_installed?: boolean | null;
  offline_honest?: boolean | null;
  live_env_flag?: string | null;
}): MoilLiveStepGateReadiness {
  const live_env = opts.live_env === true;
  const injector_installed = opts.injector_installed === true;
  const server_offline_honest = opts.offline_honest !== false;
  const offline_honest_input =
    opts.offline_honest == null ? true : opts.offline_honest === true;

  const live_ready =
    live_env && injector_installed && offline_honest_input === false;
  const offline_honest = !live_ready;

  const live_env_flag =
    String(opts.live_env_flag || "ANTIEK_MIDNIGHT_OIL_LIVE_STEP").trim() ||
    "ANTIEK_MIDNIGHT_OIL_LIVE_STEP";

  let summary: string;
  if (live_ready) {
    summary =
      "L4 MO live-step ready · env on · injector installed · offline_honest=false";
  } else {
    const missing: string[] = [];
    if (!live_env) missing.push("live_env");
    if (!injector_installed) missing.push("injector");
    if (offline_honest_input) missing.push("still_offline_honest");
    summary = `L4 MO live-step deferred · offline-honest · missing=${missing.join(",") || "unknown"} · never enables live from Settings`;
  }

  return {
    live_env,
    injector_installed,
    server_offline_honest,
    live_env_flag,
    live_ready,
    offline_honest,
    never_enables_live: true,
    html_first: true,
    dual_gate: "L4",
    summary,
  };
}
