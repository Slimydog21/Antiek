import { useNavigate } from "react-router-dom";
import { useState } from "react";

import { useWorkspace } from "../../workspace/WorkspaceStore";
import { LemonTag } from "../lemon/LemonTag";
import { usePinned } from "./pinnedStore";

/**
 * ProjectTree — the dockable navigation panel. Three sections:
 *
 *   ▾ Pinned     items the operator explicitly pinned (persist in S9)
 *   ▾ Recent     last N investigations + documents + notebooks (auto)
 *   ▾ All        list-view links to the index routes
 *
 * Click an item            → router navigate (route-mode swap)
 * Cmd/Ctrl+Click           → open as a floating panel (workspace open)
 * Right-click              → context menu (pin / float / copy link)
 *
 * S4 ships static mock data via constants below — the live data flows
 * (useInvestigationList + useDocuments + useNotebooks) plug in during
 * the S5/S6/S7 mode ports. The architecture (sections + interactions)
 * is what's load-bearing in S4; data is swappable.
 */
type NodeKind = "investigation" | "document" | "notebook";

type TreeNode = {
  kind: NodeKind;
  id: string;
  title: string;
  status?: "running" | "done" | "failed";
};

const MOCK_RECENT: TreeNode[] = [
  { kind: "investigation", id: "nvda-q4", title: "NVDA Q4 risk model", status: "running" },
  { kind: "investigation", id: "web-gaming-2026", title: "Web gaming 2026", status: "done" },
  { kind: "investigation", id: "kalshi-liquidity", title: "Kalshi liquidity gate", status: "done" },
  { kind: "document", id: "kalshi-paper", title: "Kalshi liquidity preprint.pdf" },
  { kind: "notebook", id: "synth-nvda", title: "NVDA synthesis · draft 2" },
];

const ALL_LINKS: Array<{ to: string; label: string }> = [
  { to: "/investigations", label: "All investigations" },
  { to: "/documents", label: "All documents" },
  { to: "/notebooks", label: "All notebooks" },
  { to: "/sources", label: "All sources" },
];

const routeForNode = (n: TreeNode): string => {
  switch (n.kind) {
    case "investigation":
      return `/inv/${n.id}`;
    case "document":
      return `/wrestle/${n.id}`;
    case "notebook":
      return `/notebook/${n.id}`;
  }
};

const panelKindForNode = (n: TreeNode) => {
  switch (n.kind) {
    case "investigation":
      return "Trajectory" as const;
    case "document":
      return "PdfViewer" as const;
    case "notebook":
      return "Notebook" as const;
  }
};

export function ProjectTree() {
  const navigate = useNavigate();
  const pinned = usePinned((s) => s.pinned);
  const togglePin = usePinned((s) => s.toggle);
  const openPanel = useWorkspace((s) => s.open);

  const pinnedKey = (n: TreeNode) => `${n.kind}:${n.id}`;

  // Show pinned nodes by reading them out of the mocks; in production
  // these come from the live hooks (S5+).
  const pinnedNodes = MOCK_RECENT.filter((n) => pinned.has(pinnedKey(n)));
  const recentNodes = MOCK_RECENT.filter((n) => !pinned.has(pinnedKey(n)));

  const [expanded, setExpanded] = useState<Record<string, boolean>>({
    pinned: true,
    recent: true,
    all: true,
  });

  const onItemClick = (n: TreeNode, e: React.MouseEvent) => {
    if (e.metaKey || e.ctrlKey) {
      e.preventDefault();
      openPanel(panelKindForNode(n), { id: n.id }, { mode: "floating", title: n.title });
      return;
    }
    navigate(routeForNode(n));
  };

  return (
    <div className="text-[13px] text-ink dark:text-bright">
      {/* Pinned */}
      <Section
        label="Pinned"
        expanded={expanded.pinned}
        onToggle={() => setExpanded((s) => ({ ...s, pinned: !s.pinned }))}
        count={pinnedNodes.length}
      >
        {pinnedNodes.length === 0 ? (
          <p className="px-3 py-2 text-[12px] italic text-ink-mute dark:text-moonlight">
            Pin an item from Recent to keep it close.
          </p>
        ) : (
          pinnedNodes.map((n) => (
            <NodeRow
              key={pinnedKey(n)}
              node={n}
              pinned
              onClick={(e) => onItemClick(n, e)}
              onPin={() => togglePin(pinnedKey(n))}
            />
          ))
        )}
      </Section>

      {/* Recent */}
      <Section
        label="Recent"
        expanded={expanded.recent}
        onToggle={() => setExpanded((s) => ({ ...s, recent: !s.recent }))}
        count={recentNodes.length}
      >
        {recentNodes.map((n) => (
          <NodeRow
            key={pinnedKey(n)}
            node={n}
            pinned={false}
            onClick={(e) => onItemClick(n, e)}
            onPin={() => togglePin(pinnedKey(n))}
          />
        ))}
      </Section>

      {/* All */}
      <Section
        label="All"
        expanded={expanded.all}
        onToggle={() => setExpanded((s) => ({ ...s, all: !s.all }))}
        count={ALL_LINKS.length}
      >
        {ALL_LINKS.map((l) => (
          <button
            key={l.to}
            type="button"
            onClick={() => navigate(l.to)}
            className="w-full flex items-center gap-2 px-3 py-1.5 hover:bg-sun/20 dark:hover:bg-sun/10 text-left"
          >
            <span className="opacity-50">›</span>
            <span>{l.label}</span>
          </button>
        ))}
      </Section>
    </div>
  );
}

function Section({
  label,
  expanded,
  onToggle,
  count,
  children,
}: {
  label: string;
  expanded: boolean;
  onToggle: () => void;
  count?: number;
  children: React.ReactNode;
}) {
  return (
    <section className="border-b border-rule dark:border-charcoal-1 last:border-b-0">
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={expanded}
        className="w-full flex items-center gap-1.5 px-3 py-2 font-mono text-[11px] uppercase tracking-wider text-shadow-1 dark:text-moonlight hover:text-ink dark:hover:text-bright"
      >
        <span aria-hidden="true">{expanded ? "▾" : "▸"}</span>
        <span>{label}</span>
        {count !== undefined && (
          <span className="ml-auto text-ink-mute dark:text-moonlight tabular-nums">
            {count}
          </span>
        )}
      </button>
      {expanded && <div className="pb-1.5">{children}</div>}
    </section>
  );
}

function NodeRow({
  node,
  pinned,
  onClick,
  onPin,
}: {
  node: TreeNode;
  pinned: boolean;
  onClick: (e: React.MouseEvent) => void;
  onPin: () => void;
}) {
  const dot: Record<NonNullable<TreeNode["status"]>, "sun" | "aurora" | "danger"> = {
    running: "sun",
    done: "aurora",
    failed: "danger",
  };
  const icon: Record<NodeKind, string> = {
    investigation: "⌕",
    document: "📄",
    notebook: "❍",
  };

  return (
    <div className="flex items-center group">
      <button
        type="button"
        onClick={onClick}
        className="flex-1 flex items-center gap-2 px-3 py-1.5 hover:bg-sun/20 dark:hover:bg-sun/10 text-left min-w-0"
        title="Click to open. Cmd/Ctrl+Click to open as floating panel."
      >
        <span aria-hidden="true" className="text-ink-mute dark:text-moonlight shrink-0">
          {icon[node.kind]}
        </span>
        <span className="truncate flex-1">{node.title}</span>
        {node.status && (
          <LemonTag dot colour={dot[node.status]} className="shrink-0 text-[10px]">
            {node.status}
          </LemonTag>
        )}
      </button>
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          onPin();
        }}
        aria-label={pinned ? "Unpin" : "Pin"}
        className={
          "px-2 py-1.5 shrink-0 text-[13px] " +
          (pinned
            ? "text-sun-deep dark:text-sun"
            : "text-ink-mute dark:text-moonlight opacity-0 group-hover:opacity-100 hover:text-ink dark:hover:text-bright")
        }
      >
        {pinned ? "★" : "☆"}
      </button>
    </div>
  );
}

export default ProjectTree;
