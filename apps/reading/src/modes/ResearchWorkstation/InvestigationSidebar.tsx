import { useState } from "react";
import { NavLink, useParams } from "react-router-dom";

import { useInvestigationList } from "../../hooks/useInvestigationList";
import { useInvestigationTree } from "../../hooks/useInvestigationTree";
import type { TreeNode } from "../../hooks/useInvestigationTree";
import type { InvestigationSummary } from "../../lib/api";

/**
 * Left sidebar showing past investigations as a tree. Each node carries
 * its question (truncated), status badge, and total cost. Click any
 * node to navigate to /inv/<id>.
 *
 * The tree is built from substrate-side parent_investigation_id fields
 * (canonical) with localStorage as a defensive secondary source — see
 * useInvestigationTree.
 */
export default function InvestigationSidebar() {
  const { investigations, loading, error, refetch } = useInvestigationList();
  const tree = useInvestigationTree(investigations);
  const params = useParams<{ investigationId?: string }>();
  const activeId = params.investigationId ?? null;

  return (
    <div className="p-3 text-xs">
      <div className="flex items-center justify-between mb-3">
        <div className="font-mono text-stone-700 font-semibold uppercase tracking-wider">
          Investigations
        </div>
        <button
          onClick={refetch}
          className="text-stone-400 hover:text-stone-900 transition-colors"
          aria-label="Refresh"
        >
          ⟳
        </button>
      </div>
      {loading && investigations.length === 0 && (
        <div className="text-stone-400 italic font-mono">Loading…</div>
      )}
      {error && (
        <div className="text-red-700 font-mono text-[10px]">{error}</div>
      )}
      {!loading && investigations.length === 0 && !error && (
        <div className="text-stone-400 italic font-serif">
          No investigations yet. Ask a question to start.
        </div>
      )}
      <ul className="space-y-1">
        {tree.map((node) => (
          <TreeRow key={node.investigationId} node={node} depth={0} activeId={activeId} />
        ))}
      </ul>
    </div>
  );
}

function TreeRow({
  node,
  depth,
  activeId,
}: {
  node: TreeNode;
  depth: number;
  activeId: string | null;
}) {
  const [expanded, setExpanded] = useState(true);
  const summary = node.summary;
  const isActive = activeId === node.investigationId;
  return (
    <li>
      <div className="flex items-start gap-1.5">
        {node.children.length > 0 ? (
          <button
            onClick={() => setExpanded((v) => !v)}
            className="text-stone-400 hover:text-stone-700 transition-colors w-3 text-center text-[10px] mt-1 shrink-0"
            aria-label={expanded ? "Collapse" : "Expand"}
          >
            {expanded ? "▾" : "▸"}
          </button>
        ) : (
          <span className="w-3 shrink-0" />
        )}
        <NavLink
          to={`/inv/${node.investigationId}`}
          className={`flex-1 min-w-0 py-1 px-1.5 rounded transition-colors ${
            isActive
              ? "bg-stone-200 text-stone-900"
              : "hover:bg-stone-100 text-stone-700"
          }`}
          style={{ marginLeft: depth * 8 }}
        >
          <div className="flex items-start gap-1.5">
            <StatusDot status={summary?.status ?? "in_progress"} />
            <div className="flex-1 min-w-0">
              <div className="font-serif leading-snug truncate">
                {truncate(summary?.question ?? node.investigationId, 60)}
              </div>
              <div className="font-mono text-[9px] text-stone-400 mt-0.5">
                {summary?.cost_usd_total
                  ? `$${summary.cost_usd_total.toFixed(4)}`
                  : "$0"}
                {summary?.started_at && ` · ${formatRelative(summary.started_at)}`}
              </div>
            </div>
          </div>
        </NavLink>
      </div>
      {expanded && node.children.length > 0 && (
        <ul className="space-y-1 mt-1">
          {node.children.map((child) => (
            <TreeRow
              key={child.investigationId}
              node={child}
              depth={depth + 1}
              activeId={activeId}
            />
          ))}
        </ul>
      )}
    </li>
  );
}

function StatusDot({ status }: { status: InvestigationSummary["status"] }) {
  const color =
    status === "in_progress"
      ? "bg-amber-400 animate-pulse"
      : status === "completed"
        ? "bg-emerald-500"
        : status === "failed"
          ? "bg-red-500"
          : "bg-stone-400";
  return (
    <span
      className={`w-1.5 h-1.5 rounded-full mt-1.5 shrink-0 ${color}`}
      aria-label={status}
    />
  );
}

function truncate(s: string, n: number): string {
  if (s.length <= n) return s;
  return s.slice(0, n - 1) + "…";
}

function formatRelative(iso: string): string {
  try {
    const then = new Date(iso).getTime();
    const ago = Date.now() - then;
    const seconds = Math.floor(ago / 1000);
    if (seconds < 60) return `${seconds}s ago`;
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return `${minutes}m ago`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours}h ago`;
    const days = Math.floor(hours / 24);
    if (days < 30) return `${days}d ago`;
    return new Date(iso).toLocaleDateString();
  } catch {
    return "";
  }
}
