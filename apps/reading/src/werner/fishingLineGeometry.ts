export interface Point {
  x: number;
  y: number;
}

/**
 * Quadratic catenary-ish line from rod tip to bait (SPR-14).
 * sag = min(40, slack * 0.12) where slack = dist - tautLength.
 */
export function catenaryPath(
  rod: Point,
  bait: Point,
  tautLength = 24,
): string {
  const dx = bait.x - rod.x;
  const dy = bait.y - rod.y;
  const dist = Math.hypot(dx, dy);
  if (dist < 8) {
    return `M ${rod.x} ${rod.y} L ${bait.x} ${bait.y}`;
  }
  const slack = Math.max(0, dist - tautLength);
  const sag = Math.min(40, slack * 0.12);
  const mx = (rod.x + bait.x) / 2;
  const my = (rod.y + bait.y) / 2 + sag;
  return `M ${rod.x} ${rod.y} Q ${mx} ${my} ${bait.x} ${bait.y}`;
}

/** Rod tip in screen space from mascot bounding box (64px viewBox scale). */
export function rodTipFromMascotRect(
  rect: DOMRect,
  mascotSize: number,
  localTip = { x: 50, y: 22 },
): Point {
  const scale = mascotSize / 64;
  return {
    x: rect.left + localTip.x * scale,
    y: rect.top + localTip.y * scale,
  };
}