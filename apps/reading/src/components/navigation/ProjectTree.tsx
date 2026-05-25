import { useNavigate } from "react-router-dom";
import { useState } from "react";

import { useWorkspace } from "../../workspace/WorkspaceStore";
import type { PanelKind } from "../../workspace/panel.types";
import { LemonTag } from "../lemon/LemonTag";
import { usePinned } from "./pinnedStore";
import { useActiveWorkflow } from "../../shell/activeWorkflow";
import type { ActiveWorkflow } from "../../shell/activeWorkflow";
import { WORKFLOW_LABEL } from "../../shell/workflowTaxonomy";

/**
 * ProjectTree — the persistent CONTENT column, scoped to the active workflow
 * (frontend-design spec, SPR-04). You navigate the nouns you've made, not the
 * tools that make them; and you see the nouns of the workflow you're in.
 *
 * Functional rationale: "where is my work?" is answered per workflow —
 * Research shows investigations + chase trees, Read shows the corpus +
 * notebooks, Write shows deliverables, Speak shows interview projects. A flat
 * all-folders list could be otherwise; a workflow-scoped tree could not,
 * without losing the legibility the four-workflow rail promises. Folders whose
 * product isn't built render an HONEST empty state naming the owning sprint —
 * never a fake row (a seeded sample would do negative work).
 *
 * Mock data below; the live hooks (useInvestigationList + useDocuments +
 * useNotebooks) plug into the same folder shape during the per-mode data
 * ports. The folder architecture + workflow-scoping is what's load-bearing.
 */
type NodeKind =
  | "investigation"
  | "document"
  | "notebook"
  | "deliverable"
  | "interview";

type TreeNode = {
  kind: NodeKind;
  id: string;
  title: string;
  status?: "running" | "done" | "failed";
  children?: TreeNode[];
};

type Folder = {
  key: string;
  label: string;
  workflow: ActiveWorkflow;
  nodes: TreeNode[];
  /** Honest empty state for an unbuilt product surface (names the owning sprint). */
  emptyNote?: string;
};

const FOLDERS: Folder[] = [
  // ---- Research ----
  {
    key: "investigations",
    label: "Investigations",
    workflow: "research",
    nodes: [
      {
        kind: "investigation",
        id: "web-gaming-2026",
        title: "Web gaming 2026",
        status: "running",
        children: [
          { kind: "investigation", id: "rosebud-retention", title: "Rosebud retention diligence" },
          { kind: "investigation", id: "roblox-ad-load", title: "Roblox ad-load ceiling" },
        ],
      },
      { kind: "investigation", id: "ducklake-iceberg", title: "DuckLake vs Iceberg", status: "done" },
      { kind: "investigation", id: "rl-reward-shaping", title: "RL reward-shaping survey", status: "done" },
    ],
  },
  // ---- Read ----
  {
    key: "documents",
    label: "Documents",
    workflow: "read",
    nodes: [
      { kind: "document", id: "nilo-deck", title: "Nilo Series-A deck.pdf" },
      { kind: "document", id: "roblox-10k", title: "Roblox 10-K FY25" },
    ],
  },
  {
    key: "notebooks",
    label: "Notebooks",
    workflow: "read",
    nodes: [
      { kind: "notebook", id: "web-gaming-memo", title: "Web-gaming memo draft" },
      { kind: "notebook", id: "substrate-notes", title: "Substrate design notes" },
    ],
  },
  {
    key: "library",
    label: "Library",
    workflow: "read",
    nodes: [],
    emptyNote: "No books yet — the library ships in the Read spec.",
  },
  // ---- Write ----
  {
    key: "deliverables",
    label: "Deliverables",
    workflow: "write",
    nodes: [{ kind: "deliverable", id: "web-gaming-ic-memo", title: "Web-gaming IC memo" }],
  },
  {
    key: "blocks",
    label: "Block repository",
    workflow: "write",
    nodes: [],
    emptyNote: "Insight blocks browse here — ships in the Write spec.",
  },
  // ---- Speak ----
  {
    key: "interviews",
    label: "Interview projects",
    workflow: "speak",
    nodes: [{ kind: "interview", id: "nilo-founder", title: "Founder call — Nilo" }],
  },
  {
    key: "contributors",
    label: "Contributors",
    workflow: "speak",
    nodes: [],
    emptyNote: "Contributor economics ship in the Speak spec.",
  },
];

const ICON: Record<NodeKind, string> = {
  investigation: "⌕",
  document: "📄",
  notebook: "❍",
  deliverable: "✎",
  interview: "🎙",
};

const routeForNode = (n: TreeNode): string => {
  switch (n.kind) {
    case "investigation":
      return `/inv/${n.id}`;
    case "document":
      return `/wrestle/${n.id}`;
    case "notebook":
      return `/notebook/${n.id}`;
    case "deliverable":
      return `/create/${n.id}`;
    case "interview":
      return `/interview/${n.id}`;
  }
};

/** Panel kind for cmd-click float, where one exists. */
const panelKindForNode = (n: TreeNode): PanelKind | null => {
  switch (n.kind) {
    case "investigation":
      return "Trajectory";
    case "document":
      return "PdfViewer";
    case "notebook":
      return "Notebook";
    default:
      return null;
  }
};

const nodeKey = (n: TreeNode) => `${n.kind}:${n.id}`;

/** Flatten one level deep so Pinned can surface children too. */
function flatten(nodes: TreeNode[]): TreeNode[] {
  return nodes.flatMap((n) => [n, ...(n.children ?? [])]);
}

const ALL_NODES = FOLDERS.flatMap((f) => flatten(f.nodes));

export function ProjectTree() {
  const navigate = useNavigate();
  const pinned = usePinned((s) => s.pinned);
  const togglePin = usePinned((s) => s.toggle);
  const openPanel = useWorkspace((s) => s.open);
  const active = useActiveWorkflow((s) => s.active);

  const pinnedNodes = ALL_NODES.filter((n) => pinned.has(nodeKey(n)));
  const folders = FOLDERS.filter((f) => f.workflow === active);

  // Default-expand the populated folders of the active workflow; collapse empties.
  const [expanded, setExpanded] = useState<Record<string, boolean>>({ pinned: true });
  const isExpanded = (key: string, fallback: boolean) =>
    key in expanded ? expanded[key] : fallback;

  const onItemClick = (n: TreeNode, e: React.MouseEvent) => {
    const kind = panelKindForNode(n);
    if ((e.metaKey || e.ctrlKey) && kind) {
      e.preventDefault();
      openPanel(kind, { id: n.id }, { mode: "floating", title: n.title });
      return;
    }
    navigate(routeForNode(n));
  };

  return (
    <div className="text-[13px] text-ink dark:text-bright">
      {/* Active-workflow label — tells the user which work's nouns these are */}
      <div className="px-3 pt-2 pb-1 font-mono text-[10px] uppercase tracking-[0.16em] text-ink-mute dark:text-moonlight">
        {WORKFLOW_LABEL[active]}
      </div>

      {/* Pinned (universal, across workflows) */}
      <Section
        label="Pinned"
        expanded={isExpanded("pinned", true)}
        onToggle={() => setExpanded((s) => ({ ...s, pinned: !isExpanded("pinned", true) }))}
        count={pinnedNodes.length}
      >
        {pinnedNodes.length === 0 ? (
          <p className="px-3 py-2 text-[12px] italic text-ink-mute dark:text-moonlight">
            Pin an item to keep it close.
          </p>
        ) : (
          pinnedNodes.map((n) => (
            <NodeRow
              key={nodeKey(n)}
              node={n}
              pinned
              onClick={(e) => onItemClick(n, e)}
              onPin={() => togglePin(nodeKey(n))}
            />
          ))
        )}
      </Section>

      {/* The active workflow's content folders */}
      {folders.map((folder) => {
        const fallback = folder.nodes.length > 0; // populated folders open by default
        return (
          <Section
            key={folder.key}
            label={folder.label}
            expanded={isExpanded(folder.key, fallback)}
            onToggle={() =>
              setExpanded((s) => ({ ...s, [folder.key]: !isExpanded(folder.key, fallback) }))
            }
            count={folder.nodes.length}
          >
            {folder.nodes.length === 0 ? (
              <p className="px-3 py-2 text-[12px] italic text-ink-mute dark:text-moonlight">
                {folder.emptyNote ?? "Empty."}
              </p>
            ) : (
              folder.nodes.map((n) => (
                <div key={nodeKey(n)}>
                  <NodeRow
                    node={n}
                    pinned={pinned.has(nodeKey(n))}
                    onClick={(e) => onItemClick(n, e)}
                    onPin={() => togglePin(nodeKey(n))}
                  />
                  {n.children?.map((c) => (
                    <NodeRow
                      key={nodeKey(c)}
                      node={c}
                      pinned={pinned.has(nodeKey(c))}
                      indent
                      onClick={(e) => onItemClick(c, e)}
                      onPin={() => togglePin(nodeKey(c))}
                    />
                  ))}
                </div>
              ))
            )}
          </Section>
        );
      })}
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
  indent,
  onClick,
  onPin,
}: {
  node: TreeNode;
  pinned: boolean;
  indent?: boolean;
  onClick: (e: React.MouseEvent) => void;
  onPin: () => void;
}) {
  const dot: Record<NonNullable<TreeNode["status"]>, "sun" | "aurora" | "danger"> = {
    running: "sun",
    done: "aurora",
    failed: "danger",
  };

  return (
    <div className="flex items-center group">
      <button
        type="button"
        onClick={onClick}
        className={
          "flex-1 flex items-center gap-2 py-1.5 hover:bg-sun/20 dark:hover:bg-sun/10 text-left min-w-0 " +
          (indent ? "pl-7 pr-3" : "px-3")
        }
        title="Click to open. Cmd/Ctrl+Click to open as a floating panel."
      >
        <span aria-hidden="true" className="text-ink-mute dark:text-moonlight shrink-0">
          {indent ? "↳" : ICON[node.kind]}
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
