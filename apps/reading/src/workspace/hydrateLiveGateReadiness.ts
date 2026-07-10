/**
 * Residual (ave): pure L1/L2 publication hydrate dual-gate readiness.
 *
 * Settings hydrate-live panel honesty: arxiv (L1) and substack (L2) each need
 * env_enabled + injector_installed. Offline-honest when neither live path is
 * ready. Settings never enables live injectors — operator dual-gate only.
 *
 * Outside Settings pure CTA thrash (aut–avc) · dual-gate honesty polish.
 */

export type HydrateLiveGateLeg = {
  dual_gate: "L1" | "L2";
  source: "arxiv" | "substack";
  env_flag: string;
  env_enabled: boolean;
  injector_installed: boolean;
  /** Live hydrate ready for this source (both gates on). */
  live_ready: boolean;
  summary: string;
};

export type HydrateLiveGateReadiness = {
  arxiv: HydrateLiveGateLeg;
  substack: HydrateLiveGateLeg;
  any_live_ready: boolean;
  offline_honest: boolean;
  never_enables_live: true;
  html_first: true;
  dual_gate: "L1-L2";
  summary: string;
};

function leg(
  dual_gate: "L1" | "L2",
  source: "arxiv" | "substack",
  env_flag: string,
  env_enabled: boolean,
  injector_installed: boolean,
): HydrateLiveGateLeg {
  const live_ready = env_enabled && injector_installed;
  const summary = live_ready
    ? `${source} live ready · env on · injector installed (${dual_gate})`
    : !env_enabled && !injector_installed
      ? `${source} deferred · env off · injector absent (${dual_gate})`
      : !env_enabled
        ? `${source} deferred · env off · injector present (${dual_gate})`
        : `${source} deferred · env on · injector absent (${dual_gate})`;
  return {
    dual_gate,
    source,
    env_flag,
    env_enabled,
    injector_installed,
    live_ready,
    summary,
  };
}

/**
 * Composite L1/L2 hydrate dual-gate readiness from status payload fields.
 * Pure — never mutates injectors · never invents live readiness.
 */
export function hydrateLiveGateReadiness(opts: {
  arxiv_env_flag?: string | null;
  arxiv_env_enabled?: boolean | null;
  arxiv_injector_installed?: boolean | null;
  substack_env_flag?: string | null;
  substack_env_enabled?: boolean | null;
  substack_injector_installed?: boolean | null;
  /** Server-reported composite; recomputed for honesty when present. */
  offline_honest?: boolean | null;
  any_live_injector?: boolean | null;
}): HydrateLiveGateReadiness {
  const arxiv = leg(
    "L1",
    "arxiv",
    String(opts.arxiv_env_flag || "ANTIEK_HYDRATE_LIVE_ARXIV").trim() ||
      "ANTIEK_HYDRATE_LIVE_ARXIV",
    opts.arxiv_env_enabled === true,
    opts.arxiv_injector_installed === true,
  );
  const substack = leg(
    "L2",
    "substack",
    String(opts.substack_env_flag || "ANTIEK_HYDRATE_LIVE_SUBSTACK").trim() ||
      "ANTIEK_HYDRATE_LIVE_SUBSTACK",
    opts.substack_env_enabled === true,
    opts.substack_injector_installed === true,
  );

  const any_live_ready = arxiv.live_ready || substack.live_ready;
  // Offline-honest when no live path is fully gated on.
  const offline_honest = !any_live_ready;

  const summary = offline_honest
    ? `offline-honest · L1 arxiv ${arxiv.live_ready ? "live" : "deferred"} · L2 substack ${substack.live_ready ? "live" : "deferred"} · never enables live from Settings`
    : `live hydrate path open · L1 arxiv ${arxiv.live_ready ? "ready" : "deferred"} · L2 substack ${substack.live_ready ? "ready" : "deferred"} · operator dual-gate only`;

  return {
    arxiv,
    substack,
    any_live_ready,
    offline_honest,
    never_enables_live: true,
    html_first: true,
    dual_gate: "L1-L2",
    summary,
  };
}
