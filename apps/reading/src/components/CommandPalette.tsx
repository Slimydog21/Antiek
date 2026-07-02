import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { apiFetch, type ParkedQuestionEntry } from "../lib/api";
import { useOpenDocument } from "../lib/openDocument";
import {
  dispatchBrainstormQuestionSelection,
} from "../modes/BrainstormStation/WatchForLaterPanel";
import { openNotebook } from "../workspace/actions";
import {
  buildShareableUrl,
  clearAll,
  clearScope,
  project,
} from "../workspace/persistence";
import { SHORTCUT_EVENTS } from "../workspace/shortcuts";
import { useWorkspace } from "../workspace/WorkspaceStore";
import {
  WORKFLOWS,
  WORKFLOW_ORDER,
  workflowForPath,
  type Workflow,
} from "../shell/workflowTaxonomy";
import { OPERATOR_ROUTES } from "../shell/operatorRoutes";
import {
  entryWorkflow as facetEntryWorkflow,
  rankEntries as facetRankEntries,
} from "../shell/paletteFacet";
import LemonButton from "./lemon/LemonButton";
import { LemonModal } from "./lemon/LemonModal";
import { toast } from "./lemon/LemonToast";

/**
 * Command Palette (PostHog Wedge 3, master-spec §5.6 + §4.5).
 *
 * Cmd/Ctrl+K opens; ESC closes. Single fuzzy-search surface across:
 *   - Routes (workflow doors, built workflow surfaces, governance,
 *     pricing, operator dashboard)
 *   - Investigations (GET /investigations)
 *   - Documents (GET /documents)
 *   - Notebooks (GET /notebooks)
 *   - Write pieces (GET /deliverables)
 *   - Parked questions / watch-for-later (GET /watch-for-later)
 *
 * Per master-spec §5.6 PostHog philosophy: 'transparent intelligence,
 * not magic'. The palette shows the source kind, the matched text,
 * and an explicit navigation target. No agentic suggestions; this is
 * a navigation primitive, not an LLM surface.
 *
 * Per §10.2 retrieval-time gates: this palette only ever shows
 * already-loaded substrate; cross-graph results are filtered by the
 * backend before the palette ever sees them.
 */

interface PaletteRoute {
  kind: "route";
  id: string;
  title: string;
  subtitle: string;
  path: string;
  /** SPR-04 — workflow facet, used for grouping + workflow-scoped filter. */
  workflow?: Workflow;
}

interface PaletteInvestigation {
  kind: "investigation";
  id: string;
  title: string;
  subtitle: string;
  path: string;
}

interface PaletteDocument {
  kind: "document";
  id: string;
  documentId: string;
  title: string;
  subtitle: string;
  path: string;
}

interface PaletteNotebook {
  kind: "notebook";
  id: string;
  title: string;
  subtitle: string;
  path: string;
}

interface PaletteDeliverable {
  kind: "deliverable";
  id: string;
  title: string;
  subtitle: string;
  path: string;
}

interface PaletteParkedQuestion {
  kind: "parked_question";
  id: string;
  title: string;
  subtitle: string;
  path: string;
  question: ParkedQuestionEntry;
}

/** S8-full extension — workspace-system action (open panel, reset
 *  layout, copy shareable link, etc.). Actions have no path; instead
 *  they expose a `run` callback the palette invokes on select. */
interface PaletteAction {
  kind: "action";
  id: string;
  title: string;
  subtitle: string;
  run: () => void;
  /** SPR-04 — workflow facet (e.g. a "go to Read" jump action). */
  workflow?: Workflow;
}

export type PaletteEntry =
  | PaletteRoute
  | PaletteInvestigation
  | PaletteDocument
  | PaletteNotebook
  | PaletteDeliverable
  | PaletteParkedQuestion
  | PaletteAction;

const ROUTE_INDEX: PaletteRoute[] = OPERATOR_ROUTES.map((route) => ({
  kind: "route",
  id: `route:${route.id}`,
  title: route.title,
  subtitle: route.paletteSubtitle ?? route.description,
  path: route.path,
  workflow: route.workflow,
}));

/**
 * SPR-04 — decorate every route entry with its workflow facet, derived
 * from the taxonomy's path→workflow resolver. Done mechanically rather
 * than hand-tagging 20+ rows so the facet can't drift from the taxonomy.
 */
const ROUTE_INDEX_WITH_FACET: PaletteRoute[] = ROUTE_INDEX.map((r) => ({
  ...r,
  workflow: r.workflow ?? workflowForPath(r.path),
}));

function record(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function nonEmptyString(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

function nullableString(value: unknown): string | null {
  return value == null ? null : nonEmptyString(value);
}

function finiteNonNegativeNumber(value: unknown): number | null {
  const parsed =
    typeof value === "number"
      ? value
      : typeof value === "string" && value.trim() !== ""
        ? Number(value)
        : Number.NaN;
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : null;
}

function safeInvestigations(value: unknown): PaletteInvestigation[] {
  const body = record(value);
  const investigations = Array.isArray(body?.investigations) ? body.investigations : [];
  return investigations.flatMap((item) => {
    const inv = record(item);
    const investigationId = nonEmptyString(inv?.investigation_id);
    if (!investigationId) return [];
    const topic = nonEmptyString(inv?.topic) ?? investigationId;
    const encodedInvestigationId = encodeURIComponent(investigationId);
    return [
      {
        kind: "investigation" as const,
        id: `inv:${investigationId}`,
        title: topic,
        subtitle: `Investigation · ${investigationId.slice(0, 8)}`,
        path: `/inv/${encodedInvestigationId}`,
      },
      {
        kind: "investigation" as const,
        id: `replay:${investigationId}`,
        title: `Replay: ${topic}`,
        subtitle: `Trajectory · ${investigationId.slice(0, 8)}`,
        path: `/replay/${encodedInvestigationId}`,
      },
    ];
  });
}

function safeDocuments(value: unknown): PaletteDocument[] {
  const body = record(value);
  const documents = Array.isArray(body?.documents) ? body.documents : [];
  return documents.flatMap((item) => {
    const doc = record(item);
    const documentId = nonEmptyString(doc?.document_id);
    if (!documentId) return [];
    return [{
      kind: "document" as const,
      id: `doc:${documentId}`,
      documentId,
      title: nullableString(doc?.title) ?? documentId,
      subtitle: `Document · ${documentId.slice(0, 8)}`,
      path: `/read/${encodeURIComponent(documentId)}`,
    }];
  });
}

function safeNotebooks(value: unknown): PaletteNotebook[] {
  const body = record(value);
  const notebooks = Array.isArray(body?.notebooks) ? body.notebooks : [];
  return notebooks.flatMap((item) => {
    const nb = record(item);
    const notebookId = nonEmptyString(nb?.notebook_id);
    if (!notebookId) return [];
    return [{
      kind: "notebook" as const,
      id: `nb:${notebookId}`,
      title: nonEmptyString(nb?.title) ?? notebookId,
      subtitle: `Notebook · ${notebookId.slice(0, 8)}`,
      path: `/notebook/${encodeURIComponent(notebookId)}`,
    }];
  });
}

function safeDeliverables(value: unknown): PaletteDeliverable[] {
  const body = record(value);
  const deliverables = Array.isArray(body?.deliverables) ? body.deliverables : [];
  return deliverables.flatMap((item) => {
    const d = record(item);
    const deliverableId = nonEmptyString(d?.deliverable_id);
    if (!deliverableId) return [];
    const sectionCount = Math.floor(finiteNonNegativeNumber(d?.section_count) ?? 0);
    const linked = nonEmptyString(d?.investigation_root_id) ? " · linked research" : "";
    return [{
      kind: "deliverable" as const,
      id: `dlv:${deliverableId}`,
      title: nonEmptyString(d?.title) ?? "Untitled piece",
      subtitle: `Piece · ${sectionCount} section${sectionCount === 1 ? "" : "s"}${linked}`,
      path: `/write/${encodeURIComponent(deliverableId)}`,
    }];
  });
}

function safeParkedQuestion(value: unknown): ParkedQuestionEntry | null {
  const q = record(value);
  if (!q) return null;
  const questionId = nonEmptyString(q.question_id);
  const questionText = nonEmptyString(q.question_text);
  const sourceInvestigationId = nonEmptyString(q.source_investigation_id);
  const parkedAt = nonEmptyString(q.parked_at);
  if (!questionId || !questionText || !sourceInvestigationId || !parkedAt) return null;
  return {
    question_id: questionId,
    question_text: questionText,
    source_investigation_id: sourceInvestigationId,
    source_document_id: nullableString(q.source_document_id),
    anchor_region_id: nullableString(q.anchor_region_id),
    parked_at: parkedAt,
    parent_event_id: nullableString(q.parent_event_id),
  };
}

function safeParkedQuestions(value: unknown): PaletteParkedQuestion[] {
  const body = record(value);
  const rawQuestions = Array.isArray(body?.questions)
    ? body.questions
    : Array.isArray(body?.parked)
      ? body.parked
      : [];
  return rawQuestions.flatMap((item) => {
    const question = safeParkedQuestion(item);
    if (!question) return [];
    return [{
      kind: "parked_question" as const,
      id: `pq:${question.question_id}`,
      title: question.question_text,
      subtitle: `Parked question · ${question.question_id.slice(0, 8)}`,
      path: "/brainstorm",
      question,
    }];
  });
}

/**
 * SPR-04 — workflow-jump commands. Typing "research", "read", "write",
 * or "speak" surfaces a "Go to <Workflow>" command at the top. These are
 * the rail's four workflows as palette entries.
 */
function buildWorkflowJumps(navigate: (p: string) => void): PaletteAction[] {
  return WORKFLOW_ORDER.map((wf) => ({
    kind: "action" as const,
    id: `wf:goto:${wf}`,
    title: `Go to ${WORKFLOWS[wf].label}`,
    subtitle: WORKFLOWS[wf].tagline,
    workflow: wf,
    run: () => navigate(WORKFLOWS[wf].defaultRoute),
  }));
}

/**
 * Public re-exports of the pure facet logic. The implementation lives in
 * src/shell/paletteFacet.ts so it can be unit-tested without importing
 * this component (which pulls in lib/api + the data layer). Kept here so
 * existing callers/tests that import from CommandPalette keep working.
 */
export function entryWorkflow(e: PaletteEntry): Workflow | undefined {
  return facetEntryWorkflow(e);
}

export function rankEntries(
  entries: PaletteEntry[],
  query: string,
): PaletteEntry[] {
  return facetRankEntries(entries, query);
}

export default function CommandPalette() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [investigations, setInvestigations] = useState<PaletteInvestigation[]>([]);
  const [documents, setDocuments] = useState<PaletteDocument[]>([]);
  const [notebooks, setNotebooks] = useState<PaletteNotebook[]>([]);
  const [deliverables, setDeliverables] = useState<PaletteDeliverable[]>([]);
  const [parked, setParked] = useState<PaletteParkedQuestion[]>([]);
  const [activeIdx, setActiveIdx] = useState(0);
  // S9 acceptance: destructive layout-reset commands confirm via a
  // LemonModal before clearing. The palette stores the pending
  // destructive action; the modal renders alongside the palette.
  const [pendingDestructive, setPendingDestructive] = useState<
    | { kind: "reset-all"; count: number }
    | null
  >(null);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const navigate = useNavigate();
  const openDocument = useOpenDocument();

  const loadIndex = useCallback(async () => {
    try {
      const [iResp, dResp, nResp, dlvResp, pResp] = await Promise.all([
        apiFetch("/investigations").catch(() => null),
        apiFetch("/documents").catch(() => null),
        apiFetch("/notebooks").catch(() => null),
        apiFetch("/deliverables").catch(() => null),
        apiFetch("/watch-for-later").catch(() => null),
      ]);

      if (iResp?.ok) {
        // Each investigation gets two palette rows: Research home
        // surface (/inv/:id) and the trajectory replay (/replay/:id).
        // The replay route is canonical for operator-graded outcomes
        // per master-spec §14.1.
        setInvestigations(safeInvestigations(await iResp.json()));
      }

      if (dResp?.ok) {
        // SPR-05 one door: open in the ONE Reader (the gated /read/:id route
        // openDocument navigates to) — was a /wrestle/:id mis-route (the
        // pdf.js page-1 surface that can't fetch by id). The palette keeps the
        // canonical path for ranking/display, but selection calls
        // openDocument(id) so future reader options stay behind one resolver.
        setDocuments(safeDocuments(await dResp.json()));
      }

      if (nResp?.ok) {
        setNotebooks(safeNotebooks(await nResp.json()));
      }

      if (dlvResp?.ok) {
        setDeliverables(safeDeliverables(await dlvResp.json()));
      }

      if (pResp?.ok) {
        setParked(safeParkedQuestions(await pResp.json()));
      }
    } catch {
      // Palette is best-effort; offline state still shows ROUTE_INDEX.
    }
  }, []);

  useEffect(() => {
    // S8: the workspace shortcuts module (src/workspace/shortcuts.ts)
    // owns the ⌘K binding now and dispatches "antiek:palette:toggle"
    // so the NavRail Search button click + the keyboard handler both
    // reach the same code path. We also keep an in-component ⌘K
    // fallback so the palette still works when AppShell isn't the
    // ancestor (e.g. in Storybook stories rendered without AppShell).
    const onToggle = () => setOpen((v) => !v);
    window.addEventListener(
      "antiek:palette:toggle" as keyof WindowEventMap,
      onToggle as EventListener,
    );

    const handler = (e: KeyboardEvent) => {
      const isToggle =
        (e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k";
      if (isToggle) {
        e.preventDefault();
        setOpen((v) => !v);
        return;
      }
      if (e.key === "Escape" && open) {
        e.preventDefault();
        setOpen(false);
      }
    };
    window.addEventListener("keydown", handler);

    return () => {
      window.removeEventListener(
        "antiek:palette:toggle" as keyof WindowEventMap,
        onToggle as EventListener,
      );
      window.removeEventListener("keydown", handler);
    };
  }, [open]);

  useEffect(() => {
    if (open) {
      void loadIndex();
      // Defer focus until after the dialog mounts.
      setTimeout(() => inputRef.current?.focus(), 0);
    } else {
      setQuery("");
      setActiveIdx(0);
    }
  }, [open, loadIndex]);

  // S8-full — workspace actions over the active store. Built per-render
  // so the action set reflects whatever panels are currently open.
  const wsPanels = useWorkspace((s) => s.panels);
  const workspaceActions = useMemo<PaletteAction[]>(() => {
    const actions: PaletteAction[] = [
      {
        kind: "action",
        id: "ws:open-project-tree",
        title: "Open Project tree",
        subtitle: "Workspace · dock left (⌘B)",
        run: () => {
          const ws = useWorkspace.getState();
          if (ws.panels["shortcuts:projecttree"]) return;
          ws.open("ProjectTree", {}, {
            mode: "docked-left",
            title: "Project",
            id: "shortcuts:projecttree",
          });
        },
      },
      {
        kind: "action",
        id: "ws:open-notebook-editor",
        title: "Open new notebook (editor)",
        subtitle: "Workspace · floating · TipTap editor",
        run: () => {
          openNotebook({ kind: "NotebookEditor", mode: "floating" });
        },
      },
      {
        kind: "action",
        id: "ws:toggle-aisidecar",
        title: "Toggle AI sidecar",
        subtitle: "Workspace · ⌘/",
        run: () => {
          window.dispatchEvent(
            new CustomEvent(SHORTCUT_EVENTS.AISIDECAR_TOGGLE),
          );
        },
      },
      {
        kind: "action",
        id: "ws:copy-shareable-layout",
        title: "Copy shareable layout link",
        subtitle: "Workspace · ?ws=… URL",
        run: () => {
          const url = buildShareableUrl(project(useWorkspace.getState()));
          if (url && navigator.clipboard) {
            void navigator.clipboard.writeText(url);
            toast.ok("Shareable layout link copied.");
          } else {
            toast.warn("Could not copy — clipboard unavailable.");
          }
        },
      },
      {
        kind: "action",
        id: "ws:reset-layout-route",
        title: "Reset workspace layout (this route)",
        subtitle: "Workspace · clears the per-route saved layout",
        run: () => {
          // Compute the route key the same way useWorkspaceHydration does;
          // we conservatively use the current pathname.
          const path =
            typeof window !== "undefined" ? window.location.pathname : "/";
          clearScope({ kind: "route", route: path });
          useWorkspace.getState().reset();
          toast.ok("Layout reset for this route.");
        },
      },
      {
        // S9 acceptance: "Reset layout (this investigation)" — the
        // third palette reset command. Pulled the investigation id
        // from the current URL via a /inv/:id pathname match.
        kind: "action",
        id: "ws:reset-layout-investigation",
        title: "Reset workspace layout (this investigation)",
        subtitle: "Workspace · clears the per-investigation saved layout",
        run: () => {
          const path =
            typeof window !== "undefined" ? window.location.pathname : "/";
          const m = path.match(/\/inv\/([^/]+)/);
          if (!m) {
            toast.warn("No investigation in URL — nothing to reset.");
            return;
          }
          clearScope({ kind: "investigation", id: m[1] });
          useWorkspace.getState().reset();
          toast.ok(`Layout reset for investigation ${m[1].slice(0, 8)}.`);
        },
      },
      {
        kind: "action",
        id: "ws:reset-layouts-all",
        title: "Reset ALL workspace layouts",
        subtitle: "Workspace · wipes every antiek.workspace.* key",
        run: () => {
          // S9 acceptance: confirm-via-LemonModal before clearing.
          // Stash the pending action; the modal below confirms.
          // We do a dry-count for the modal copy.
          let count = 0;
          try {
            for (let i = 0; i < window.localStorage.length; i++) {
              const k = window.localStorage.key(i);
              if (k && k.startsWith("antiek.workspace.")) count++;
            }
          } catch {
            // ignore
          }
          setPendingDestructive({ kind: "reset-all", count });
        },
      },
    ];

    // Per-panel actions (dock-l/r/bottom, float, popout, close).
    const visiblePanelEntries: PaletteAction[] = Object.values(wsPanels)
      .slice(0, 20) // cap so the palette doesn't bloat
      .flatMap((p) => [
        {
          kind: "action" as const,
          id: `ws:${p.id}:dock-left`,
          title: `${p.title} → Dock left`,
          subtitle: "Panel · move",
          run: () => useWorkspace.getState().setMode(p.id, "docked-left"),
        },
        {
          kind: "action" as const,
          id: `ws:${p.id}:dock-right`,
          title: `${p.title} → Dock right`,
          subtitle: "Panel · move",
          run: () => useWorkspace.getState().setMode(p.id, "docked-right"),
        },
        {
          kind: "action" as const,
          id: `ws:${p.id}:float`,
          title: `${p.title} → Float`,
          subtitle: "Panel · move",
          run: () => useWorkspace.getState().setMode(p.id, "floating"),
        },
        {
          kind: "action" as const,
          id: `ws:${p.id}:close`,
          title: `${p.title} → Close`,
          subtitle: "Panel · close",
          run: () => useWorkspace.getState().close(p.id),
        },
      ]);

    return [...actions, ...visiblePanelEntries];
  }, [wsPanels]);

  const workflowJumps = useMemo<PaletteAction[]>(
    () => buildWorkflowJumps(navigate),
    [navigate],
  );

  const entries = useMemo<PaletteEntry[]>(
    () => [
      ...workflowJumps,
      ...workspaceActions,
      ...ROUTE_INDEX_WITH_FACET,
      ...investigations,
      ...documents,
      ...notebooks,
      ...deliverables,
      ...parked,
    ],
    [
      workflowJumps,
      workspaceActions,
      investigations,
      documents,
      notebooks,
      deliverables,
      parked,
    ],
  );

  const ranked = useMemo(
    () => rankEntries(entries, query).slice(0, 12),
    [entries, query],
  );

  const choose = (entry: PaletteEntry) => {
    if (entry.kind === "action") {
      entry.run();
    } else {
      if (entry.kind === "parked_question") {
        dispatchBrainstormQuestionSelection(entry.question);
      } else if (entry.kind === "document") {
        openDocument(entry.documentId);
        setOpen(false);
        return;
      }
      navigate(entry.path);
    }
    setOpen(false);
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveIdx((idx) => Math.min(idx + 1, ranked.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveIdx((idx) => Math.max(idx - 1, 0));
    } else if (e.key === "Enter" && ranked[activeIdx]) {
      e.preventDefault();
      choose(ranked[activeIdx]);
    }
  };

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 bg-ink/40 flex items-start justify-center pt-24"
      onClick={() => setOpen(false)}
      role="dialog"
      aria-modal="true"
      aria-label="Command palette"
    >
      <div
        className="w-[640px] max-w-[90vw] bg-ice-0 dark:bg-charcoal-2 border border-rule dark:border-charcoal-1 rounded-lg shadow-2xl overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setActiveIdx(0);
          }}
          onKeyDown={onKeyDown}
          placeholder="Type a route, investigation, document, notebook, or piece…"
          className="w-full px-4 py-3 text-base font-serif text-ink dark:text-bright placeholder:text-ink-mute dark:text-moonlight outline-none border-b border-rule dark:border-charcoal-1"
        />
        <ul className="max-h-[400px] overflow-y-auto">
          {ranked.length === 0 ? (
            <li className="px-4 py-6 text-sm text-shadow-1 dark:text-moonlight italic">
              No matches.
            </li>
          ) : (
            ranked.map((e, idx) => (
              <li
                key={e.id}
                onMouseEnter={() => setActiveIdx(idx)}
                onClick={() => choose(e)}
                className={`px-4 py-2.5 cursor-pointer flex items-center justify-between gap-3 ${
                  idx === activeIdx ? "bg-ice-3 dark:bg-charcoal-1" : ""
                }`}
              >
                <div className="min-w-0">
                  <p className="text-sm text-ink dark:text-bright truncate font-serif">
                    {e.title}
                  </p>
                  <p className="text-xs text-shadow-1 dark:text-moonlight truncate">
                    {e.subtitle}
                  </p>
                </div>
                <div className="flex items-center gap-1.5 shrink-0">
                  {(() => {
                    const wf = entryWorkflow(e);
                    return wf && wf !== "shared" ? (
                      <span className="text-[10px] uppercase tracking-wider font-mono text-ink bg-sun/70 px-1.5 py-0.5 rounded">
                        {WORKFLOWS[wf].label}
                      </span>
                    ) : null;
                  })()}
                  <span className="text-[10px] uppercase tracking-wider font-mono text-shadow-1 dark:text-moonlight bg-ice-3 dark:bg-charcoal-1 px-1.5 py-0.5 rounded">
                    {e.kind.replace("_", " ")}
                  </span>
                </div>
              </li>
            ))
          )}
        </ul>
        <footer className="px-4 py-2 border-t border-rule dark:border-charcoal-1 bg-ice-1 dark:bg-charcoal-2 text-[11px] font-mono text-shadow-1 dark:text-moonlight flex items-center justify-between">
          <span>↑↓ navigate · Enter select · Esc close</span>
          <span>⌘K toggle</span>
        </footer>
      </div>

      {/* S9 acceptance: confirm-via-LemonModal before the destructive
          all-layouts reset. The modal sits in the palette's portal so
          it overlays even when the palette itself is open. */}
      <LemonModal
        open={pendingDestructive?.kind === "reset-all"}
        onClose={() => setPendingDestructive(null)}
        title="Reset ALL workspace layouts?"
        forceUserAction
        footer={
          <div className="flex items-center justify-end gap-2">
            <LemonButton
              variant="secondary"
              onClick={() => setPendingDestructive(null)}
            >
              Cancel
            </LemonButton>
            <LemonButton
              variant="danger"
              onClick={() => {
                const n = clearAll();
                useWorkspace.getState().reset();
                setPendingDestructive(null);
                toast.warn(`Wiped ${n} saved layout(s).`);
              }}
            >
              Wipe all layouts
            </LemonButton>
          </div>
        }
      >
        <p className="text-sm text-ink dark:text-bright">
          This deletes every <code>antiek.workspace.*</code> key in
          localStorage —{" "}
          <strong>{pendingDestructive?.count ?? 0}</strong> stored layout
          {(pendingDestructive?.count ?? 0) === 1 ? "" : "s"}. Per-route
          and per-investigation snapshots are gone; the operator falls
          back to default starters.
        </p>
        <p className="text-xs font-mono text-shadow-1 dark:text-moonlight mt-3">
          Use "Reset workspace layout (this route)" or "(this
          investigation)" if you only want to clear a single scope.
        </p>
      </LemonModal>
    </div>
  );
}
