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
 *   route → tree: routeSync (documentSpace.adoptTabForRoute) — an open tab that shows
 *     the route is adopted before a root is seeded, so a child stays a child.
 *     Its activations are "route" activations: they follow a navigation and
 *     never start one;
 *   tree → route: only a USER activation (strip, keys, the cross-pane seam)
 *     navigates, through the store's navIntent, and only when the route does
 *     not already show the tab. Nothing is inferred from which tab happens
 *     to be active, so a mode switch, a reload or a load never hijacks the
 *     navigation that brought the operator here (F-04).
 *
 * Test/story seam: without a Router context the strip renders nothing (it
 * exists to navigate). DocumentTabStripView is the presentational half the
 * stories render with a fixed tree.
 */
import { useCallback, useEffect, useMemo, useRef } from "react";
import { useInRouterContext, useLocation, useNavigate } from "react-router-dom";
import { CornerDownRight, ListTree } from "lucide-react";

import { ErrorState, LoadingState } from "../components/states";
import { branchIntentOf } from "./branchNavigation";
import { mothershipForPath, routeForTab, routeTabFor, tabShowsPath } from "./documentSpace";
import { MODE_HOME } from "./mothershipForPath";
import { syncRouteToTree } from "./routeSync";
import { sectionIdFromRef } from "./sectionRef";
import { SiblingStrip } from "./SiblingStrip";
import { TabPathHeader } from "./TabPathHeader";
import { TabTreePanel } from "./TabTreePanel";
import { labelForTab, type TabLabel } from "./tabLabels";
import { useForkLineage } from "./forkLineage";
import { DOCUMENT_PANEL_ID, domIdFor } from "./tabStripParts";
import { requestTabTitle, titleKey, useTabTitles, type TitleEntry } from "./tabTitles";
import { pathTo, type TabNode, type TabTree } from "./tabTree";
import { locationStamp, useTabTrees } from "./tabTreeStore";

export { labelForTab };

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

  // Keyed by the history entry, so a branch navigation to a surface already
  // on screen elsewhere still files under its parent.
  const intent = branchIntentOf(location.state);
  useEffect(() => {
    void syncRouteToTree(mothership, location.pathname, intent);
    // `intent` is derived from the entry `location.key` names.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.pathname, location.key, mothership]);

  // tree → route: a USER activation's intent, taken once. An intent left
  // behind by a newer activation, or by a tab the route sync has since moved
  // off, shows nothing.
  const navIntent = useTabTrees((s) => s.navIntent);
  useEffect(() => {
    if (!navIntent) return;
    const store = useTabTrees.getState();
    store.consumeNavIntent(navIntent.seq);
    const t = store.trees[navIntent.mothership];
    if (!t || t.active_tab_id !== navIntent.tabId) return;
    // Issued at another history entry: the operator navigated since (an
    // agent open made before this strip loaded, then a click elsewhere).
    // Their navigation wins.
    if (navIntent.at !== locationStamp()) return;
    // The last open tab closed: the mode's home, never the closed surface
    // left on screen under "No open tabs".
    if (navIntent.tabId === null) {
      const home = MODE_HOME[navIntent.mothership];
      if (location.pathname + location.search !== home) navigate(home);
      return;
    }
    // A Write section navigates to its piece (it scopes that piece in place),
    // so a section of another piece never leaves this piece on screen.
    const holder = routeTabFor(t, navIntent.tabId);
    if (!holder) return;
    if (navIntent.mothership === mothership && tabShowsPath(holder, location.pathname)) return;
    const route = routeForTab(holder);
    if (route) navigate(route);
  }, [navIntent, mothership, location.pathname, location.search, navigate]);

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

  // SPR-01 (thread-merge + document fork), verdict C: the fork badge and
  // the forks chip, for the ACTIVE tab when it is a reader tab. The lineage
  // is the session's learned view (forkLineage.ts) — the reader mount feeds
  // it; an unknown neighbourhood renders nothing, never a wrong badge.
  const activeTab = tree?.active_tab_id ? tree.nodes[tree.active_tab_id] : null;
  const activeRef = activeTab?.kind === "reader" ? activeTab.ref : null;
  const forkedFrom = useForkLineage((s) =>
    activeRef !== null ? (s.byFork[activeRef] ?? null) : null,
  );
  const forksOfActive = useForkLineage((s) =>
    activeRef !== null ? (s.byParent[activeRef] ?? null) : null,
  );
  // The hop: an already-open tab for the document is ACTIVATED (the badge
  // hops between the two tabs); otherwise the document opens on its route
  // and the route sync files the tab.
  const openDocument = useCallback(
    (documentId: string) => {
      const t = useTabTrees.getState().trees[mothership];
      const open = t
        ? Object.values(t.nodes).find((n) => n.kind === "reader" && n.ref === documentId)
        : null;
      if (t && open) {
        useTabTrees.getState().activateTab(mothership, open.tab_id);
        return;
      }
      navigate(`/read/${encodeURIComponent(documentId)}`);
    },
    [mothership, navigate],
  );

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
      forkBadge={
        forkedFrom
          ? {
              parentDocumentId: forkedFrom.parent_document_id,
              parentTitle: forkedFrom.parent_title,
            }
          : null
      }
      forkDocumentIds={forksOfActive?.map((row) => row.fork_document_id) ?? null}
      onOpenDocument={openDocument}
      onActivate={activate}
      onToggleTree={() => useTabTrees.getState().toggleTreePanel()}
      onFocusSubtree={(id) => useTabTrees.getState().setSubtreeFocus(id)}
      onVisitChild={() => useTabTrees.getState().visitChildOfActive(mothership)}
      onRowsShown={requestRows}
      onCloseTab={(id, mode) => useTabTrees.getState().closeTabById(mothership, id, mode)}
    />
  );
}

function isSectionTab(tab: TabNode): boolean {
  return tab.kind === "document" && sectionIdFromRef(tab.ref) !== null;
}

function siblingsOf(tree: TabTree | null | undefined): readonly string[] {
  const active = tree?.active_tab_id ? tree.nodes[tree.active_tab_id] : null;
  if (!tree || !active) return tree ? tree.root_order : [];
  return active.parent_tab_id === null
    ? tree.root_order
    : (tree.nodes[active.parent_tab_id]?.child_order ?? []);
}

export type StripStatus = "loading" | "error" | "ready";

/** The strip's own surface: in the docked preset nothing opaque sits behind
 *  it, so without it the scene showed through the tabs (B3-10). The inset
 *  pane shell is the same colour, so the strip reads as one with the pane. */
const STRIP_SURFACE = "bg-ice-1 dark:bg-charcoal-1";

export interface DocumentTabStripViewProps {
  status: StripStatus;
  errorDetail?: string | null;
  onRetry: () => void;
  tree: TabTree | null | undefined;
  labelOf: (tabId: string) => TabLabel;
  treePanelOpen: boolean;
  subtreeFocusId: string | null;
  /** SPR-01 verdict C: the active tab IS a fork — the badge hops to the
   *  original. */
  forkBadge?: { parentDocumentId: string; parentTitle: string | null } | null;
  /** SPR-01 verdict C: the active tab HAS forks — the chip hops to the
   *  latest one (creation order from the lineage store). */
  forkDocumentIds?: string[] | null;
  onOpenDocument?: (documentId: string) => void;
  onActivate: (tabId: string) => void;
  onToggleTree: () => void;
  onFocusSubtree: (tabId: string | null) => void;
  onVisitChild: () => void;
  onRowsShown?: (tabIds: string[]) => void;
  /** The tree panel's Delete / Shift+Delete (prune / close only this). */
  onCloseTab?: (tabId: string, mode: "prune" | "lift_children") => void;
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
  forkBadge = null,
  forkDocumentIds = null,
  onOpenDocument,
  onActivate,
  onToggleTree,
  onFocusSubtree,
  onVisitChild,
  onRowsShown,
  onCloseTab,
}: DocumentTabStripViewProps) {
  const toggleRef = useRef<HTMLButtonElement>(null);
  const rootRef = useRef<HTMLDivElement>(null);

  // The tree panel is a popover: a press anywhere outside the strip closes it
  // (the toggle is inside, and keeps its own toggling).
  useEffect(() => {
    if (!treePanelOpen) return;
    const onPointerDown = (e: PointerEvent) => {
      const root = rootRef.current;
      if (root && e.target instanceof Node && root.contains(e.target)) return;
      onToggleTree();
    };
    // Esc closes it from any focus, not only from inside it (the panel's
    // own rows handle their Esc and stop it there). It is the popover's
    // Esc alone: a pane fullscreen stays until the next one (escapeOverlay).
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key !== "Escape" || e.defaultPrevented) return;
      e.preventDefault();
      onToggleTree();
    };
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [treePanelOpen, onToggleTree]);

  if (status === "loading" || !tree) {
    if (status === "error") {
      return (
        <div data-document-strip className={`shrink-0 border-b border-hairline p-1.5 ${STRIP_SURFACE}`}>
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
      <div data-document-strip className={`shrink-0 border-b border-hairline ${STRIP_SURFACE}`}>
        <LoadingState variant="inline" shape="strip" rows={3} label="Opening your tabs" />
      </div>
    );
  }

  const active = tree.active_tab_id ? tree.nodes[tree.active_tab_id] : null;
  const path = active ? pathTo(tree, active.tab_id) : [];
  const siblings = siblingsOf(tree);
  const parent = active?.parent_tab_id ? tree.nodes[active.parent_tab_id] : null;
  const children = active ? active.child_order.filter((c) => Object.hasOwn(tree.nodes, c)) : [];
  // A kind with no route of its own opens as a window. A Write section is
  // the exception: it scopes the piece's view in place (WriteHome reads the
  // active tab), so it is a view of this page, never a window.
  const bridge = active !== null && routeForTab(active) === null && !isSectionTab(active);

  return (
    <div ref={rootRef} className={`relative shrink-0 ${STRIP_SURFACE}`} data-document-strip>
      {path.length > 1 ? (
        <TabPathHeader tree={tree} path={path} labelOf={labelOf} onActivate={onActivate} />
      ) : null}

      {/* One fixed height with or without tabs (B3-5): 28 px of tabs plus
          the hairline, the loading skeleton's height too, so neither the
          first tab nor the last close moves the page. */}
      <div data-strip-row className="flex items-stretch min-w-0 box-content h-7 border-b border-hairline">
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
            onShowAll={() => {
              if (!treePanelOpen) onToggleTree();
            }}
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

        {/* SPR-01 verdict C: lineage from the chrome itself. The fork badge
            answers "what is this, what did it come from" without opening
            anything; the forks chip answers the reverse from the source
            tab. Both HOP (open-or-activate), never mutate. */}
        {active && forkBadge && onOpenDocument ? (
          <button
            type="button"
            data-fork-badge
            onClick={() => onOpenDocument(forkBadge.parentDocumentId)}
            aria-label={`This tab is a fork of ${forkBadge.parentTitle?.trim() || "the original"}: open the original`}
            title="This tab is a fork — the original is untouched. Open it."
            className="shrink-0 ml-1 my-1 flex items-center gap-0.5 rounded px-1.5 font-mono text-xxs text-ink-soft dark:text-moonlight border border-hairline hover:bg-ice-2 dark:hover:bg-charcoal-1 focus-visible:outline focus-visible:outline-2 focus-visible:outline-sun"
          >
            fork of {forkBadge.parentTitle?.trim() || "the original"}
          </button>
        ) : null}
        {active && forkDocumentIds && forkDocumentIds.length > 0 && onOpenDocument ? (
          <button
            type="button"
            data-forks-chip
            onClick={() => onOpenDocument(forkDocumentIds[forkDocumentIds.length - 1])}
            aria-label={`${forkDocumentIds.length} fork${forkDocumentIds.length === 1 ? "" : "s"} of this document: open the latest`}
            title={`${forkDocumentIds.length} fork${forkDocumentIds.length === 1 ? "" : "s"} of this document — open the latest`}
            className="shrink-0 ml-1 my-1 flex items-center gap-0.5 rounded px-1.5 font-mono text-xxs text-ink-soft dark:text-moonlight border border-hairline hover:bg-ice-2 dark:hover:bg-charcoal-1 focus-visible:outline focus-visible:outline-2 focus-visible:outline-sun"
          >
            {forkDocumentIds.length} fork{forkDocumentIds.length === 1 ? "" : "s"} ▸
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
          data-esc-overlay=""
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
            onCloseTab={onCloseTab}
            focusOnOpen
          />
        </div>
      ) : null}
    </div>
  );
}

export default DocumentTabStrip;
