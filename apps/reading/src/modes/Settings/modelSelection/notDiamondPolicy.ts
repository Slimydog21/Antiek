/**
 * NotDiamond router advisor — UI policy (reading app).
 *
 * Spec: `.infinite/sprint-briefs/notdiamond-advisor-decision-spec.md`
 * Doctrine: evidence/advisory only — never routing authority.
 *
 * Modes:
 *   disabled — local policy only
 *   shadow   — log what NotDiamond would recommend; do not surface as pick
 *   advisory — show recommendation beside local ranks; operator still picks
 *
 * There is NO "authority" / "live route" mode in this policy. Live HTTP
 * adapter stays gated behind two ratified Antiek-bench weeks (backend).
 */

export type NotDiamondMode = "disabled" | "shadow" | "advisory";

export type NotDiamondUiState = {
  mode: NotDiamondMode;
  /** Always false in the reading UI — live calls are backend-gated. */
  liveAdapterEnabled: false;
  authority: "advisory_or_less";
};

export function defaultNotDiamondState(): NotDiamondUiState {
  return {
    mode: "disabled",
    liveAdapterEnabled: false,
    authority: "advisory_or_less",
  };
}

export function setNotDiamondMode(
  state: NotDiamondUiState,
  mode: NotDiamondMode,
): NotDiamondUiState {
  return {
    ...state,
    mode,
    liveAdapterEnabled: false,
    authority: "advisory_or_less",
  };
}

export function isLiveRouteForbidden(mode: NotDiamondMode): boolean {
  // Every mode forbids live authority routing from this surface.
  void mode;
  return true;
}

export function modeLabel(mode: NotDiamondMode): string {
  switch (mode) {
    case "disabled":
      return "Disabled (local policy only)";
    case "shadow":
      return "Shadow (log only — no UI pick)";
    case "advisory":
      return "Advisory (recommend beside local ranks)";
    default: {
      const _e: never = mode;
      return _e;
    }
  }
}
