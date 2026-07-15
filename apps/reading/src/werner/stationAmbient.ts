/**
 * One decision point for the live station's ambient animation.
 *
 * Product reactions and directed interaction are higher-authority foreground
 * states. An activity's idle class may run only when every foreground gate is
 * clear and the pointer is genuinely idle on a visible page.
 */
export interface StationAmbientInput {
  activeClass: string | null;
  idleClass: string | null;
  pointerIdle: boolean;
  tabHidden: boolean;
  dragging: boolean;
  directedTravel: boolean;
  returningHome: boolean;
  productEmote: boolean;
  reducedMotion: boolean;
  activityEnabled: boolean;
}

export function stationAmbientClass({
  activeClass,
  idleClass,
  pointerIdle,
  tabHidden,
  dragging,
  directedTravel,
  returningHome,
  productEmote,
  reducedMotion,
  activityEnabled,
}: StationAmbientInput): string | null {
  const activityClass = pointerIdle ? idleClass : activeClass;
  if (
    !activityClass ||
    !activityEnabled ||
    reducedMotion ||
    tabHidden ||
    dragging ||
    directedTravel ||
    returningHome ||
    productEmote
  ) {
    return null;
  }
  return activityClass;
}
