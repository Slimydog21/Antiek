import type { PaneTarget, PaneTile } from "./panel.types";

export const CORE_PANE: PaneTarget = { kind: "core" };
export const COMPANION_PANE: PaneTarget = { kind: "companion" };
export const PANE_GAP = 10;
export const PANE_MIN_WIDTH = 360;

export type PaneRect = { x: number; y: number; width: number; height: number };
export type PanePlacement = { target: PaneTarget; rect: PaneRect };
export type PaneGeometry =
  | { kind: "unmeasured" }
  | { kind: "measured"; width: number; height: number; placements: PanePlacement[] };

export function paneKey(target: PaneTarget): string {
  switch (target.kind) {
    case "core": return "core";
    case "companion": return "companion";
    case "window": return `window:${target.id}`;
  }
}

export function samePane(a: PaneTarget | null, b: PaneTarget | null): boolean {
  return a === b || (a !== null && b !== null && paneKey(a) === paneKey(b));
}

/** Preserve presentation order; only actual admitted hosts can enter it. */
export function reconcilePaneOrder(previous: readonly PaneTarget[], admitted: readonly PaneTarget[]): PaneTarget[] {
  const current = new Map(admitted.map((target) => [paneKey(target), target]));
  const result: PaneTarget[] = [];
  for (const target of [...previous, ...admitted]) {
    const key = paneKey(target);
    const member = current.get(key);
    if (!member) continue;
    result.push(member);
    current.delete(key);
  }
  return result;
}

export function adjacentPane(order: readonly PaneTarget[], target: PaneTarget, direction: -1 | 1): PaneTarget | null {
  const index = order.findIndex((member) => samePane(member, target));
  return index < 0 ? null : order[index + direction] ?? null;
}

export function spatialPaneNeighbor(placements: readonly PanePlacement[], target: PaneTarget, direction: -1 | 1): PaneTarget | null {
  const current = placements.find((member) => samePane(member.target, target));
  if (!current) return null;
  const center = current.rect.x + current.rect.width / 2;
  const middle = current.rect.y + current.rect.height / 2;
  const candidates = placements.filter((member) => !samePane(member.target, target)
    && direction * (member.rect.x + member.rect.width / 2 - center) > 0);
  const rank = (member: PanePlacement) => ({
    outsideRow: Math.min(current.rect.y + current.rect.height, member.rect.y + member.rect.height)
      <= Math.max(current.rect.y, member.rect.y) ? 1 : 0,
    horizontal: Math.abs(member.rect.x + member.rect.width / 2 - center),
    vertical: Math.abs(member.rect.y + member.rect.height / 2 - middle),
  });
  candidates.sort((a, b) => {
    const first = rank(a); const second = rank(b);
    return first.outsideRow - second.outsideRow || first.horizontal - second.horizontal || first.vertical - second.vertical;
  });
  return candidates[0]?.target ?? null;
}

export function swapAdjacentPane(order: PaneTarget[], target: PaneTarget, direction: -1 | 1): PaneTarget[] {
  const index = order.findIndex((member) => samePane(member, target));
  const neighbor = index < 0 ? null : order[index + direction];
  if (!neighbor) return order;
  return order.map((member, i) => i === index ? neighbor : i === index + direction ? target : member);
}

function removeMissingTiles(tree: PaneTile | null, available: Set<string>): PaneTile | null {
  if (!tree) return null;
  if (tree.kind === "leaf") {
    const key = paneKey(tree.target);
    if (!available.delete(key)) return null;
    return tree;
  }
  const first = removeMissingTiles(tree.first, available);
  const second = removeMissingTiles(tree.second, available);
  if (!first) return second;
  if (!second) return first;
  return { ...tree, first, second };
}

function shallowestLeaf(tree: PaneTile, depth = 0): { target: PaneTarget; depth: number } {
  if (tree.kind === "leaf") return { target: tree.target, depth };
  const first = shallowestLeaf(tree.first, depth + 1);
  const second = shallowestLeaf(tree.second, depth + 1);
  return first.depth <= second.depth ? first : second;
}

function insertTile(tree: PaneTile, target: PaneTarget): PaneTile {
  const selected = shallowestLeaf(tree);
  function insert(node: PaneTile): PaneTile {
    if (node.kind === "leaf") {
      return samePane(node.target, selected.target)
        ? { kind: "split", axis: selected.depth % 2 === 0 ? "x" : "y", ratio: 0.5,
            first: node, second: { kind: "leaf", target } }
        : node;
    }
    return { ...node, first: insert(node.first), second: insert(node.second) };
  }
  return insert(tree);
}

/** Layout toggles never rebuild surviving splits or discard their ratios. */
export function reconcilePaneTiles(previous: PaneTile | null, order: readonly PaneTarget[]): PaneTile | null {
  const remaining = new Set(order.map(paneKey));
  let tree = removeMissingTiles(previous, remaining);
  for (const target of order) {
    if (!remaining.delete(paneKey(target))) continue;
    tree = tree ? insertTile(tree, target) : { kind: "leaf", target };
  }
  return tree;
}

export function swapPaneTiles(tree: PaneTile | null, a: PaneTarget, b: PaneTarget): PaneTile | null {
  if (!tree) return null;
  if (tree.kind === "leaf") {
    return samePane(tree.target, a) ? { ...tree, target: b }
      : samePane(tree.target, b) ? { ...tree, target: a } : tree;
  }
  return { ...tree, first: swapPaneTiles(tree.first, a, b) ?? tree.first,
    second: swapPaneTiles(tree.second, a, b) ?? tree.second };
}

function validRect(rect: PaneRect): boolean {
  return Object.values(rect).every(Number.isFinite) && rect.width > 0 && rect.height > 0;
}

export function paneGeometry(input: {
  width: number; height: number; arrangement: "horizontal" | "tiled";
  order: readonly PaneTarget[]; tiles: PaneTile | null; zoom: PaneTarget | null;
}): PaneGeometry {
  const { width, height, order, tiles, zoom, arrangement } = input;
  const working = { x: PANE_GAP, y: PANE_GAP, width: width - 2 * PANE_GAP, height: height - 2 * PANE_GAP };
  if (!validRect(working)) return { kind: "unmeasured" };
  if (zoom && order.some((target) => samePane(target, zoom))) {
    return { kind: "measured", width, height, placements: [{ target: zoom, rect: working }] };
  }
  if (arrangement === "horizontal") {
    const columnWidth = Math.max(PANE_MIN_WIDTH, width * 0.49);
    return { kind: "measured", width: Math.max(width, PANE_GAP + order.length * (columnWidth + PANE_GAP)), height,
      placements: order.map((target, index) => ({ target,
        rect: { ...working, x: PANE_GAP + index * (columnWidth + PANE_GAP), width: columnWidth } })) };
  }
  const placements: PanePlacement[] = [];
  function place(node: PaneTile, rect: PaneRect): void {
    if (node.kind === "leaf") { placements.push({ target: node.target, rect }); return; }
    const ratio = Number.isFinite(node.ratio) ? Math.max(0.1, Math.min(0.9, node.ratio)) : 0.5;
    if (node.axis === "x") {
      const available = rect.width - PANE_GAP;
      const firstWidth = available * ratio;
      place(node.first, { ...rect, width: firstWidth });
      place(node.second, { ...rect, x: rect.x + firstWidth + PANE_GAP, width: available - firstWidth });
    } else {
      const available = rect.height - PANE_GAP;
      const firstHeight = available * ratio;
      place(node.first, { ...rect, height: firstHeight });
      place(node.second, { ...rect, y: rect.y + firstHeight + PANE_GAP, height: available - firstHeight });
    }
  }
  if (tiles) place(tiles, working);
  return placements.every(({ rect }) => validRect(rect))
    ? { kind: "measured", width, height, placements }
    : { kind: "unmeasured" };
}

/** World coordinates from the measured scrollport, never the browser width. */
export function revealPane(input: {
  rect: PaneRect; viewportWidth: number; extentWidth: number; scrollLeft: number;
}): number | null {
  const { rect, viewportWidth, extentWidth, scrollLeft } = input;
  if (!validRect(rect) || ![viewportWidth, extentWidth, scrollLeft].every(Number.isFinite)
      || viewportWidth <= 0 || extentWidth <= 0) return null;
  const left = rect.x;
  const right = rect.x + rect.width;
  const next = rect.width > viewportWidth || left < scrollLeft ? left
    : right > scrollLeft + viewportWidth ? right - viewportWidth : scrollLeft;
  return Math.max(0, Math.min(Math.max(0, extentWidth - viewportWidth), next));
}
