import { useId, useState } from "react";
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
}

export function ResearchIndexView({
  tree,
  activeId,
  loading,
  error,
  onRefresh,
  nowMs = Date.now(),
}: ResearchIndexViewProps) {
  const hasRows = tree.length > 0;
  const isInitialLoading = loading && !hasRows;
  const isStale = !!error && hasRows;
  const isTerminalError = !!error && !hasRows;

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
        <ul className="ris__tree">
          {tree.map((node) => (
            <TreeRow
              key={node.investigationId}
              node={node}
              depth={0}
              activeId={activeId}
              nowMs={nowMs}
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
}: {
  node: TreeNode;
  depth: number;
  activeId: string | null;
  nowMs: number;
}) {
  const [expanded, setExpanded] = useState(true);
  const childrenId = `research-index-children-${useId().replace(/:/g, "")}`;
  const summary = node.summary;
  const isActive = activeId === node.investigationId;
  const hasChildren = node.children.length > 0;
  const status = summary?.status ?? "unknown";
  const statusLabel = status === "unknown" ? "status unavailable" : STATUS_LABELS[status];
  const age = formatRelative(summary?.started_at ?? null, nowMs);

  return (
    <li data-depth={depth}>
      <div className="ris__row">
        {hasChildren ? (
          <button
            onClick={() => setExpanded((v) => !v)}
            className="ris__disclosure"
            aria-label={expanded ? "Collapse" : "Expand"}
            aria-expanded={expanded}
            aria-controls={childrenId}
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
          title={summary?.question ?? node.investigationId}
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
        <ul id={childrenId} className="ris__tree" hidden={!expanded}>
          {node.children.map((child) => (
            <TreeRow
              key={child.investigationId}
              node={child}
              depth={depth + 1}
              activeId={activeId}
              nowMs={nowMs}
            />
          ))}
        </ul>
      )}
    </li>
  );
}
