import {
  useCallback,
  useEffect,
  useId,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
  type MutableRefObject,
} from "react";
import { Link, useParams } from "react-router-dom";

import { useInvestigationList } from "../../hooks/useInvestigationList";
import { useInvestigationTree } from "../../hooks/useInvestigationTree";
import type { TreeNode } from "../../hooks/useInvestigationTree";
import type { InvestigationSummary } from "../../lib/api";

import "./research-index-sidebar.css";

export type { TreeNode };

const STATUS_LABELS: Record<InvestigationSummary["status"], string> = {
  in_progress: "in progress",
  completed: "completed",
  failed: "failed",
  stopped: "stopped",
  not_found: "not found",
};

function formatRelative(iso: string | null, nowMs: number): string {
  if (!iso) return "";
  try {
    const then = new Date(iso).getTime();
    if (!Number.isFinite(then)) return "";
    const ago = nowMs - then;
    if (ago < 0) return "";
    const seconds = Math.floor(ago / 1000);
    if (seconds < 60) return `${seconds}s ago`;
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return `${minutes}m ago`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours}h ago`;
    const days = Math.floor(hours / 24);
    if (days < 30) return `${days}d ago`;
    return new Date(then).toISOString().slice(0, 10);
  } catch {
    return "";
  }
}

function truncate(s: string, n: number): string {
  if (s.length <= n) return s;
  return s.slice(0, n - 1) + "\u2026";
}

/**
 * Keep data, lineage, and route authority in the existing production hooks;
 * the exported view is only a deterministic rendering seam.
 */
export default function InvestigationSidebar() {
  const { investigations, loading, error, refetch } = useInvestigationList();
  const tree = useInvestigationTree(investigations);
  const params = useParams<{ investigationId?: string }>();
  const activeId = params.investigationId ?? null;

  return (
    <ResearchIndexView
      tree={tree}
      activeId={activeId}
      loading={loading}
      error={error}
      onRefresh={refetch}
    />
  );
}

export interface ResearchIndexViewProps {
  tree: TreeNode[];
  activeId: string | null;
  loading: boolean;
  error: string | null;
  onRefresh: () => void;
  /** Fixed clock for deterministic age display. Production naturally
   *  uses Date.now(); fixtures pin this. */
  nowMs?: number;
  /** Story/test seam; production preserves the current all-expanded default. */
  initialExpandedIds?: Iterable<string>;
}

interface TreeIndex {
  nodes: Map<string, TreeNode>;
  parents: Map<string, string>;
  parentIds: Set<string>;
}

function indexTree(tree: TreeNode[]): TreeIndex {
  const nodes = new Map<string, TreeNode>();
  const parents = new Map<string, string>();
  const parentIds = new Set<string>();
  const visit = (items: TreeNode[], parentId?: string, ancestors = new Set<string>()) => {
    for (const node of items) {
      const id = node.investigationId;
      if (nodes.has(id) || ancestors.has(id)) continue;
      nodes.set(id, node);
      if (parentId) parents.set(id, parentId);
      if (node.children.length > 0) parentIds.add(id);
      visit(node.children, id, new Set([...ancestors, id]));
    }
  };
  visit(tree);
  return { nodes, parents, parentIds };
}

function visiblePreorder(tree: TreeNode[], expandedIds: Set<string>): string[] {
  const result: string[] = [];
  const seen = new Set<string>();
  const visit = (items: TreeNode[]) => {
    for (const node of items) {
      const id = node.investigationId;
      if (seen.has(id)) continue;
      seen.add(id);
      result.push(id);
      if (expandedIds.has(id)) visit(node.children);
    }
  };
  visit(tree);
  return result;
}

function ancestorChain(activeId: string | null, index: TreeIndex): string[] {
  if (!activeId || !index.nodes.has(activeId)) return [];
  const chain: string[] = [];
  const seen = new Set<string>([activeId]);
  let current = index.parents.get(activeId);
  while (current && !seen.has(current)) {
    chain.unshift(current);
    seen.add(current);
    current = index.parents.get(current);
  }
  return chain;
}

export function ResearchIndexView({
  tree,
  activeId,
  loading,
  error,
  onRefresh,
  nowMs = Date.now(),
  initialExpandedIds,
}: ResearchIndexViewProps) {
  const hasRows = tree.length > 0;
  const isInitialLoading = loading && !hasRows;
  const isStale = !!error && hasRows;
  const isTerminalError = !!error && !hasRows;
  const index = useMemo(() => indexTree(tree), [tree]);
  const [expandedIds, setExpandedIds] = useState<Set<string>>(
    () => new Set(initialExpandedIds ?? index.parentIds),
  );
  const initialFocusId = activeId && index.nodes.has(activeId)
    ? activeId
    : tree[0]?.investigationId ?? null;
  const [focusedId, setFocusedId] = useState<string | null>(initialFocusId);
  const rowRefs = useRef(new Map<string, HTMLDivElement>());
  const linkRefs = useRef(new Map<string, HTMLAnchorElement>());
  const treeRootRef = useRef<HTMLUListElement>(null);
  const treeHasFocus = useRef(false);
  const restoreAfterTreeChange = useRef(false);
  const focusedIdRef = useRef(focusedId);
  focusedIdRef.current = focusedId;
  const knownParents = useRef(new Set(index.parentIds));
  const revealedChain = useRef("");

  const visibleIds = useMemo(
    () => visiblePreorder(tree, expandedIds),
    [tree, expandedIds],
  );
  const activeAncestors = useMemo(
    () => ancestorChain(activeId, index),
    [activeId, index],
  );
  const activeChainSignature = activeId && index.nodes.has(activeId)
    ? `${activeId}:${activeAncestors.join("/")}`
    : "";
  const treeMembershipSignature = [...index.nodes.keys()].join("\u0000");

  useEffect(() => {
    const clearForOutsideTarget = (event: Event) => {
      const target = event.target;
      if (target instanceof Node && !treeRootRef.current?.contains(target)) {
        treeHasFocus.current = false;
      }
    };
    document.addEventListener("pointerdown", clearForOutsideTarget);
    document.addEventListener("focusin", clearForOutsideTarget);
    return () => {
      document.removeEventListener("pointerdown", clearForOutsideTarget);
      document.removeEventListener("focusin", clearForOutsideTarget);
    };
  }, []);

  useLayoutEffect(() => () => {
    const current = focusedIdRef.current;
    if (current && rowRefs.current.get(current) === document.activeElement) {
      restoreAfterTreeChange.current = true;
    }
  }, [treeMembershipSignature]);

  useEffect(() => {
    const additions = [...index.parentIds].filter((id) => !knownParents.current.has(id));
    knownParents.current = new Set(index.parentIds);
    if (additions.length === 0) return;
    setExpandedIds((previous) => new Set([...previous, ...additions]));
  }, [index]);

  useEffect(() => {
    if (!activeChainSignature) {
      revealedChain.current = "";
      return;
    }
    if (revealedChain.current === activeChainSignature) return;
    revealedChain.current = activeChainSignature;
    setExpandedIds((previous) => new Set([...previous, ...activeAncestors]));
  }, [activeAncestors, activeChainSignature]);

  useEffect(() => {
    if (visibleIds.length === 0) {
      if (focusedId !== null) setFocusedId(null);
      return;
    }
    if (focusedId && visibleIds.includes(focusedId)) return;
    const fallback = activeId && visibleIds.includes(activeId) ? activeId : visibleIds[0];
    const restoreDomFocus = focusedId !== null
      && (treeHasFocus.current || restoreAfterTreeChange.current);
    restoreAfterTreeChange.current = false;
    setFocusedId(fallback);
    if (restoreDomFocus) queueMicrotask(() => rowRefs.current.get(fallback)?.focus());
  }, [activeId, focusedId, visibleIds]);

  const focusRow = useCallback((id: string) => {
    setFocusedId(id);
    rowRefs.current.get(id)?.focus();
  }, []);

  const containsFocusedDescendant = useCallback((id: string): boolean => {
    let current = focusedId ? index.parents.get(focusedId) : undefined;
    const seen = new Set<string>();
    while (current && !seen.has(current)) {
      if (current === id) return true;
      seen.add(current);
      current = index.parents.get(current);
    }
    return false;
  }, [focusedId, index]);

  const toggleExpanded = useCallback((id: string) => {
    if (expandedIds.has(id) && containsFocusedDescendant(id)) {
      setFocusedId(id);
      // Pointer activation focuses the disclosure after its click handler;
      // restore the roving treeitem once that native focus step completes.
      queueMicrotask(() => rowRefs.current.get(id)?.focus());
    }
    setExpandedIds((previous) => {
      const next = new Set(previous);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }, [containsFocusedDescendant, expandedIds]);

  const handleTreeKeyDown = useCallback((event: KeyboardEvent<HTMLDivElement>, id: string) => {
    const node = index.nodes.get(id);
    if (!node) return;
    const position = visibleIds.indexOf(id);
    let destination: string | undefined;
    switch (event.key) {
      case "ArrowDown":
        destination = visibleIds[position + 1];
        break;
      case "ArrowUp":
        destination = visibleIds[position - 1];
        break;
      case "Home":
        destination = visibleIds[0];
        break;
      case "End":
        destination = visibleIds.at(-1);
        break;
      case "ArrowRight":
        if (node.children.length > 0 && !expandedIds.has(id)) {
          setExpandedIds((previous) => new Set([...previous, id]));
        } else if (node.children.length > 0) {
          destination = node.children[0]?.investigationId;
        }
        break;
      case "ArrowLeft":
        if (node.children.length > 0 && expandedIds.has(id)) {
          setExpandedIds((previous) => {
            const next = new Set(previous);
            next.delete(id);
            return next;
          });
        } else {
          destination = index.parents.get(id);
        }
        break;
      case "Enter":
        linkRefs.current.get(id)?.click();
        break;
      default:
        return;
    }
    event.preventDefault();
    if (destination) focusRow(destination);
  }, [expandedIds, focusRow, index, visibleIds]);

  return (
    <nav className="ris" aria-label="Research index" aria-busy={loading}>
      <div className="ris__header">
        <h2 className="ris__title">Research index</h2>
        <button
          onClick={onRefresh}
          className="ris__refresh"
          aria-label="Refresh investigations"
        >
          <span className="ris__refresh-icon" aria-hidden="true">
            &#x27F3;
          </span>
        </button>
      </div>

      {isStale && (
        <div className="ris__stale" role="status">
          Could not refresh — showing cached data.
        </div>
      )}

      {isInitialLoading && (
        <div className="ris__loading" role="status" aria-live="polite">
          Loading research index&hellip;
        </div>
      )}

      {isTerminalError && (
        <div role="alert">
          <div className="ris__error">{error}</div>
          <button className="ris__retry" onClick={onRefresh}>
            Retry
          </button>
        </div>
      )}

      {!loading && !error && tree.length === 0 && (
        <div className="ris__empty">
          No investigations yet. Ask a question to start.
        </div>
      )}

      {tree.length > 0 && (
        <ul
          className="ris__tree"
          role="tree"
          aria-label="Investigations"
          ref={treeRootRef}
          onFocusCapture={() => { treeHasFocus.current = true; }}
        >
          {tree.map((node) => (
            <TreeRow
              key={node.investigationId}
              node={node}
              depth={0}
              activeId={activeId}
              nowMs={nowMs}
              expandedIds={expandedIds}
              focusedId={focusedId}
              setFocusedId={setFocusedId}
              toggleExpanded={toggleExpanded}
              onKeyDown={handleTreeKeyDown}
              rowRefs={rowRefs}
              linkRefs={linkRefs}
            />
          ))}
        </ul>
      )}
    </nav>
  );
}

function TreeRow({
  node,
  depth,
  activeId,
  nowMs,
  expandedIds,
  focusedId,
  setFocusedId,
  toggleExpanded,
  onKeyDown,
  rowRefs,
  linkRefs,
}: {
  node: TreeNode;
  depth: number;
  activeId: string | null;
  nowMs: number;
  expandedIds: Set<string>;
  focusedId: string | null;
  setFocusedId: (id: string) => void;
  toggleExpanded: (id: string) => void;
  onKeyDown: (event: KeyboardEvent<HTMLDivElement>, id: string) => void;
  rowRefs: MutableRefObject<Map<string, HTMLDivElement>>;
  linkRefs: MutableRefObject<Map<string, HTMLAnchorElement>>;
}) {
  const childrenId = `research-index-children-${useId().replace(/:/g, "")}`;
  const summary = node.summary;
  const isActive = activeId === node.investigationId;
  const hasChildren = node.children.length > 0;
  const expanded = expandedIds.has(node.investigationId);
  const status = summary?.status ?? "unknown";
  const statusLabel = status === "unknown" ? "status unavailable" : STATUS_LABELS[status];
  const age = formatRelative(summary?.started_at ?? null, nowMs);

  return (
    <li data-depth={depth} role="none">
      <div
        className="ris__row"
        role="treeitem"
        aria-level={depth + 1}
        aria-expanded={hasChildren ? expanded : undefined}
        tabIndex={focusedId === node.investigationId ? 0 : -1}
        onFocus={(event) => {
          if (event.target === event.currentTarget) setFocusedId(node.investigationId);
        }}
        onKeyDown={(event) => {
          if (event.target === event.currentTarget) onKeyDown(event, node.investigationId);
        }}
        ref={(element) => {
          if (element) rowRefs.current.set(node.investigationId, element);
          else rowRefs.current.delete(node.investigationId);
        }}
      >
        {hasChildren ? (
          <button
            onClick={(event) => {
              event.stopPropagation();
              toggleExpanded(node.investigationId);
            }}
            className="ris__disclosure"
            aria-label={expanded ? "Collapse" : "Expand"}
            aria-expanded={expanded}
            aria-controls={childrenId}
            tabIndex={-1}
          >
            {expanded ? "\u25BE" : "\u25B8"}
          </button>
        ) : (
          <span className="ris__leaf-spacer" aria-hidden="true" />
        )}
        <Link
          to={`/inv/${node.investigationId}`}
          className={`ris__link${isActive ? " ris__link--active" : ""}`}
          aria-current={isActive ? "page" : undefined}
          tabIndex={-1}
          title={summary?.question ?? node.investigationId}
          onClick={() => setFocusedId(node.investigationId)}
          ref={(element) => {
            if (element) linkRefs.current.set(node.investigationId, element);
            else linkRefs.current.delete(node.investigationId);
          }}
        >
          <div className="ris__status">
            <span
              className={`ris__status-shape ris__status-shape--${status}`}
              aria-hidden="true"
            />
            <span className="ris__status-label">{statusLabel}</span>
          </div>
          <div className="ris__body">
            <div className="ris__question">
              {truncate(summary?.question ?? node.investigationId, 60)}
            </div>
            <div className="ris__meta">
              {summary?.cost_usd_total != null
                ? `$${summary.cost_usd_total.toFixed(4)}`
                : "cost unavailable"}
              {age ? ` \u00B7 ${age}` : null}
            </div>
          </div>
        </Link>
      </div>
      {hasChildren && (
        <ul id={childrenId} className="ris__tree" role="group" hidden={!expanded}>
          {node.children.map((child) => (
            <TreeRow
              key={child.investigationId}
              node={child}
              depth={depth + 1}
              activeId={activeId}
              nowMs={nowMs}
              expandedIds={expandedIds}
              focusedId={focusedId}
              setFocusedId={setFocusedId}
              toggleExpanded={toggleExpanded}
              onKeyDown={onKeyDown}
              rowRefs={rowRefs}
              linkRefs={linkRefs}
            />
          ))}
        </ul>
      )}
    </li>
  );
}
