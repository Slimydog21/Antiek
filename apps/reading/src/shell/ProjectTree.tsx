import { useNavigate, useLocation } from "react-router-dom";
import { useEffect, useRef, useState } from "react";

import { useWorkspace } from "../workspace/WorkspaceStore";
import { usePinned } from "../components/navigation/pinnedStore";
import { LemonTag } from "../components/lemon/LemonTag";
import { listBooks } from "../api/books";
import type { BookSummary } from "../api/books";
import {
  listPrivateWriteDocuments,
  createNativePrivateWrite,
  type InvestigationSummary,
  type PrivateWriteDocumentSummaryShape,
} from "../lib/api";
import { useAuth } from "../lib/auth";
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
type NodeKind = "investigation" | "document" | "notebook" | "private-write";

type TreeNode = {
  kind: NodeKind;
  id: string;
  title: string;
  projectId?: string;
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
    case "private-write":
      return "";
  }
};

const panelKindForNode = (n: TreeNode) => {
  switch (n.kind) {
    case "investigation":
      return "Trajectory" as const;
    case "document":
      return "HostedDocument" as const;
    case "notebook":
      return "Notebook" as const;
    case "private-write":
      return "PrivateWrite" as const;
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

function privateWriteNode(document: PrivateWriteDocumentSummaryShape): TreeNode {
  return {
    kind: "private-write",
    id: document.write_document_id,
    projectId: document.project_id,
    title: document.title || "Untitled private manuscript",
  };
}

const WRITE_SUMMARY_KEYS = new Set([
  "write_document_id", "project_id", "title", "revision", "html_sha256", "visibility", "updated_at",
  "origin_kind",
]);
const HEX64 = /^[0-9a-f]{64}$/;

function validPrivateWriteSummary(value: PrivateWriteDocumentSummaryShape): boolean {
  if (!value || typeof value !== "object" || Object.keys(value).some((key) => !WRITE_SUMMARY_KEYS.has(key))) return false;
  return typeof value.write_document_id === "string" && value.write_document_id.length > 0 &&
    typeof value.project_id === "string" && value.project_id.length > 0 &&
    typeof value.title === "string" && Number.isInteger(value.revision) && value.revision >= 1 &&
    HEX64.test(value.html_sha256) && value.visibility === "private" &&
    (value.origin_kind === "ai_composition" || value.origin_kind === "owner_native") &&
    typeof value.updated_at === "string";
}

function usePrivateWriteDocuments(enabled: boolean) {
  const { sessionGeneration } = useAuth();
  const [documents, setDocuments] = useState<PrivateWriteDocumentSummaryShape[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshEpoch, setRefreshEpoch] = useState(0);

  useEffect(() => {
    if (!enabled) { setDocuments([]); setLoading(false); setError(null); return; }
    const abort = new AbortController();
    setDocuments([]); setLoading(true); setError(null);
    void (async () => {
      try {
        const complete: PrivateWriteDocumentSummaryShape[] = [];
        let cursor = "";
        for (let pageNumber = 0; pageNumber < 2_000; pageNumber += 1) {
          const page = await listPrivateWriteDocuments(abort.signal, cursor, 100);
          if (!Array.isArray(page.documents) ||
              !(page.next_after_document_id === null || typeof page.next_after_document_id === "string")) {
            throw new Error("Private Write collection response is malformed");
          }
          for (const document of page.documents) {
            if (!validPrivateWriteSummary(document) || document.write_document_id <= cursor ||
                (complete.at(-1)?.write_document_id ?? "") >= document.write_document_id) {
              throw new Error("Private Write collection authority is inconsistent");
            }
            complete.push(document); cursor = document.write_document_id;
          }
          if (page.next_after_document_id === null) {
            if (!abort.signal.aborted) setDocuments(complete);
            return;
          }
          if (page.documents.length === 0 || page.next_after_document_id !== cursor) {
            throw new Error("Private Write collection cursor made no progress");
          }
        }
        throw new Error("Private Write collection exceeds the bounded page walk");
      } catch (caught: unknown) {
        if ((caught as { name?: string }).name !== "AbortError" && !abort.signal.aborted) {
          setDocuments([]); setError(caught instanceof Error ? caught.message : String(caught));
        }
      } finally { if (!abort.signal.aborted) setLoading(false); }
    })();
    return () => abort.abort();
  }, [enabled, refreshEpoch, sessionGeneration]);

  return { documents, loading, error, refresh: () => setRefreshEpoch((value) => value + 1) };
}

const newMutationKey = () => globalThis.crypto?.randomUUID?.() ??
  `native-write-${Date.now()}-${Math.random().toString(16).slice(2)}`;

function NewManuscriptAction({
  onCreated,
}: {
  onCreated: (document: PrivateWriteDocumentSummaryShape) => void;
}) {
  const { sessionGeneration } = useAuth();
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [state, setState] = useState<"idle" | "creating" | "error">("idle");
  const [message, setMessage] = useState("");
  const keyRef = useRef("");
  const invokerRef = useRef<HTMLButtonElement | null>(null);
  const dialogRef = useRef<HTMLDivElement | null>(null);
  const createAbortRef = useRef<AbortController | null>(null);
  const generationRef = useRef(sessionGeneration);

  useEffect(() => {
    if (generationRef.current !== sessionGeneration) {
      generationRef.current = sessionGeneration;
      createAbortRef.current?.abort(); setOpen(false); setTitle(""); setMessage("");
      setState("idle");
    }
    return () => createAbortRef.current?.abort();
  }, [sessionGeneration]);

  useEffect(() => {
    if (!open) { invokerRef.current?.focus(); return; }
    dialogRef.current?.querySelector<HTMLInputElement>("input")?.focus();
    const keydown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && state !== "creating") {
        event.preventDefault(); setOpen(false); return;
      }
      if (event.key !== "Tab") return;
      const controls = dialogRef.current?.querySelectorAll<HTMLElement>("input,button:not([disabled])");
      if (!controls?.length) return;
      const first = controls[0]; const last = controls[controls.length - 1];
      if (event.shiftKey && globalThis.document.activeElement === first) {
        event.preventDefault(); last.focus();
      } else if (!event.shiftKey && globalThis.document.activeElement === last) {
        event.preventDefault(); first.focus();
      }
    };
    const dialog = dialogRef.current;
    dialog?.addEventListener("keydown", keydown);
    return () => dialog?.removeEventListener("keydown", keydown);
  }, [open, state]);

  const begin = () => {
    keyRef.current = newMutationKey(); setTitle(""); setMessage("");
    setState("idle"); setOpen(true);
  };
  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (state === "creating" || !title.trim() || title !== title.trim()) return;
    setState("creating"); setMessage("");
    const requestGeneration = sessionGeneration;
    const abort = new AbortController(); createAbortRef.current = abort;
    try {
      const created = await createNativePrivateWrite(title, keyRef.current, abort.signal);
      if (abort.signal.aborted || generationRef.current !== requestGeneration) return;
      const allowed = new Set([
        "event_id", "write_document_id", "project_id", "title", "revision",
        "html_sha256", "visibility", "origin_kind", "replayed",
      ]);
      if (created.origin_kind !== "owner_native" || created.visibility !== "private" ||
          created.revision !== 1 || !HEX64.test(created.html_sha256) ||
          !/^ivwp-[0-9a-f]{32}$/.test(created.project_id) ||
          !/^ivwd-[0-9a-f]{32}$/.test(created.write_document_id) ||
          !/^ivwn-create-[0-9a-f]{25}$/.test(created.event_id) ||
          typeof created.replayed !== "boolean" || created.title !== title ||
          Object.keys(created).some((key) => !allowed.has(key))) {
        throw new Error("Create receipt is inconsistent");
      }
      onCreated({
        write_document_id: created.write_document_id, project_id: created.project_id,
        title: created.title, revision: 1, html_sha256: created.html_sha256,
        visibility: "private", origin_kind: "owner_native", updated_at: "pending-refresh",
      });
      setOpen(false);
    } catch (caught: unknown) {
      if ((caught as { name?: string }).name === "AbortError" ||
          generationRef.current !== requestGeneration) return;
      setState("error");
      setMessage(caught instanceof Error ? caught.message : "Manuscript creation failed");
    } finally { if (createAbortRef.current === abort) createAbortRef.current = null; }
  };

  return <>
    <button ref={invokerRef} type="button" onClick={begin} className="m-3 w-[calc(100%-1.5rem)] border border-ink px-3 py-2 text-left font-mono text-xs focus-visible:outline focus-visible:outline-2 dark:border-bright">＋ New manuscript</button>
    {open && <div className="fixed inset-0 z-[100] grid place-items-center bg-charcoal-2/60 p-4">
      <div ref={dialogRef} role="dialog" aria-modal="true" aria-labelledby="new-manuscript-title" className="w-full max-w-md border border-rule bg-ice-0 p-5 text-ink shadow-xl dark:border-charcoal-1 dark:bg-charcoal-2 dark:text-bright">
        <p className="font-mono text-[10px] uppercase tracking-[0.18em]">Owner-native Write</p>
        <h2 id="new-manuscript-title" className="mt-1 font-serif text-xl">New private manuscript</h2>
        <form onSubmit={(event) => void submit(event)}>
          <label className="mt-4 block text-xs" htmlFor="native-write-title">Title</label>
          <input id="native-write-title" value={title} maxLength={300} disabled={state === "creating"} onChange={(event) => setTitle(event.target.value)} className="mt-1 w-full border border-rule bg-transparent px-3 py-2 text-sm focus-visible:outline focus-visible:outline-2 dark:border-charcoal-1" />
          {message && <p role="alert" className="mt-2 text-xs text-danger">{message}</p>}
          <div className="mt-5 flex justify-end gap-2"><button type="button" disabled={state === "creating"} onClick={() => setOpen(false)} className="border border-rule px-3 py-1.5 text-xs dark:border-charcoal-1">Cancel</button><button type="submit" disabled={state === "creating" || !title.trim() || title !== title.trim()} className="border border-ink bg-ink px-3 py-1.5 text-xs text-ice-0 disabled:opacity-40 dark:border-bright">{state === "creating" ? "Creating…" : "Create manuscript"}</button></div>
        </form>
      </div>
    </div>}
  </>;
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
  const write = usePrivateWriteDocuments(workflow === "write");

  const pinnedKey = (n: TreeNode) => `${n.kind}:${n.id}`;

  const researchNodes = research.investigations.map(investigationNode);
  const readNodes = read.documents.map(documentNode);
  const writeNodes = write.documents.map(privateWriteNode);
  const recent =
    workflow === "research" ? researchNodes : workflow === "read" ? readNodes :
      workflow === "write" ? writeNodes : [];
  const recentLoading =
    workflow === "research" ? research.loading : workflow === "read" ? read.loading :
      workflow === "write" ? write.loading : false;
  const recentError =
    workflow === "research" ? research.error : workflow === "read" ? read.error :
      workflow === "write" ? write.error : null;
  const pinnedNodes = recent.filter((n) => pinned.has(pinnedKey(n)));
  const recentNodes = recent.filter((n) => !pinned.has(pinnedKey(n)));

  const [expanded, setExpanded] = useState<Record<string, boolean>>({
    pinned: true,
    recent: true,
    all: true,
  });

  const onItemClick = (n: TreeNode, e: React.MouseEvent) => {
    if (n.kind === "private-write") {
      if (!n.projectId) return;
      e.preventDefault();
      openPanel(
        "PrivateWrite", { projectId: n.projectId, writeDocumentId: n.id },
        { mode: "floating", title: n.title, id: `PrivateWrite:${n.projectId}:${n.id}` },
      );
      return;
    }
    if (e.metaKey || e.ctrlKey) {
      e.preventDefault();
      openPanel(panelKindForNode(n), { id: n.id }, { mode: "floating", title: n.title });
      return;
    }
    navigate(routeForNode(n));
  };

  const openPrivateWrite = (document: PrivateWriteDocumentSummaryShape) => {
    openPanel(
      "PrivateWrite",
      { projectId: document.project_id, writeDocumentId: document.write_document_id },
      { mode: "floating", title: document.title,
        id: `PrivateWrite:${document.project_id}:${document.write_document_id}` },
    );
    write.refresh();
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
      {workflow === "write" && <NewManuscriptAction onCreated={openPrivateWrite} />}
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
    "private-write": "✎",
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
