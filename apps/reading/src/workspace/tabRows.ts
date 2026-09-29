/**
 * tabRows.ts — the tree panel's rows: the forest (or one focused subtree)
 * flattened DEPTH-FIRST, pre-order, so every child is drawn directly under
 * its own parent (forensic defect 3: breadth-first order indented by depth
 * put children under the wrong parent as soon as there were two roots).
 *
 * Each row carries what the ARIA tree pattern needs on a flat list (level,
 * set size, position) and what the panel draws (the true depth for the
 * `dN` badge, the capped indent). Iterative: a 300-deep rabbit hole must not
 * blow the stack.
 */
import { depthOf, type TabTree } from "./tabTree";

/** Indentation stops growing here; deeper rows carry a depth badge. */
export const INDENT_CAP = 6;

export interface TabRow {
  id: string;
  parentId: string | null;
  /** aria-level: 1 at the top of the current view. */
  level: number;
  /** The tab's true depth in its tree (1 = a root), for the dN badge. */
  depth: number;
  /** Levels of indent actually drawn (never more than INDENT_CAP - 1). */
  indent: number;
  setsize: number;
  posinset: number;
  hasChildren: boolean;
  expanded: boolean;
}

export function flattenTabRows(
  tree: TabTree,
  opts: { focusId?: string | null; collapsed?: ReadonlySet<string> } = {},
): TabRow[] {
  const collapsed = opts.collapsed ?? new Set<string>();
  const focus = opts.focusId && Object.hasOwn(tree.nodes, opts.focusId) ? opts.focusId : null;
  const tops = focus ? [focus] : [...tree.root_order];
  const baseDepth = focus ? depthOf(tree, focus) - 1 : 0;
  const rows: TabRow[] = [];
  type Frame = { id: string; level: number; posinset: number; setsize: number };
  const stack: Frame[] = [];
  for (let i = tops.length - 1; i >= 0; i--) {
    stack.push({ id: tops[i], level: 1, posinset: i + 1, setsize: tops.length });
  }
  while (stack.length > 0) {
    const f = stack.pop() as Frame;
    const node = tree.nodes[f.id];
    if (!node) continue;
    const children = node.child_order.filter((c) => Object.hasOwn(tree.nodes, c));
    const expanded = children.length > 0 && !collapsed.has(f.id);
    rows.push({
      id: f.id,
      parentId: f.level === 1 ? null : node.parent_tab_id,
      level: f.level,
      depth: baseDepth + f.level,
      indent: Math.min(f.level, INDENT_CAP) - 1,
      setsize: f.setsize,
      posinset: f.posinset,
      hasChildren: children.length > 0,
      expanded,
    });
    if (!expanded) continue;
    for (let i = children.length - 1; i >= 0; i--) {
      stack.push({ id: children[i], level: f.level + 1, posinset: i + 1, setsize: children.length });
    }
  }
  return rows;
}
