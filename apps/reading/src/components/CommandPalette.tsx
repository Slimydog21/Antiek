import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { apiFetch, type InvestigationSummary } from "../lib/api";
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
import {
  entryWorkflow as facetEntryWorkflow,
  leadingStateFilter as facetLeadingStateFilter,
  rankEntries as facetRankEntries,
  STATE_FILTERS,
} from "../shell/paletteFacet";
import {
  researchStateDotClass,
  researchStateFor,
  isUnseen as researchIsUnseen,
  type ResearchState,
} from "../shared/researchState";
import { lastSeenAt } from "../workspace/seen";
import LemonButton from "./lemon/LemonButton";
import { LemonModal } from "./lemon/LemonModal";
import { toast } from "./lemon/LemonToast";

/**
 * Command Palette (PostHog Wedge 3, master-spec §5.6 + §4.5).
 *
 * Cmd/Ctrl+K opens; ESC closes. Single fuzzy-search surface across:
 *   - Routes (workstation, brainstorm, notebooks, sources, privacy,
 *     pricing, operator dashboard, wrestler)
 *   - Investigations (GET /investigations)
 *   - Documents (GET /documents)
 *   - Notebooks (GET /notebooks)
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
  /** herdr transfer P0-5: state facet + unread axis for state: filters. */
  state?: ResearchState;
  unseen?: boolean;
}

interface PaletteDocument {
  kind: "document";
  id: string;
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

interface PaletteParkedQuestion {
  kind: "parked_question";
  id: string;
  title: string;
  subtitle: string;
  path: string;
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
  | PaletteParkedQuestion
  | PaletteAction;

const ROUTE_INDEX: PaletteRoute[] = [
  {
    kind: "route",
    id: "route:research",
    title: "Research workstation",
    subtitle: "Mode A — chat-first investigation surface (/)",
    path: "/",
  },
  {
    kind: "route",
    id: "route:wrestle",
    title: "Document wrestler",
    subtitle: "Mode B — PDF reading + region selection (/wrestle)",
    path: "/wrestle",
  },
  {
    kind: "route",
    id: "route:create",
    title: "Creation studio",
    subtitle: "Mode C — Lego-block writing (/create)",
    path: "/create",
  },
  {
    kind: "route",
    id: "route:sources",
    title: "Sources",
    subtitle: "Acquisition adapters (/sources)",
    path: "/sources",
  },
  {
    kind: "route",
    id: "route:brainstorm",
    title: "Brainstorm station",
    subtitle: "Mode E — watch-for-later + thought-partner (/brainstorm)",
    path: "/brainstorm",
  },
  {
    kind: "route",
    id: "route:privacy",
    title: "Privacy dashboard",
    subtitle: "ε exposure + delete-all (/privacy)",
    path: "/privacy",
  },
  {
    kind: "route",
    id: "route:pricing",
    title: "Pricing",
    subtitle: "OpenRouter-style calculator (/pricing)",
    path: "/pricing",
  },
  {
    kind: "route",
    id: "route:operator",
    title: "Operator dashboard",
    subtitle: "Pre-onboarded IP escrow (/operator)",
    path: "/operator",
  },
  {
    kind: "route",
    id: "route:trust",
    title: "Trust Center",
    subtitle: "ε budgets · deletion SLA · unlock status (/trust)",
    path: "/trust",
  },
  {
    kind: "route",
    id: "route:settings",
    title: "Settings",
    subtitle: "Application settings (/settings)",
    path: "/settings",
  },
  {
    kind: "route",
    id: "route:coordination",
    title: "Coordination",
    subtitle: "Gate ledger · roadmap · unified cost · escrow/consent (/coordination)",
    path: "/coordination",
  },
  {
    kind: "route",
    id: "route:loop3",
    title: "Loop 3 checklist",
    subtitle: "RL unlock criteria + env gate (/loop-3)",
    path: "/loop-3",
  },
  {
    kind: "route",
    id: "route:skill-rules",
    title: "Skill rules",
    subtitle: "Cross-user promoted rules (/skill-rules)",
    path: "/skill-rules",
  },
  {
    kind: "route",
    id: "route:speak",
    title: "Speak",
    subtitle: "Remember someone — invite their people, gather their voices (/speak)",
    path: "/speak",
  },
  {
    kind: "route",
    id: "route:federation",
    title: "Federation config",
    subtitle: "Cross-substrate policy (/federation)",
    path: "/federation",
  },
  {
    kind: "route",
    id: "route:outcomes-index",
    title: "Outcomes audit",
    subtitle: "Cross-investigation grading history (/outcomes)",
    path: "/outcomes",
  },
  {
    kind: "route",
    id: "route:investigations-index",
    title: "My research",
    subtitle: "One monitor over every running + completed research (/my-research)",
    path: "/my-research",
  },
  {
    kind: "route",
    id: "route:payouts",
    title: "Payouts audit",
    subtitle: "Stripe Connect transfer log (/payouts)",
    path: "/payouts",
  },
  {
    kind: "route",
    id: "route:notebooks-index",
    title: "Notebooks",
    subtitle: "Wedge 2 literate-analysis surface (/notebooks)",
    path: "/notebooks",
  },
  {
    kind: "route",
    id: "route:documents-index",
    title: "Documents",
    subtitle: "Substrate-attached sources by tier (/documents)",
    path: "/documents",
  },
  {
    kind: "route",
    id: "route:billing",
    title: "Billing",
    subtitle: "Free-tier usage + margin breakdown (/billing)",
    path: "/billing",
  },
  {
    kind: "route",
    id: "route:stats",
    title: "Substrate stats",
    subtitle: "Per-table cardinality dashboard (/stats)",
    path: "/stats",
  },
  {
    kind: "route",
    id: "route:map",
    title: "Application map",
    subtitle: "Index of every operator-facing surface (/map)",
    path: "/map",
  },
  {
    kind: "route",
    id: "route:cross-graph-citations",
    title: "Cross-graph citations",
    subtitle: "Record citations + rev-share (/cross-graph/citations)",
    path: "/cross-graph/citations",
  },
];

/**
 * SPR-04 — decorate every route entry with its workflow facet, derived
 * from the taxonomy's path→workflow resolver. Done mechanically rather
 * than hand-tagging 20+ rows so the facet can't drift from the taxonomy.
 */
const ROUTE_INDEX_WITH_FACET: PaletteRoute[] = ROUTE_INDEX.map((r) => ({
  ...r,
  workflow: workflowForPath(r.path),
}));

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

  const loadIndex = useCallback(async () => {
    try {
      const [iResp, dResp, nResp, pResp] = await Promise.all([
        apiFetch("/investigations").catch(() => null),
        apiFetch("/documents").catch(() => null),
        apiFetch("/notebooks").catch(() => null),
        apiFetch("/watch-for-later").catch(() => null),
      ]);

      if (iResp?.ok) {
        const data = await iResp.json();
        // Each investigation gets two palette rows: the workstation
        // surface (/inv/:id) and the trajectory replay (/replay/:id).
        // The replay route is canonical for operator-graded outcomes
        // per master-spec §14.1.
        const items: PaletteInvestigation[] = (
          data.investigations ?? []
        ).flatMap(
          (inv: {
            investigation_id: string;
            topic?: string;
            status?: string;
            completed_at?: string | null;
          }) => {
            // State facet (P0-5): the palette becomes a triage surface —
            // "state:blocked" shows what needs the operator. The replay row
            // shares the source investigation's state.
            const state =
              typeof inv.status === "string"
                ? researchStateFor(inv.status as InvestigationSummary["status"])
                : undefined;
            const unseen =
              state !== undefined && typeof inv.investigation_id === "string"
                ? researchIsUnseen(
                    {
                      status: inv.status as InvestigationSummary["status"],
                      completed_at: inv.completed_at ?? null,
                    },
                    lastSeenAt(inv.investigation_id),
                  )
                : false;
            return [
              {
                kind: "investigation" as const,
                id: `inv:${inv.investigation_id}`,
                title: inv.topic ?? inv.investigation_id,
                subtitle: `Investigation · ${inv.investigation_id.slice(0, 8)}`,
                path: `/inv/${inv.investigation_id}`,
                state,
                unseen,
              },
              {
                kind: "investigation" as const,
                id: `replay:${inv.investigation_id}`,
                title: `Replay: ${inv.topic ?? inv.investigation_id}`,
                subtitle: `Trajectory · ${inv.investigation_id.slice(0, 8)}`,
                path: `/replay/${inv.investigation_id}`,
                state,
                unseen,
              },
            ];
          },
        );
        setInvestigations(items);
      }

      if (dResp?.ok) {
        const data = await dResp.json();
        const items: PaletteDocument[] = (data.documents ?? []).map(
          (doc: { document_id: string; title?: string | null }) => ({
            kind: "document" as const,
            id: `doc:${doc.document_id}`,
            title: doc.title ?? doc.document_id,
            subtitle: `Document · ${doc.document_id.slice(0, 8)}`,
            path: `/wrestle/${doc.document_id}`,
          }),
        );
        setDocuments(items);
      }

      if (nResp?.ok) {
        const data = await nResp.json();
        const items: PaletteNotebook[] = (data.notebooks ?? []).map(
          (nb: { notebook_id: string; title: string }) => ({
            kind: "notebook" as const,
            id: `nb:${nb.notebook_id}`,
            title: nb.title,
            subtitle: `Notebook · ${nb.notebook_id.slice(0, 8)}`,
            path: `/notebook/${nb.notebook_id}`,
          }),
        );
        setNotebooks(items);
      }

      if (pResp?.ok) {
        const data = await pResp.json();
        const items: PaletteParkedQuestion[] = (data.parked ?? []).map(
          (q: { question_id: string; question_text: string }) => ({
            kind: "parked_question" as const,
            id: `pq:${q.question_id}`,
            title: q.question_text,
            subtitle: `Parked question · ${q.question_id.slice(0, 8)}`,
            path: `/brainstorm`,
          }),
        );
        setParked(items);
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
      ...parked,
    ],
    [workflowJumps, workspaceActions, investigations, documents, notebooks, parked],
  );

  const ranked = useMemo(
    () => rankEntries(entries, query).slice(0, 12),
    [entries, query],
  );

  const choose = (entry: PaletteEntry) => {
    if (entry.kind === "action") {
      entry.run();
    } else {
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
          placeholder="Type a route, investigation, document, or notebook… (try state:blocked)"
          className="w-full px-4 py-3 text-base font-serif text-ink dark:text-bright placeholder:text-ink-mute dark:text-moonlight outline-none border-b border-rule dark:border-charcoal-1"
        />
        {/* herdr transfer P0-5 — state-filter chips: the palette as a
            triage surface. Clicking a chip sets the `state:` query; the
            chip stays highlighted while its filter is active; the ✕ clears. */}
        <div className="flex items-center gap-1.5 px-4 py-1.5 border-b border-rule dark:border-charcoal-1 flex-wrap">
          {STATE_FILTERS.map((f) => {
            const active = facetLeadingStateFilter(query) === f;
            return (
              <button
                key={f}
                type="button"
                onClick={() => setQuery(active ? "" : `state:${f}`)}
                className={`text-[11px] font-mono px-2 py-0.5 rounded-full border transition-colors ${
                  active
                    ? "bg-sun text-ink border-sun"
                    : "border-rule dark:border-charcoal-1 text-shadow-1 dark:text-moonlight hover:text-ink dark:hover:text-bright"
                }`}
              >
                {f}
              </button>
            );
          })}
          {facetLeadingStateFilter(query) && (
            <button
              type="button"
              onClick={() => setQuery("")}
              className="text-[11px] font-mono px-2 py-0.5 text-shadow-1 dark:text-moonlight hover:text-emperor"
            >
              ✕ clear
            </button>
          )}
        </div>
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
                  {"state" in e && e.state && (
                    <span
                      aria-label={e.state + (e.unseen ? " · unseen" : "")}
                      title={e.state + (e.unseen ? " · unseen" : "")}
                      className={`w-2 h-2 rounded-full shrink-0 ${researchStateDotClass(
                        e.state,
                        e.unseen === true,
                      )}`}
                    />
                  )}
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
