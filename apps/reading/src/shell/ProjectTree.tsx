import { useNavigate, useLocation } from "react-router-dom";
import { useEffect, useState } from "react";

import { useWorkspace } from "../workspace/WorkspaceStore";
import { usePinned } from "../components/navigation/pinnedStore";
import { LemonTag } from "../components/lemon/LemonTag";
import { listBooks } from "../api/books";
import type { BookSummary } from "../api/books";
import type { InvestigationSummary } from "../lib/api";
import { useInvestigationList } from "../hooks/useInvestigationList";
import {
import { emitWernerExperience } from "../werner/reactionBus";
  WORKFLOWS,
  workflowForPath,
  type Workflow,
} from "./workflowTaxonomy";

/**
 * ProjectTree (SPR-04 zone 2) — the content-first project tree, scoped to
 * the ACTIVE WORKFLOW's nouns (the objects the operator works on), not the
 * workflow's tools.
 *
 *   Research → Investigations / Chase trees / Outcomes
 *   Read     → Library / Documents / Notebooks / Sources
 *   Write    → Deliverables / Block repository
 *   Speak    → People to remember / Their people / Voices
 *
 * The sections are driven by WORKFLOWS[wf].nouns from the taxonomy, so the
 * tree re-scopes automatically when the rail switches workflows. Within a
 * section, Recent/Pinned items come from live workflow data where it exists.
 *
 * This SUPERSEDES the flat Pinned/Recent/All tree at
 * components/navigation/ProjectTree.tsx; PanelRegistry now points here.
 */
type NodeKind = "investigation" | "document" | "notebook";

type TreeNode = {
  kind: NodeKind;
  id: string;
  title: string;
  status?: "running" | "done" | "failed";
};

// The "All" links per workflow → the workflow's index routes (nouns).
const ALL_LINKS: Record<Exclude<Workflow, "shared">, Array<{ to: string; label: string }>> = {
  research: [
    // SPR-05: one door for "all my research" — the multi-research monitor.
    { to: "/my-research", label: "All my research" },
    { to: "/outcomes", label: "Outcomes audit" },
  ],
  read: [
    // SPR-13 M4 — the personal space + its meta-docs tab, after the Library.
    { to: "/readings", label: "Your readings" },
    { to: "/meta-readings", label: "All meta-docs" },
    { to: "/documents", label: "All documents" },
    { to: "/notebooks", label: "All notebooks" },
    { to: "/sources", label: "All sources" },
  ],
  write: [{ to: "/create", label: "All deliverables" }],
  speak: [
    // Speak SPR-08 one door: the duplicate "All interviews" link is folded
    // into the Speak home (interviews live inside a project there now).
    { to: "/speak", label: "All projects" },
  ],
};

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

function investigationStatus(status: InvestigationSummary["status"]): TreeNode["status"] {
  switch (status) {
    case "in_progress":
      return "running";
    case "completed":
    case "stopped":
      return "done";
    case "failed":
    case "not_found":
      return "failed";
  }
}

function investigationNode(inv: InvestigationSummary): TreeNode {
  return {
    kind: "investigation",
    id: inv.investigation_id,
    title: inv.question ?? "Untitled investigation",
    status: investigationStatus(inv.status),
  };
}

function documentNode(book: BookSummary): TreeNode {
  return {
    kind: "document",
    id: book.document_id,
    title: book.title ?? "Untitled document",
  };
}

function useReadDocuments() {
  const [documents, setDocuments] = useState<BookSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const resp = await listBooks("all");
        if (!cancelled) {
          setDocuments(resp.books);
          setError(null);
        }
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return { documents, loading, error };
}

export function ProjectTree({
  /** Override the active workflow (Storybook); defaults to the route. */
  workflow: forced,
}: {
  workflow?: Exclude<Workflow, "shared">;
} = {}) {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const routeWf = workflowForPath(pathname);
  const workflow: Exclude<Workflow, "shared"> =
    forced ?? (routeWf === "shared" ? "research" : routeWf);
  const meta = WORKFLOWS[workflow];

  const pinned = usePinned((s) => s.pinned);
  const togglePin = usePinned((s) => s.toggle);
  const openPanel = useWorkspace((s) => s.open);
  const research = useInvestigationList();
  const read = useReadDocuments();

  const pinnedKey = (n: TreeNode) => `${n.kind}:${n.id}`;

  const researchNodes = research.investigations.map(investigationNode);
  const readNodes = read.documents.map(documentNode);
  const recent =
    workflow === "research" ? researchNodes : workflow === "read" ? readNodes : [];
  const recentLoading =
    workflow === "research" ? research.loading : workflow === "read" ? read.loading : false;
  const recentError =
    workflow === "research" ? research.error : workflow === "read" ? read.error : null;
  const pinnedNodes = recent.filter((n) => pinned.has(pinnedKey(n)));
  const recentNodes = recent.filter((n) => !pinned.has(pinnedKey(n)));

  const [expanded, setExpanded] = useState<Record<string, boolean>>({
    pinned: true,
    recent: true,
    all: true,
  });

  const onItemClick = (n: TreeNode, e: React.MouseEvent) => {
    emitWernerExperience("highlight");
    if (e.metaKey || e.ctrlKey) {
      e.preventDefault();
      openPanel(panelKindForNode(n), { id: n.id }, { mode: "floating", title: n.title });
      return;
    }
    navigate(routeForNode(n));
  };

  return (
    <div
      className="text-[13px] text-ink dark:text-bright"
      data-testid={`project-tree-${workflow}`}
    >
      {/* Workflow header — names the active workflow + its nouns. */}
      <div className="px-3 pt-2.5 pb-2 border-b border-rule dark:border-charcoal-1">
        <p className="font-serif text-[15px] text-ink dark:text-bright">
          {meta.label}
        </p>
        <p className="font-mono text-[10.5px] uppercase tracking-wider text-shadow-1 dark:text-moonlight mt-0.5">
          {meta.nouns.join(" · ")}
        </p>
      </div>

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
        {recentLoading ? (
          <p className="px-3 py-2 text-[12px] text-ink-mute dark:text-moonlight">
            Loading recent items...
          </p>
        ) : recentError ? (
          <p className="px-3 py-2 text-[12px] text-danger">
            Could not load recent items: {recentError}
          </p>
        ) : recentNodes.length === 0 ? (
          <p className="px-3 py-2 text-[12px] italic text-ink-mute dark:text-moonlight">
            No recent items yet.
          </p>
        ) : (
          recentNodes.map((n) => (
            <NodeRow
              key={pinnedKey(n)}
              node={n}
              pinned={false}
              onClick={(e) => onItemClick(n, e)}
              onPin={() => togglePin(pinnedKey(n))}
            />
          ))
        )}
      </Section>

      {/* All — workflow-scoped index routes. */}
      <Section
        label="All"
        expanded={expanded.all}
        onToggle={() => setExpanded((s) => ({ ...s, all: !s.all }))}
        count={ALL_LINKS[workflow].length}
      >
        {ALL_LINKS[workflow].map((l) => (
          <button
            key={l.to}
            type="button"
            onClick={() => { emitWernerExperience("highlight"); navigate(l.to); }}
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
        data-node-id={node.id}
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
