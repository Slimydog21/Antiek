/**
 * DocumentTabStrip — the cockpit's left document tab strip (D6).
 *
 * Mounted ONCE in PanelLayout's shared centre column, so both presets get it
 * (the inset left pane; the docked main surface area) and every route's
 * mothership gets it (universal — Write mode's C5 groundwork). It renders:
 *
 *   - the ACTIVE PATH's tabs as a calm strip (hier numbers + labels, click
 *     to activate) — the model's addressing is the ancestry display;
 *   - the Opus Trail as the breadcrumb for the active tab's ancestry, over
 *     a Thread built by documentSpace.threadForPath in the ONE form Trail
 *     lawfully renders (every hop on the same canonical entity — the
 *     one-entity integrity contract is never bent). Never a second
 *     breadcrumb component;
 *   - the tree panel (prefix t): the full tree, with subtree focus;
 *   - the undo affordance after a close (the model's undo tokens).
 *
 * Tabs are navigation state: ACTIVATING a tab navigates to its canonical
 * route (routeForTab — the URL stays canonical, never a guessed embedding).
 * Kinds with no canonical route render the honest "opens as window" bridge.
 *
 * Two sync directions, both loop-safe:
 *   route → tree: the current route's surface is seeded as a root tab and
 *     activated (a route the operator navigated to directly still has a tab);
 *   tree → route: activating a tab with a canonical route (strip, keys)
 *     navigates there.
 *
 * Test/story seam: without a Router context the strip renders nothing (it
 * exists to navigate) — PanelLayout's router-free tests keep their DOM.
 */
import { useEffect, useRef } from "react";
import { useInRouterContext, useLocation, useNavigate } from "react-router-dom";

import { Trail } from "../shell/Trail";
import {
  mothershipForPath,
  rootRefForPath,
  rootTabId,
  routeForTab,
  threadForPath,
} from "./documentSpace";
import { pathTo, type TabNode } from "./tabTree";
import { useTabTrees } from "./tabTreeStore";

/** The display label the model can honestly offer (it stores no titles —
 *  titles live in the surfaces): a branch anchor's quote, else the ref. */
export function labelForTab(tab: TabNode): string {
  const quote = tab.branch_origin?.anchor?.quote?.trim();
  if (quote) return quote.length > 36 ? `${quote.slice(0, 36)}…` : quote;
  return tab.ref;
}

export function DocumentTabStrip() {
  // Test/story seam: without a Router context the strip renders nothing (it
  // exists to navigate) — PanelLayout's router-free tests keep their DOM.
  // The guard is an OUTER component because hooks cannot be conditional.
  if (!useInRouterContext()) return null;
  return <DocumentTabStripInner />;
}

function DocumentTabStripInner() {
  const location = useLocation();
  const navigate = useNavigate();
  const mothership = mothershipForPath(location.pathname);

  const tree = useTabTrees((s) => s.trees[mothership]);
  const treePanelOpen = useTabTrees((s) => s.treePanelOpen);
  const subtreeFocusId = useTabTrees((s) => s.subtreeFocusId);
  const lastUndo = useTabTrees((s) => s.lastUndo);

  // route → tree: seed the current route's surface as a root tab and follow
  // it (unless the operator is already down one of its branches).
  useEffect(() => {
    // (the outer component already proved a Router exists)
    let cancelled = false;
    void (async () => {
      await useTabTrees.getState().ensureMothership(mothership);
      if (cancelled) return;
      const ref = rootRefForPath(location.pathname);
      if (!ref) return;
      const store = useTabTrees.getState();
      const tree = store.trees[mothership];
      if (!tree) return;
      const id = rootTabId(ref);
      if (!tree.nodes[id]) {
        store.spawnTab(mothership, null, {
          tab_id: id,
          kind: ref.kind,
          ref: ref.ref,
          mothership,
          activate: true,
        });
        return;
      }
      const active = tree.active_tab_id;
      const inSubtree = active !== null && pathTo(tree, active).includes(id);
      if (!inSubtree && active !== id) store.activateTab(mothership, id);
    })();
    return () => {
      cancelled = true;
    };
  }, [location.pathname, mothership]);

  // tree → route: an ACTIVATION (strip clicks, the prefix keys, the
  // cross-pane seam) navigates to the tab's canonical route. Guarded to
  // changes only: whatever was already active when this strip mounted (a
  // stale store from an earlier surface) is NOT a mandate to hijack the
  // current route — the route sync above is the authority on mount.
  const activeTab = tree?.active_tab_id ? tree.nodes[tree.active_tab_id] : null;
  const activeRoute = activeTab ? routeForTab(activeTab) : null;
  const prevActiveRef = useRef<string | null>(activeTab?.tab_id ?? null);
  useEffect(() => {
    const id = activeTab?.tab_id ?? null;
    if (id === prevActiveRef.current) return;
    prevActiveRef.current = id;
    if (activeRoute && location.pathname !== activeRoute) navigate(activeRoute);
  }, [activeTab, activeRoute, location.pathname, navigate]);

  function openTab(tab: TabNode) {
    useTabTrees.getState().activateTab(mothership, tab.tab_id);
    const route = routeForTab(tab);
    if (route) navigate(route);
  }

  const path = tree && tree.active_tab_id ? pathTo(tree, tree.active_tab_id) : [];
  const thread = tree ? threadForPath(tree, tree.active_tab_id) : null;

  return (
    <div className="relative shrink-0" data-document-strip>
      <div className="flex items-center gap-1 border-b border-hairline px-2 py-1 text-xs">
        <button
          type="button"
          onClick={() => useTabTrees.getState().toggleTreePanel()}
          aria-expanded={treePanelOpen}
          aria-label="Toggle the tab tree"
          className="shrink-0 rounded px-1.5 py-0.5 text-shadow-1 dark:text-moonlight hover:bg-ice-2 dark:hover:bg-charcoal-1"
        >
          ≡
        </button>
        {!tree && <span className="text-shadow-1 dark:text-moonlight">tabs…</span>}
        {path.map((tabId, i) => {
          const tab = tree!.nodes[tabId];
          const isActive = tabId === tree!.active_tab_id;
          return (
            <span key={tabId} className="flex items-center gap-1 min-w-0">
              {i > 0 && <span aria-hidden="true" className="text-ink-mute dark:text-moonlight/60">›</span>}
              <button
                type="button"
                onClick={() => openTab(tab)}
                data-tab-id={tabId}
                aria-current={isActive ? "page" : undefined}
                className={`flex items-center gap-1 min-w-0 rounded px-1.5 py-0.5 ${
                  isActive
                    ? "bg-ice-2 dark:bg-charcoal-1 text-ink dark:text-bright"
                    : "text-ink-soft dark:text-moonlight hover:bg-ice-2 dark:hover:bg-charcoal-1"
                }`}
              >
                <span className="font-mono text-shadow-1 dark:text-moonlight shrink-0">
                  {tab.hier_number}
                </span>
                <span className="truncate">{labelForTab(tab)}</span>
              </button>
            </span>
          );
        })}
        {activeTab && routeForTab(activeTab) === null ? (
          <span
            className="ml-1 text-shadow-1 dark:text-moonlight italic"
            data-tab-bridge
            title="This surface is route-bound — it opens as a window, never an embedding guess."
          >
            opens as window
          </span>
        ) : null}
        {lastUndo ? (
          <button
            type="button"
            onClick={() => useTabTrees.getState().undoLastClose(mothership)}
            className="ml-auto shrink-0 rounded px-1.5 py-0.5 text-sun-deep hover:bg-ice-2 dark:hover:bg-charcoal-1"
            data-undo-close
          >
            Undo close
          </button>
        ) : null}
      </div>

      {thread && thread.hops.length > 1 ? (
        <div className="border-b border-hairline" data-tab-trail>
          <Trail
            thread={thread}
            onJump={(hop) => {
              if (hop.provenanceRef) {
                const tab = tree?.nodes[hop.provenanceRef];
                if (tab) openTab(tab);
              }
            }}
          />
        </div>
      ) : null}

      {treePanelOpen && tree ? (
        <div
          data-tab-tree-panel
          className="absolute left-0 top-full z-20 mt-0.5 max-h-[60vh] min-w-[260px] max-w-[360px] overflow-auto rounded border border-hairline bg-ice-0 dark:bg-charcoal-2 shadow-z2 py-1"
        >
          <TreePanel
            tree={tree}
            focusId={subtreeFocusId}
            onActivate={openTab}
            onFocus={(id) => useTabTrees.getState().setSubtreeFocus(id)}
          />
        </div>
      ) : null}
    </div>
  );
}

function TreePanel({
  tree,
  focusId,
  onActivate,
  onFocus,
}: {
  tree: NonNullable<ReturnType<typeof useTabTrees.getState>["trees"]["reading"]>;
  focusId: string | null;
  onActivate: (tab: TabNode) => void;
  onFocus: (id: string | null) => void;
}) {
  const roots = focusId ? [focusId] : [...tree.root_order];
  const focusTab = focusId ? tree.nodes[focusId] : null;
  const rows: { tab: TabNode; depth: number }[] = [];
  const stack = roots.map((id) => ({ id, depth: 0 }));
  while (stack.length > 0) {
    const { id, depth } = stack.shift() as { id: string; depth: number };
    const tab = tree.nodes[id];
    if (!tab) continue;
    rows.push({ tab, depth });
    for (const c of tab.child_order) stack.push({ id: c, depth: depth + 1 });
  }
  return (
    <>
      <div className="flex items-center justify-between px-2 py-1 border-b border-hairline">
        <span className="text-xxs uppercase tracking-wider text-shadow-1 dark:text-moonlight">
          {focusTab ? `Subtree of ${focusTab.hier_number}` : "All tabs"}
        </span>
        {focusTab ? (
          <button
            type="button"
            onClick={() => onFocus(null)}
            className="text-xxs text-sun-deep hover:underline"
          >
            show full tree
          </button>
        ) : null}
      </div>
      {rows.length === 0 ? (
        <p className="px-2 py-1 text-xs text-shadow-1 dark:text-moonlight">No open tabs.</p>
      ) : null}
      {rows.map(({ tab, depth }) => (
        <div
          key={tab.tab_id}
          className={`flex items-center gap-1.5 px-2 py-0.5 text-xs ${
            tab.tab_id === tree.active_tab_id ? "bg-ice-2 dark:bg-charcoal-1" : ""
          }`}
          style={{ paddingLeft: `${8 + depth * 14}px` }}
          data-tree-row={tab.tab_id}
        >
          <button
            type="button"
            onClick={() => onActivate(tab)}
            className="flex items-center gap-1.5 min-w-0 text-left text-ink dark:text-bright"
          >
            <span className="font-mono text-shadow-1 dark:text-moonlight shrink-0">
              {tab.hier_number}
            </span>
            <span className="truncate">{labelForTab(tab)}</span>
            <span className="text-xxs text-shadow-1 dark:text-moonlight shrink-0">
              {tab.kind}
            </span>
          </button>
          <button
            type="button"
            onClick={() => onFocus(tab.tab_id)}
            aria-label={`Focus the subtree at ${tab.hier_number}`}
            className="ml-auto shrink-0 text-shadow-1 hover:text-ink dark:hover:text-bright px-0.5"
          >
            ⌄
          </button>
        </div>
      ))}
    </>
  );
}

export default DocumentTabStrip;
