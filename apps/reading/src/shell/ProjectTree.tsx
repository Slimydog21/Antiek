import { useNavigate, useLocation } from "react-router-dom";
import { useEffect, useState } from "react";

import { useWorkspace } from "../workspace/WorkspaceStore";
import { usePinned } from "../components/navigation/pinnedStore";
import { useOpenDocument } from "../lib/openDocument";
import { listDeliverables } from "../lib/api";
import { listPeople, type RememberedPerson } from "../lib/speakApi";
import { LemonTag } from "../components/lemon/LemonTag";
import { listBooks } from "../api/books";
import type { BookSummary } from "../api/books";
import type { DeliverableSummary, InvestigationSummary } from "../lib/api";
import { useInvestigationList } from "../hooks/useInvestigationList";
import {
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
type NodeKind = "investigation" | "document" | "notebook" | "deliverable" | "person";

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
  write: [{ to: "/write", label: "All pieces" }],
  speak: [
    // Speak SPR-08 one door: the duplicate "All interviews" link is folded
    // into the Speak home (interviews live inside a project there now).
    { to: "/speak", label: "All projects" },
  ],
};

// SPR-05 one door: a `document` node is NOT routed by a path string anymore —
// it opens through `openDocument` (→ the gated /read/:id Reader). This is a door
// that was NOT on the migration-map's 11 (it routed to /wrestle/:id, the killed
// open target); per the spec's fifth-door rule, it is routed here too. Only
// investigation / notebook nodes still resolve to a path; a `document` reaching
// these helpers is unreachable (onItemClick routes it earlier) — we fail loud
// rather than mint a dead /wrestle path.
const routeForNode = (n: TreeNode): string => {
  switch (n.kind) {
    case "investigation":
      return `/inv/${n.id}`;
    case "notebook":
      return `/notebook/${n.id}`;
    case "deliverable":
      return `/write/${encodeURIComponent(n.id)}`;
    case "person":
      return `/speak/${encodeURIComponent(n.id)}`;
    case "document":
      throw new Error("document nodes open via openDocument, not a route (SPR-05)");
  }
};

const panelKindForNode = (n: TreeNode): "Trajectory" | "Notebook" | "DeliverablePreview" => {
  switch (n.kind) {
    case "investigation":
      return "Trajectory";
    case "notebook":
      return "Notebook";
    case "deliverable":
      return "DeliverablePreview";
    case "person":
      throw new Error("person nodes route to Speak; no floating panel contract exists");
    case "document":
      throw new Error("document nodes open via openDocument, not a panel (SPR-05)");
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

function nonEmptyString(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

function deliverableNode(deliverable: DeliverableSummary): TreeNode | null {
  const id = nonEmptyString(deliverable.deliverable_id);
  if (!id) return null;
  return {
    kind: "deliverable",
    id,
    title: nonEmptyString(deliverable.title) ?? "Untitled piece",
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

function safePersonNodes(value: unknown): TreeNode[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) => {
    const row =
      typeof item === "object" && item !== null && !Array.isArray(item)
        ? (item as Partial<RememberedPerson>)
        : null;
    const id = nonEmptyString(row?.id);
    if (!id) return [];
    const voiceCount =
      typeof row?.voiceCount === "number" &&
      Number.isSafeInteger(row.voiceCount) &&
      row.voiceCount >= 0
        ? row.voiceCount
        : 0;
    return [{
      kind: "person" as const,
      id,
      title: `${nonEmptyString(row?.name) ?? "Untitled remembrance"} · ${
        voiceCount === 0 ? "no voices yet" : `${voiceCount} voice${voiceCount === 1 ? "" : "s"}`
      }`,
    }];
  });
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
  const openDocument = useOpenDocument();
  const [writeRecent, setWriteRecent] = useState<TreeNode[]>([]);
  const [speakRecent, setSpeakRecent] = useState<TreeNode[]>([]);

  const pinnedKey = (n: TreeNode) => `${n.kind}:${n.id}`;

  const researchNodes = research.investigations.map(investigationNode);
  const readNodes = read.documents.map(documentNode);

  useEffect(() => {
    if (workflow !== "write") return;
    let cancelled = false;
    listDeliverables()
      .then((body) => {
        if (!cancelled) setWriteRecent(body.deliverables.flatMap((d) => deliverableNode(d) ?? []));
      })
      .catch(() => {
        if (!cancelled) setWriteRecent([]);
      });
    return () => {
      cancelled = true;
    };
  }, [workflow]);

  useEffect(() => {
    if (workflow !== "speak") return;
    let cancelled = false;
    listPeople()
      .then((people) => {
        if (!cancelled) setSpeakRecent(safePersonNodes(people));
      })
      .catch(() => {
        if (!cancelled) setSpeakRecent([]);
      });
    return () => {
      cancelled = true;
    };
  }, [workflow]);

  const recent =
    workflow === "research"
      ? researchNodes
      : workflow === "read"
        ? readNodes
        : workflow === "write"
          ? writeRecent
          : workflow === "speak"
            ? speakRecent
            : [];
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
    // SPR-05 one door: a document opens in the ONE Reader (openDocument → the
    // gated /read/:id) on either click — a cmd-click opens it in the inspect
    // ("view original") register rather than a bespoke PdfViewer panel (which
    // would be a second document renderer). Investigations / notebooks keep
    // their panel-or-route behaviour unchanged.
    if (n.kind === "document") {
      e.preventDefault();
      if (e.metaKey || e.ctrlKey) {
        openDocument(n.id, { mode: "inspect" });
      } else {
        openDocument(n.id);
      }
      return;
    }
    if (e.metaKey || e.ctrlKey) {
      e.preventDefault();
      if (n.kind === "person") {
        navigate(routeForNode(n));
        return;
      }
      const props = n.kind === "deliverable" ? { deliverableId: n.id } : { id: n.id };
      openPanel(panelKindForNode(n), props, { mode: "floating", title: n.title });
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
    deliverable: "✎",
    person: "◌",
  };
  const openTitle =
    node.kind === "document"
      ? "Click to open in Reader. Cmd/Ctrl+Click to inspect original."
      : node.kind === "deliverable"
        ? "Click to open in Write. Cmd/Ctrl+Click to preview."
        : node.kind === "person"
          ? "Click to open the Speak project."
          : "Click to open. Cmd/Ctrl+Click to open as floating panel.";

  return (
    <div className="flex items-center group">
      <button
        type="button"
        onClick={onClick}
        data-node-id={node.id}
        className="flex-1 flex items-center gap-2 px-3 py-1.5 hover:bg-sun/20 dark:hover:bg-sun/10 text-left min-w-0"
        title={openTitle}
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
        aria-label={pinned ? `Unpin ${node.title}` : `Pin ${node.title}`}
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
