/**
 * Residual (avf): pure L3 twin-seed dual-gate readiness.
 *
 * Live note_taker twin seed requires: live_env · use_dispatch · injector ·
 * offline_honest=false. Offline-honest when any gate is off. Settings never
 * enables live injectors (operator dual-gate only).
 *
 * Parity ave hydrateLiveGateReadiness (L1/L2).
 */

export type TwinSeedLiveGateReadiness = {
  live_env: boolean;
  use_dispatch: boolean;
  injector_installed: boolean;
  server_offline_honest: boolean;
  live_env_flag: string;
  use_dispatch_env_flag: string;
  /** True only when all L3 gates clear. */
  live_ready: boolean;
  offline_honest: boolean;
  never_enables_live: true;
  html_first: true;
  dual_gate: "L3";
  summary: string;
};

/**
 * L3 twin-seed live readiness from status payload fields.
 * Pure — never mutates injectors · never invents live readiness.
 */
export function twinSeedLiveGateReadiness(opts: {
  live_env?: boolean | null;
  use_dispatch?: boolean | null;
  injector_installed?: boolean | null;
  offline_honest?: boolean | null;
  live_env_flag?: string | null;
  use_dispatch_env_flag?: string | null;
}): TwinSeedLiveGateReadiness {
  const live_env = opts.live_env === true;
  const use_dispatch = opts.use_dispatch === true;
  const injector_installed = opts.injector_installed === true;
  const server_offline_honest = opts.offline_honest !== false;
  // When status is null/unknown, treat offline_honest as true (safe default).
  const offline_honest_input =
    opts.offline_honest == null ? true : opts.offline_honest === true;

  const live_ready =
    live_env &&
    use_dispatch &&
    injector_installed &&
    offline_honest_input === false;

  const offline_honest = !live_ready;

  const live_env_flag =
    String(opts.live_env_flag || "ANTIEK_TWIN_SEED_LIVE").trim() ||
    "ANTIEK_TWIN_SEED_LIVE";
  const use_dispatch_env_flag =
    String(opts.use_dispatch_env_flag || "USE_DISPATCH").trim() ||
    "USE_DISPATCH";

  let summary: string;
  if (live_ready) {
    summary =
      "L3 twin seed live ready · env on · dispatch on · injector installed · offline_honest=false";
  } else {
    const missing: string[] = [];
    if (!live_env) missing.push("live_env");
    if (!use_dispatch) missing.push("use_dispatch");
    if (!injector_installed) missing.push("injector");
    if (offline_honest_input) missing.push("still_offline_honest");
    summary = `L3 twin seed deferred · offline-honest · missing=${missing.join(",") || "unknown"} · never enables live from Settings`;
  }

  return {
    live_env,
    use_dispatch,
    injector_installed,
    server_offline_honest,
    live_env_flag,
    use_dispatch_env_flag,
    live_ready,
    offline_honest,
    never_enables_live: true,
    html_first: true,
    dual_gate: "L3",
    summary,
  };
}
