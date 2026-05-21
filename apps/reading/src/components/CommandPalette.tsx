import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { apiFetch } from "../lib/api";

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

export type PaletteEntry =
  | PaletteRoute
  | PaletteInvestigation
  | PaletteDocument
  | PaletteNotebook
  | PaletteParkedQuestion;

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
    id: "route:interviews",
    title: "Interviews",
    subtitle: "Projects + invited informants (/interviews)",
    path: "/interviews",
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
    title: "Investigations index",
    subtitle: "All investigations + replay links (/investigations)",
    path: "/investigations",
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

export function rankEntries(
  entries: PaletteEntry[],
  query: string,
): PaletteEntry[] {
  const q = query.trim().toLowerCase();
  if (!q) return entries;
  const scored = entries
    .map((e) => {
      const hay = `${e.title} ${e.subtitle}`.toLowerCase();
      // Substring is the strongest signal (rank 0). Otherwise score
      // by token-match count.
      if (hay.includes(q)) {
        return { e, score: hay.indexOf(q) };
      }
      const tokens = q.split(/\s+/);
      const hits = tokens.filter((t) => hay.includes(t)).length;
      return hits ? { e, score: 1000 - hits * 10 } : null;
    })
    .filter((x): x is { e: PaletteEntry; score: number } => x !== null);
  scored.sort((a, b) => a.score - b.score);
  return scored.map((s) => s.e);
}

export default function CommandPalette() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [investigations, setInvestigations] = useState<PaletteInvestigation[]>([]);
  const [documents, setDocuments] = useState<PaletteDocument[]>([]);
  const [notebooks, setNotebooks] = useState<PaletteNotebook[]>([]);
  const [parked, setParked] = useState<PaletteParkedQuestion[]>([]);
  const [activeIdx, setActiveIdx] = useState(0);
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
          (inv: { investigation_id: string; topic?: string }) => [
            {
              kind: "investigation" as const,
              id: `inv:${inv.investigation_id}`,
              title: inv.topic ?? inv.investigation_id,
              subtitle: `Investigation · ${inv.investigation_id.slice(0, 8)}`,
              path: `/inv/${inv.investigation_id}`,
            },
            {
              kind: "investigation" as const,
              id: `replay:${inv.investigation_id}`,
              title: `Replay: ${inv.topic ?? inv.investigation_id}`,
              subtitle: `Trajectory · ${inv.investigation_id.slice(0, 8)}`,
              path: `/replay/${inv.investigation_id}`,
            },
          ],
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
    // so the Topbar search input click + the keyboard handler both
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

  const entries = useMemo<PaletteEntry[]>(
    () => [
      ...ROUTE_INDEX,
      ...investigations,
      ...documents,
      ...notebooks,
      ...parked,
    ],
    [investigations, documents, notebooks, parked],
  );

  const ranked = useMemo(
    () => rankEntries(entries, query).slice(0, 12),
    [entries, query],
  );

  const choose = (entry: PaletteEntry) => {
    navigate(entry.path);
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
          placeholder="Type a route, investigation, document, or notebook…"
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
                <span className="text-[10px] uppercase tracking-wider font-mono text-shadow-1 dark:text-moonlight bg-ice-3 dark:bg-charcoal-1 px-1.5 py-0.5 rounded">
                  {e.kind.replace("_", " ")}
                </span>
              </li>
            ))
          )}
        </ul>
        <footer className="px-4 py-2 border-t border-rule dark:border-charcoal-1 bg-ice-1 dark:bg-charcoal-2 text-[11px] font-mono text-shadow-1 dark:text-moonlight flex items-center justify-between">
          <span>↑↓ navigate · Enter select · Esc close</span>
          <span>⌘K toggle</span>
        </footer>
      </div>
    </div>
  );
}
