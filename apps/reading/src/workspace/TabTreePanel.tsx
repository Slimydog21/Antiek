/**
 * TabTreePanel — the whole forest of document tabs (DESIGN-MODEL §2a), as
 * an ARIA tree (prefix t / ctrl+alt+y toggles it).
 *
 *   - Rows come from tabRows.flattenTabRows: depth-first pre-order, so every
 *     child sits directly under its parent.
 *   - Indentation stops at six levels; a deeper row keeps the level-6 indent
 *     and carries a depth badge (d9). No depth is unreachable or illegible.
 *   - Focus subtree re-roots the panel on any row; "up" restores the parent
 *     view, "show full tree" the whole forest. View-only: no server write.
 *   - Virtualised with fixed-height rows: only the visible window (plus
 *     overscan, plus the keyboard-focused row) is in the DOM, so 1,000 tabs
 *     cost what 40 do. Positions and set sizes ride on each treeitem, so a
 *     screen reader still hears "7 of 999".
 *   - Keys (the ARIA tree pattern): ↑/↓ move, Home/End jump, → opens or
 *     steps into a branch, ← closes it or steps to the parent, Enter opens
 *     the tab, s focuses the subtree, Esc closes the panel. Delete closes the
 *     row's tab with everything under it (prune, the default); Shift+Delete
 *     closes only that tab and lifts its children (§2a's two outcomes). Both
 *     undo for 10 s.
 */
import { useEffect, useLayoutEffect, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { ChevronDown, ChevronRight, Crosshair } from "lucide-react";

import { EmptyState } from "../components/states";
import { flattenTabRows, type TabRow } from "./tabRows";
import { kindNoun, type TabLabel } from "./tabLabels";
import { KindGlyph, NumberedLabel, domIdFor } from "./tabStripParts";
import type { TabTree } from "./tabTree";

/** Row geometry, in px. Fixed so the window is arithmetic, not measurement. */
export const TREE_ROW_HEIGHT = 28;
const INDENT_STEP = 14;
const OVERSCAN = 10;
/** The viewport assumed before layout has measured one (and under jsdom). */
const FALLBACK_VIEWPORT = 480;

export interface TabTreePanelProps {
  tree: TabTree;
  focusId: string | null;
  labelOf: (tabId: string) => TabLabel;
  onActivate: (tabId: string) => void;
  onFocusSubtree: (tabId: string | null) => void;
  /** Esc: the owner closes the panel and returns focus to its toggle. */
  onClose: () => void;
  /** Called with the ids in the rendered window (titles resolve lazily). */
  onRowsShown?: (tabIds: string[]) => void;
  /** Delete / Shift+Delete on a row: the two close outcomes (§2a). Absent,
   *  the panel offers no close. */
  onCloseTab?: (tabId: string, mode: "prune" | "lift_children") => void;
  /** Move focus onto the active row when the panel opens (prefix t), so its
   *  keys work at once. */
  focusOnOpen?: boolean;
}

export function TabTreePanel({
  tree,
  focusId,
  labelOf,
  onActivate,
  onFocusSubtree,
  onClose,
  onRowsShown,
  onCloseTab,
  focusOnOpen = false,
}: TabTreePanelProps) {
  const [collapsed, setCollapsed] = useState<ReadonlySet<string>>(() => new Set());
  const rows = useMemo(() => flattenTabRows(tree, { focusId, collapsed }), [tree, focusId, collapsed]);
  const indexOf = useMemo(() => new Map(rows.map((r, i) => [r.id, i])), [rows]);

  const activeId = tree.active_tab_id;
  const [cursor, setCursor] = useState<string | null>(null);
  const cursorId =
    cursor !== null && indexOf.has(cursor)
      ? cursor
      : activeId !== null && indexOf.has(activeId)
        ? activeId
        : (rows[0]?.id ?? null);

  const scrollerRef = useRef<HTMLDivElement>(null);
  const [scrollTop, setScrollTop] = useState(0);
  const viewport = scrollerRef.current?.clientHeight || FALLBACK_VIEWPORT;
  const start = Math.max(0, Math.floor(scrollTop / TREE_ROW_HEIGHT) - OVERSCAN);
  const end = Math.min(rows.length, Math.ceil((scrollTop + viewport) / TREE_ROW_HEIGHT) + OVERSCAN);
  const cursorIndex = cursorId !== null ? (indexOf.get(cursorId) ?? -1) : -1;
  const shown: { row: TabRow; index: number }[] = [];
  for (let i = start; i < end; i++) shown.push({ row: rows[i], index: i });
  if (cursorIndex >= 0 && (cursorIndex < start || cursorIndex >= end)) {
    shown.push({ row: rows[cursorIndex], index: cursorIndex });
  }

  const shownKey = shown.map((s) => s.row.id).join("\u0000");
  useEffect(() => {
    onRowsShown?.(shown.map((s) => s.row.id));
    // shownKey stands for `shown` (a fresh array each render).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shownKey, onRowsShown]);

  /** Keep row `index` inside the scroller's visible band. */
  function reveal(index: number) {
    const el = scrollerRef.current;
    const vh = el?.clientHeight || FALLBACK_VIEWPORT;
    const top = index * TREE_ROW_HEIGHT;
    let next = scrollTop;
    if (top < scrollTop) next = top;
    else if (top + TREE_ROW_HEIGHT > scrollTop + vh) next = top + TREE_ROW_HEIGHT - vh;
    if (next !== scrollTop) {
      setScrollTop(next);
      if (el) el.scrollTop = next;
    }
  }

  // On open, start with the active tab in view.
  useLayoutEffect(() => {
    if (activeId !== null && indexOf.has(activeId)) reveal(indexOf.get(activeId)!);
    // Only on mount and on re-rooting.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusId]);

  const rowEls = useRef(new Map<string, HTMLDivElement>());
  // Opening the panel from the keyboard lands on the active row.
  const pendingFocus = useRef<string | null>(focusOnOpen ? cursorId : null);
  useLayoutEffect(() => {
    const id = pendingFocus.current;
    if (id === null) return;
    const el = rowEls.current.get(id);
    if (el) {
      pendingFocus.current = null;
      el.focus();
    }
  });

  function moveTo(index: number) {
    const row = rows[Math.max(0, Math.min(rows.length - 1, index))];
    if (!row) return;
    setCursor(row.id);
    reveal(indexOf.get(row.id)!);
    pendingFocus.current = row.id;
  }

  function setOpen(id: string, open: boolean) {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (open) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function onKeyDown(e: KeyboardEvent<HTMLDivElement>) {
    // Chords belong to the keymap dispatcher (prefix t still toggles).
    if (cursorIndex < 0 || e.ctrlKey || e.metaKey || e.altKey) return;
    const row = rows[cursorIndex];
    let handled = true;
    switch (e.key) {
      case "ArrowDown":
        moveTo(cursorIndex + 1);
        break;
      case "ArrowUp":
        moveTo(cursorIndex - 1);
        break;
      case "Home":
        moveTo(0);
        break;
      case "End":
        moveTo(rows.length - 1);
        break;
      case "ArrowRight":
        if (row.hasChildren && !row.expanded) setOpen(row.id, true);
        else if (row.expanded) moveTo(cursorIndex + 1);
        break;
      case "ArrowLeft":
        if (row.expanded) setOpen(row.id, false);
        else if (row.parentId !== null && indexOf.has(row.parentId)) moveTo(indexOf.get(row.parentId)!);
        break;
      case "Enter":
      case " ":
        onActivate(row.id);
        break;
      case "s":
        onFocusSubtree(row.id);
        break;
      case "Delete": {
        if (!onCloseTab) {
          handled = false;
          break;
        }
        // Prune (the default) takes the row's subtree with it; Shift closes
        // only this tab and lifts its children. Focus stays in the tree, on
        // the row that takes this one's place.
        const lift = e.shiftKey;
        let next: TabRow | undefined;
        if (lift) next = rows[cursorIndex + 1] ?? rows[cursorIndex - 1];
        else {
          next = rows.slice(cursorIndex + 1).find((r) => r.level <= row.level) ?? rows[cursorIndex - 1];
        }
        if (next) {
          setCursor(next.id);
          pendingFocus.current = next.id;
        }
        onCloseTab(row.id, lift ? "lift_children" : "prune");
        break;
      }
      case "Escape":
        onClose();
        break;
      default:
        handled = false;
    }
    if (handled) {
      e.preventDefault();
      e.stopPropagation();
    }
  }

  const focusTab = focusId ? tree.nodes[focusId] : null;
  const focusParent = focusTab?.parent_tab_id ?? null;

  return (
    <div className="flex flex-col min-h-0" data-tab-tree-inner>
      <div className="flex items-center gap-2 px-2 h-7 shrink-0 border-b border-hairline">
        <span className="text-xxs uppercase tracking-wider text-shadow-1 dark:text-moonlight truncate">
          {focusTab ? `Subtree of ${focusTab.hier_number}` : "All tabs"}
        </span>
        {focusTab ? (
          <span className="ml-auto flex items-center gap-2 shrink-0">
            <button
              type="button"
              onClick={() => onFocusSubtree(focusParent)}
              className="text-xxs text-sun-deep hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-sun rounded"
            >
              up
            </button>
            <button
              type="button"
              onClick={() => onFocusSubtree(null)}
              className="text-xxs text-sun-deep hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-sun rounded"
            >
              show full tree
            </button>
          </span>
        ) : null}
      </div>

      {rows.length === 0 ? (
        <div className="p-2">
          <EmptyState
            variant="inline"
            art={false}
            title="No open tabs"
            body="Open a document, a research or a draft and it gets a tab here."
          />
        </div>
      ) : (
        <div
          ref={scrollerRef}
          className="relative overflow-auto overscroll-contain"
          style={{ maxHeight: "min(60vh, 560px)" }}
          onScroll={(e) => setScrollTop(e.currentTarget.scrollTop)}
        >
          <div
            role="tree"
            aria-label={focusTab ? `Tabs under ${focusTab.hier_number}` : "All tabs"}
            onKeyDown={onKeyDown}
            className="relative"
            style={{ height: rows.length * TREE_ROW_HEIGHT }}
          >
            {shown.map(({ row, index }) => {
              const tab = tree.nodes[row.id];
              const label = labelOf(row.id);
              const isActive = row.id === activeId;
              const isCursor = row.id === cursorId;
              return (
                <div
                  key={row.id}
                  ref={(el) => {
                    if (el) rowEls.current.set(row.id, el);
                    else rowEls.current.delete(row.id);
                  }}
                  role="treeitem"
                  id={domIdFor("tabtree", row.id)}
                  aria-level={row.level}
                  aria-setsize={row.setsize}
                  aria-posinset={row.posinset}
                  aria-selected={isActive}
                  aria-expanded={row.hasChildren ? row.expanded : undefined}
                  tabIndex={isCursor ? 0 : -1}
                  data-tree-row={row.id}
                  onClick={() => {
                    setCursor(row.id);
                    onActivate(row.id);
                  }}
                  onFocus={() => setCursor(row.id)}
                  className={`group absolute inset-x-0 flex items-center gap-1.5 pr-1 text-xs cursor-default select-none outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-sun ${
                    isActive
                      ? "bg-ice-2 dark:bg-charcoal-1 text-ink dark:text-bright"
                      : "text-ink dark:text-bright hover:bg-ice-1 dark:hover:bg-charcoal-1/60"
                  }`}
                  style={{
                    top: index * TREE_ROW_HEIGHT,
                    height: TREE_ROW_HEIGHT,
                    paddingLeft: `${8 + row.indent * INDENT_STEP}px`,
                  }}
                >
                  <span
                    aria-hidden="true"
                    className="w-3 shrink-0 text-shadow-1 dark:text-moonlight"
                    onClick={(e) => {
                      if (!row.hasChildren) return;
                      e.stopPropagation();
                      setOpen(row.id, !row.expanded);
                    }}
                  >
                    {row.hasChildren ? (
                      row.expanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />
                    ) : null}
                  </span>
                  <KindGlyph tab={tab} className="text-shadow-1 dark:text-moonlight" />
                  <NumberedLabel tab={tab} label={label} />
                  <span className="sr-only">, {kindNoun(tab).toLowerCase()}</span>
                  {row.depth > 6 ? (
                    <span
                      data-depth-badge
                      aria-label={`depth ${row.depth}`}
                      className="shrink-0 rounded-sm border border-hairline px-1 font-mono text-xxs leading-4 text-shadow-1 dark:text-moonlight"
                    >
                      d{row.depth}
                    </span>
                  ) : null}
                  <button
                    type="button"
                    tabIndex={-1}
                    aria-hidden="true"
                    data-focus-subtree
                    title={`Focus the subtree at ${tab.hier_number} (s)`}
                    onClick={(e) => {
                      e.stopPropagation();
                      onFocusSubtree(row.id);
                    }}
                    className="ml-auto shrink-0 rounded p-0.5 text-shadow-1 opacity-0 group-hover:opacity-100 group-focus-visible:opacity-100 hover:text-ink dark:hover:text-bright"
                  >
                    <Crosshair size={12} />
                  </button>
                </div>
              );
            })}
          </div>
        </div>
      )}
      {rows.length > 0 ? (
        <p className="shrink-0 border-t border-hairline px-2 py-1 text-xxs text-shadow-1 dark:text-moonlight">
          ↑↓ move · → ← open, close · Enter opens · s focuses the subtree
          {onCloseTab ? " · Delete prunes · ⇧Delete closes only this" : ""} · Esc closes
        </p>
      ) : null}
    </div>
  );
}
