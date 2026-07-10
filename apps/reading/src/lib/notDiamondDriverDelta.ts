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
