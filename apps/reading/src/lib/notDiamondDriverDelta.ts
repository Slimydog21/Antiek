/**
 * Residual (rl): compare NotDiamond weekly advisory suggestion to the
 * installed decision-tree driver. Pure honesty helper — advisory never auto-
 * installs; delta is operator-visible only.
 */

export type NotDiamondDriverDeltaStatus =
  | "no_suggestion"
  | "no_installed"
  | "match"
  | "differs";

export type NotDiamondDriverDelta = {
  status: NotDiamondDriverDeltaStatus;
  suggested: string;
  installed: string;
  /** Always true — NotDiamond is never dispatch authority. */
  advisory_only: true;
};

export function notDiamondDriverDelta(opts: {
  suggestedModelId?: string | null;
  installedModelId?: string | null;
}): NotDiamondDriverDelta {
  const suggested = String(opts.suggestedModelId || "").trim();
  const installed = String(opts.installedModelId || "").trim();
  if (!suggested) {
    return {
      status: "no_suggestion",
      suggested: "",
      installed,
      advisory_only: true,
    };
  }
  if (!installed) {
    return {
      status: "no_installed",
      suggested,
      installed: "",
      advisory_only: true,
    };
  }
  if (suggested === installed) {
    return {
      status: "match",
      suggested,
      installed,
      advisory_only: true,
    };
  }
  return {
    status: "differs",
    suggested,
    installed,
    advisory_only: true,
  };
}

/** Human-readable status line for Settings chrome. */
export function notDiamondDriverDeltaLabel(d: NotDiamondDriverDelta): string {
  switch (d.status) {
    case "no_suggestion":
      return "No advisory model this week (refresh weekly advisory)";
    case "no_installed":
      return `No driver installed · advisory suggests ${d.suggested} (explicit install only)`;
    case "match":
      return `Installed driver matches advisory (${d.installed})`;
    case "differs":
      return `Installed ${d.installed} · advisory suggests ${d.suggested} (differs — not auto-applied)`;
    default:
      return "Advisory only";
  }
}

/**
 * Residual (ade): compare NotDiamond weekly advisory to Antiek-bench weekly
 * recommended model. Both are advisory only — neither auto-routes dispatch.
 */
export type NotDiamondBenchDeltaStatus =
  | "no_nd"
  | "no_bench"
  | "agree"
  | "diverge";

export type NotDiamondBenchDelta = {
  status: NotDiamondBenchDeltaStatus;
  nd_suggested: string;
  bench_recommended: string;
  /** Always true — never NotDiamond router / never auto-bench route. */
  advisory_only: true;
};

export function notDiamondBenchDelta(opts: {
  ndSuggestedModelId?: string | null;
  benchRecommendedModelId?: string | null;
}): NotDiamondBenchDelta {
  const nd = String(opts.ndSuggestedModelId || "").trim();
  const bench = String(opts.benchRecommendedModelId || "").trim();
  if (!nd) {
    return {
      status: "no_nd",
      nd_suggested: "",
      bench_recommended: bench,
      advisory_only: true,
    };
  }
  if (!bench) {
    return {
      status: "no_bench",
      nd_suggested: nd,
      bench_recommended: "",
      advisory_only: true,
    };
  }
  if (nd.toLowerCase() === bench.toLowerCase()) {
    return {
      status: "agree",
      nd_suggested: nd,
      bench_recommended: bench,
      advisory_only: true,
    };
  }
  return {
    status: "diverge",
    nd_suggested: nd,
    bench_recommended: bench,
    advisory_only: true,
  };
}

export function notDiamondBenchDeltaLabel(d: NotDiamondBenchDelta): string {
  switch (d.status) {
    case "no_nd":
      return "No NotDiamond advisory model this week";
    case "no_bench":
      return `NotDiamond suggests ${d.nd_suggested} · Antiek-bench weekly rank unset (run offline dogfood)`;
    case "agree":
      return `NotDiamond and Antiek-bench agree on ${d.nd_suggested} (both advisory only)`;
    case "diverge":
      return `NotDiamond ${d.nd_suggested} · Antiek-bench ${d.bench_recommended} (diverge — neither auto-routes)`;
    default:
      return "Advisory only";
  }
}

/**
 * Residual (arj): product verdict — is NotDiamond useful as a router?
 * Investigation conclusion hard-coded for Settings honesty + FUTURE agents:
 * useful as weekly advisor only; never dispatch router (L7 · decision-tree
 * sovereignty · Antiek-bench local recursive rewrite is the quality truth).
 */
export type NotDiamondImplementationVerdict = {
  implement_as_router: false;
  implement_as_advisory: true;
  dual_gate: "L7";
  never_auto_route: true;
  rationale: readonly string[];
  summary: string;
};

export function notDiamondImplementationVerdict(): NotDiamondImplementationVerdict {
  const rationale = [
    "Operator decision-tree sovereignty: model choice is explicit install, not silent route",
    "Antiek-bench recursive weekly rewrite is local usage-truth for task quality",
    "L7 dual-gate: NotDiamond router never under Antiek product doctrine",
    "Advisory weekly pick still useful for operator comparison (match/differs/agree/diverge)",
  ] as const;
  return {
    implement_as_router: false,
    implement_as_advisory: true,
    dual_gate: "L7",
    never_auto_route: true,
    rationale,
    summary:
      "Implement as weekly advisor only · never as dispatch router (L7 · decision-tree sovereignty)",
  };
}
