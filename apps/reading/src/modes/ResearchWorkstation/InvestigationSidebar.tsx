import { useState } from "react";
import { NavLink, useParams } from "react-router-dom";

import { useInvestigationList } from "../../hooks/useInvestigationList";
import { useInvestigationTree } from "../../hooks/useInvestigationTree";
import type { TreeNode } from "../../hooks/useInvestigationTree";
import type { InvestigationSummary } from "../../lib/api";
import { aggregateAttention } from "../../shared/attention";
import {
  isUnseen,
  researchStateDotClass,
  researchStateStyle,
} from "../../shared/researchState";
import { lastSeenAt } from "../../workspace/seen";
import { useSeenVersion } from "../../hooks/useSeenVersion";

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

  // P0-3 — unread state updates live when any surface marks seen.
  useSeenVersion();

  return (
    <div className="p-3 text-xs text-ink dark:text-bright">
      <div className="flex items-center justify-between mb-3">
        <div className="font-mono text-shadow-1 dark:text-moonlight font-semibold uppercase tracking-wider">
          Investigations
        </div>
        <button
          onClick={refetch}
          className="text-ink-mute dark:text-moonlight hover:text-ink dark:hover:text-bright transition-colors"
          aria-label="Refresh"
        >
          ⟳
        </button>
      </div>
      {loading && investigations.length === 0 && (
        <div className="text-ink-mute dark:text-moonlight italic font-mono">Loading…</div>
      )}
      {error && (
        <div className="text-emperor font-mono text-[10px]">{error}</div>
      )}
      {!loading && investigations.length === 0 && !error && (
        <div className="text-ink-mute dark:text-moonlight italic font-serif">
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

  // herdr transfer P0-2: a parent row rolls up its whole subtree — one
  // blocked child reddens the family. Leaf rows roll up to themselves.
  const subtree = collectSubtree(node);
  const states = subtree.map((s) => ({
    state: researchStateStyle(s.status).state,
    unseen: isUnseen(s, lastSeenAt(s.investigation_id)),
  }));
  const rollup =
    aggregateAttention(states) ??
    researchStateStyle(summary?.status ?? "not_found").state;
  const rollupUnseen = rollup === "done" && states.some((x) => x.unseen);
  const unseen =
    summary !== null && isUnseen(summary, lastSeenAt(summary.investigation_id));
  return (
    <li>
      <div className="flex items-start gap-1.5">
        {node.children.length > 0 ? (
          <button
            onClick={() => setExpanded((v) => !v)}
            className="text-ink-mute dark:text-moonlight hover:text-ink dark:text-bright transition-colors w-3 text-center text-[10px] mt-1 shrink-0"
            aria-label={expanded ? "Collapse" : "Expand"}
          >
            {expanded ? "▾" : "▸"}
          </button>
        ) : (
          <span className="w-3 shrink-0" />
        )}
        <NavLink
          to={`/inv/${node.investigationId}`}
          className={`flex-1 min-w-0 py-1 px-1.5 rounded transition-colors relative ${
            isActive
              ? "bg-sun text-ink"
              : "hover:bg-sun/20 dark:hover:bg-sun/15 text-ink dark:text-bright"
          }`}
          style={{ marginLeft: depth * 8 }}
        >
          {isActive && (
            <span aria-hidden="true" className="absolute left-0 top-1 bottom-1 w-0.5 bg-ink" />
          )}
          <div className="flex items-start gap-1.5">
            <span
              aria-label={`${rollup}${rollupUnseen ? " · unseen" : ""}`}
              title={`${rollup}${rollupUnseen ? " · unseen" : ""}`}
              className={`w-1.5 h-1.5 rounded-full mt-1.5 shrink-0 ${researchStateDotClass(rollup, rollupUnseen)}`}
            />
            <div className="flex-1 min-w-0">
              <div
                className={`font-serif leading-snug truncate ${
                  unseen ? "font-bold" : ""
                }`}
              >
                {truncate(summary?.question ?? node.investigationId, 60)}
              </div>
              <div className="font-mono text-[9px] text-ink-mute dark:text-moonlight mt-0.5">
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

/** Depth-first summaries of a node and its whole subtree — the input to the
 *  attention rollup. The tree is already sorted newest-first by
 *  useInvestigationTree; order does not affect the max. */
function collectSubtree(node: TreeNode): InvestigationSummary[] {
  const out: InvestigationSummary[] = [];
  const walk = (n: TreeNode) => {
    if (n.summary) out.push(n.summary);
    for (const child of n.children) walk(child);
  };
  walk(node);
  return out;
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
