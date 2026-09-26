/**
 * DocumentTabStrip — the cockpit's left document tabs (D6, DESIGN-MODEL §2a).
 *
 * Mounted ONCE in PanelLayout's shared centre column, so both presets and
 * every route's mothership get it. From the top:
 *
 *   - the PATH HEADER (TabPathHeader), root → active tab, compressed past
 *     four crumbs; shown once the active tab has a parent;
 *   - the SIBLING STRIP (SiblingStrip): the active tab and its siblings as an
 *     ARIA tablist controlling the route content, the tree toggle before it
 *     and a `↳ n` chip after it for the active tab's children;
 *   - the TREE PANEL (TabTreePanel, prefix t): the whole forest.
 *
 * Labels are titles derived from each tab's ref (tabTitles + tabLabels),
 * never a raw id. Close is held for 10 s behind a LemonToast Undo
 * (tabTreeStore). Loading, empty and error use the shared state primitives.
 *
 * Tabs are navigation state: ACTIVATING a tab navigates to its canonical
 * route (routeForTab). Two sync directions, both loop-safe:
 *   route → tree: documentSpace.adoptTabForRoute — an open tab that shows
 *     the route is adopted before a root is seeded, so a child stays a child;
 *   tree → route: an activation (strip, keys, the cross-pane seam) navigates
 *     to the tab's route unless the route already shows it.
 *
 * Test/story seam: without a Router context the strip renders nothing (it
 * exists to navigate). DocumentTabStripView is the presentational half the
 * stories render with a fixed tree.
 */
import { useCallback, useEffect, useMemo, useRef } from "react";
import { useInRouterContext, useLocation, useNavigate } from "react-router-dom";
import { CornerDownRight, ListTree } from "lucide-react";

import { ErrorState, LoadingState } from "../components/states";
import {
  adoptTabForRoute,
  freshTabId,
  mothershipForPath,
  rootTabId,
  routeForTab,
  tabShowsPath,
} from "./documentSpace";
import { SiblingStrip } from "./SiblingStrip";
import { TabPathHeader } from "./TabPathHeader";
import { TabTreePanel } from "./TabTreePanel";
import { labelForTab, type TabLabel } from "./tabLabels";
import { DOCUMENT_PANEL_ID, domIdFor } from "./tabStripParts";
import { requestTabTitle, titleKey, useTabTitles, type TitleEntry } from "./tabTitles";
import { pathTo, type Mothership, type TabTree } from "./tabTree";
import { useTabTrees } from "./tabTreeStore";

export { labelForTab };

/** The route → tree sync, shared by the route effect and "Try again". */
async function syncRouteToTree(mothership: Mothership, pathname: string): Promise<void> {
  await useTabTrees.getState().ensureMothership(mothership);
  const store = useTabTrees.getState();
  const tree = store.trees[mothership];
  if (!tree) return;
  const adoption = adoptTabForRoute(tree, pathname);
  if (adoption.action === "activate") store.activateTab(mothership, adoption.tabId);
  else if (adoption.action === "seed") {
    store.spawnTab(mothership, null, {
      tab_id: freshTabId(tree, rootTabId(adoption.ref)),
      kind: adoption.ref.kind,
      ref: adoption.ref.ref,
      mothership,
      activate: true,
    });
  }
}

export function labelsFor(
  tree: TabTree | null,
  entries: Record<string, TitleEntry>,
): (tabId: string) => TabLabel {
  return (tabId) => {
    const tab = tree!.nodes[tabId];
    const parent = tab.parent_tab_id ? tree!.nodes[tab.parent_tab_id] : null;
    return labelForTab(tab, parent, entries[titleKey(tab.kind, tab.ref)]);
  };
}

export function DocumentTabStrip() {
  // The guard is an OUTER component because hooks cannot be conditional.
  if (!useInRouterContext()) return null;
  return <DocumentTabStripInner />;
}

function DocumentTabStripInner() {
  const location = useLocation();
  const navigate = useNavigate();
  const mothership = mothershipForPath(location.pathname, location.search);

  const tree = useTabTrees((s) => s.trees[mothership]);
  const loadError = useTabTrees((s) => s.loadError[mothership]);
  const treePanelOpen = useTabTrees((s) => s.treePanelOpen);
  const subtreeFocusId = useTabTrees((s) => s.subtreeFocusId);
  const entries = useTabTitles((s) => s.entries);

  useEffect(() => {
    void syncRouteToTree(mothership, location.pathname);
  }, [location.pathname, mothership]);

  // tree → route: only an ACTIVATION navigates. Whatever was active when
  // the strip mounted is not a mandate to hijack the current route.
  const activeTab = tree?.active_tab_id ? tree.nodes[tree.active_tab_id] : null;
  const prevActiveRef = useRef<string | null>(activeTab?.tab_id ?? null);
  useEffect(() => {
    const id = activeTab?.tab_id ?? null;
    if (id === prevActiveRef.current) return;
    prevActiveRef.current = id;
    if (!activeTab || tabShowsPath(activeTab, location.pathname)) return;
    const route = routeForTab(activeTab);
    if (route) navigate(route);
  }, [activeTab, location.pathname, navigate]);

  // Activation only moves the tree; the effect above does the navigating,
  // so a click, a key and the cross-pane seam take one path.
  const activate = useCallback(
    (tabId: string) => useTabTrees.getState().activateTab(mothership, tabId),
    [mothership],
  );

  const labelOf = useMemo(() => labelsFor(tree, entries), [tree, entries]);

  // Titles resolve for what is on screen: the path, the siblings, the
  // active tab's children (the chip's tooltip); the panel asks for its rows.
  const path = tree && tree.active_tab_id ? pathTo(tree, tree.active_tab_id) : [];
  const siblings = siblingsOf(tree);
  const visibleKey = [...path, ...siblings].join("\u0000");
  useEffect(() => {
    if (!tree) return;
    for (const id of new Set([...path, ...siblings])) requestTabTitle(tree.nodes[id]);
    // visibleKey stands for path + siblings.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [visibleKey, tree]);
  const requestRows = useCallback(
    (ids: string[]) => {
      const t = useTabTrees.getState().trees[mothership];
      if (!t) return;
      for (const id of ids) if (t.nodes[id]) requestTabTitle(t.nodes[id]);
    },
    [mothership],
  );

  // The route content is the tabpanel the selected tab controls.
  const selectedDomId = tree?.active_tab_id ? domIdFor("doctab", tree.active_tab_id) : null;
  useEffect(() => {
    const panel = document.getElementById(DOCUMENT_PANEL_ID);
    if (!panel || !selectedDomId) return;
    panel.setAttribute("role", "tabpanel");
    panel.setAttribute("aria-labelledby", selectedDomId);
    return () => {
      panel.removeAttribute("role");
      panel.removeAttribute("aria-labelledby");
    };
  }, [selectedDomId]);

  const status: StripStatus = tree ? "ready" : loadError ? "error" : "loading";

  return (
    <DocumentTabStripView
      status={status}
      errorDetail={loadError}
      onRetry={() => {
        void useTabTrees
          .getState()
          .retryLoad(mothership)
          .then(() => syncRouteToTree(mothership, window.location.pathname));
      }}
      tree={tree}
      labelOf={labelOf}
      treePanelOpen={treePanelOpen}
      subtreeFocusId={subtreeFocusId}
      onActivate={activate}
      onToggleTree={() => useTabTrees.getState().toggleTreePanel()}
      onFocusSubtree={(id) => useTabTrees.getState().setSubtreeFocus(id)}
      onVisitChild={() => useTabTrees.getState().visitChildOfActive(mothership)}
      onRowsShown={requestRows}
    />
  );
}

function siblingsOf(tree: TabTree | null | undefined): readonly string[] {
  const active = tree?.active_tab_id ? tree.nodes[tree.active_tab_id] : null;
  if (!tree || !active) return tree ? tree.root_order : [];
  return active.parent_tab_id === null
    ? tree.root_order
    : (tree.nodes[active.parent_tab_id]?.child_order ?? []);
}

export type StripStatus = "loading" | "error" | "ready";

export interface DocumentTabStripViewProps {
  status: StripStatus;
  errorDetail?: string | null;
  onRetry: () => void;
  tree: TabTree | null | undefined;
  labelOf: (tabId: string) => TabLabel;
  treePanelOpen: boolean;
  subtreeFocusId: string | null;
  onActivate: (tabId: string) => void;
  onToggleTree: () => void;
  onFocusSubtree: (tabId: string | null) => void;
  onVisitChild: () => void;
  onRowsShown?: (tabIds: string[]) => void;
}

/** The presentational strip: every state, no store, no router. */
export function DocumentTabStripView({
  status,
  errorDetail,
  onRetry,
  tree,
  labelOf,
  treePanelOpen,
  subtreeFocusId,
  onActivate,
  onToggleTree,
  onFocusSubtree,
  onVisitChild,
  onRowsShown,
}: DocumentTabStripViewProps) {
  const toggleRef = useRef<HTMLButtonElement>(null);

  if (status === "loading" || !tree) {
    if (status === "error") {
      return (
        <div data-document-strip className="shrink-0 border-b border-hairline p-1.5">
          <ErrorState
            variant="inline"
            title="Couldn't open your tabs"
            body="Your documents are untouched; only the list of open tabs didn't load."
            detail={errorDetail ?? null}
            onRetry={onRetry}
          />
        </div>
      );
    }
    return (
      <div data-document-strip className="shrink-0 border-b border-hairline">
        <LoadingState variant="inline" shape="strip" rows={3} label="Opening your tabs" />
      </div>
    );
  }

  const active = tree.active_tab_id ? tree.nodes[tree.active_tab_id] : null;
  const path = active ? pathTo(tree, active.tab_id) : [];
  const siblings = siblingsOf(tree);
  const parent = active?.parent_tab_id ? tree.nodes[active.parent_tab_id] : null;
  const children = active ? active.child_order.filter((c) => Object.hasOwn(tree.nodes, c)) : [];
  const bridge = active !== null && routeForTab(active) === null;

  return (
    <div className="relative shrink-0" data-document-strip>
      {path.length > 1 ? (
        <TabPathHeader tree={tree} path={path} labelOf={labelOf} onActivate={onActivate} />
      ) : null}

      <div className="flex items-stretch min-w-0 border-b border-hairline">
        <button
          ref={toggleRef}
          type="button"
          onClick={onToggleTree}
          aria-expanded={treePanelOpen}
          aria-controls="document-tab-tree"
          aria-label="Tab tree (prefix t)"
          title="All tabs (prefix t)"
          className="shrink-0 flex items-center px-2 text-shadow-1 dark:text-moonlight hover:bg-ice-2 dark:hover:bg-charcoal-1 hover:text-ink dark:hover:text-bright focus-visible:outline focus-visible:outline-2 focus-visible:outline-sun"
        >
          <ListTree size={14} strokeWidth={1.75} aria-hidden="true" />
        </button>

        {active ? (
          <SiblingStrip
            tree={tree}
            siblings={siblings}
            activeId={active.tab_id}
            label={parent ? `Tabs under ${parent.hier_number}` : "Top-level tabs"}
            labelOf={labelOf}
            onActivate={onActivate}
          />
        ) : (
          <span className="flex items-center px-1 text-xs text-shadow-1 dark:text-moonlight">
            No open tabs
          </span>
        )}

        {active && children.length > 0 ? (
          <button
            type="button"
            data-children-chip
            onClick={onVisitChild}
            aria-label={`${children.length} tab${children.length === 1 ? "" : "s"} under ${active.hier_number}: open the last visited (prefix o)`}
            title={`${children.length} under ${active.hier_number} (prefix o)`}
            className="shrink-0 ml-1 my-1 flex items-center gap-0.5 rounded px-1.5 font-mono text-xxs text-ink-soft dark:text-moonlight border border-hairline hover:bg-ice-2 dark:hover:bg-charcoal-1 focus-visible:outline focus-visible:outline-2 focus-visible:outline-sun"
          >
            <CornerDownRight size={11} aria-hidden="true" />
            {children.length}
          </button>
        ) : null}

        {bridge ? (
          <span
            className="shrink-0 ml-1 flex items-center text-xs text-shadow-1 dark:text-moonlight italic pr-2"
            data-tab-bridge
            title="This surface is route-bound — it opens as a window, never an embedding guess."
          >
            opens as window
          </span>
        ) : null}
      </div>

      {treePanelOpen ? (
        <div
          id="document-tab-tree"
          data-tab-tree-panel
          className="absolute left-0 top-full z-20 mt-0.5 w-[min(24rem,calc(100vw-2rem))] rounded border border-hairline bg-ice-0 dark:bg-charcoal-2 shadow-z2 dark:shadow-z2-night overflow-hidden"
        >
          <TabTreePanel
            tree={tree}
            focusId={subtreeFocusId}
            labelOf={labelOf}
            onActivate={onActivate}
            onFocusSubtree={onFocusSubtree}
            onClose={() => {
              onToggleTree();
              toggleRef.current?.focus();
            }}
            onRowsShown={onRowsShown}
          />
        </div>
      ) : null}
    </div>
  );
}

export default DocumentTabStrip;
