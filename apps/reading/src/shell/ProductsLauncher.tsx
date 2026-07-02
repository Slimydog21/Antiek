import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { LemonTag } from "../components/lemon/LemonTag";
import { openWindow, windowKindForRoute } from "../components/windows/openWindow";
import { listDeliverables, type DeliverableSummary } from "../lib/api";
import { destinationForMode } from "./modeDestinations";
import {
  MODE_TAXONOMY,
  WORKFLOWS,
  WORKFLOW_ORDER,
  type ModeEntry,
  type Workflow,
} from "./workflowTaxonomy";

// Local to the launcher surface only. Keeps the taxonomy (the shared source
// for NavRail, ProjectTree, stubs, palette, and the future M2 rail-destination
// guard) free of presentation concerns. These are the human labels the
// operator sees in the calm "More" drawer.
//
// Cost & consent (escrow/IP-holder consent + unified cost) is intentionally
// not a top-level MODE_TAXONOMY entry; it lives as content inside the
// Coordination shared surface (see taxonomy sharedReason and blurb).
// Documented here for M4 clarity so the launcher remains the honest
// inventory without duplicating taxonomy.
const RUN_LABELS: Record<string, string> = {
  OperatorDashboard: "Operator console",
  TrustCenter: "Trust Center",
  PrivacyDashboard: "Privacy dashboard",
  Billing: "Billing & usage",
  Settings: "Settings",
  Coordination: "Coordination",
};

type LauncherWritePiece = {
  id: string;
  title: string;
  subtitle: string;
};

type LauncherItem =
  | { kind: "mode"; key: string; mode: ModeEntry }
  | { kind: "write-piece"; key: string; piece: LauncherWritePiece };

function nonEmptyString(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

function safeWritePiece(value: unknown): LauncherWritePiece | null {
  const row =
    typeof value === "object" && value !== null && !Array.isArray(value)
      ? (value as Partial<DeliverableSummary>)
      : null;
  const id = nonEmptyString(row?.deliverable_id);
  if (!id) return null;
  const sectionCount = Math.max(
    0,
    Math.floor(
      typeof row?.section_count === "number"
        ? row.section_count
        : Number(row?.section_count),
    ) || 0,
  );
  const linked = nonEmptyString(row?.investigation_root_id)
    ? " · linked research"
    : "";
  return {
    id,
    title: nonEmptyString(row?.title) ?? "Untitled piece",
    subtitle: `${sectionCount} section${sectionCount === 1 ? "" : "s"}${linked}`,
  };
}

/**
 * ProductsLauncher (SPR-04 zone-1 grid). The honest full inventory of every
 * mode, presented as two calm top-level groups: workflow deep/power modes
 * (under their four human workflow labels) and Run & settings (Operator,
 * Trust, Settings, governance and debug surfaces, every shared taxonomy
 * entry exactly once with human labels).
 *
 * This is the pressure-release valve that lets the rail stay at exactly
 * four workflows. Deep modes and the entire operator bucket live here and
 * in the ⌘K palette, never on the rail. It is the honesty surface: an
 * unbuilt mode is shown dimmed with a "not yet" tag rather than hidden or
 * faked as present. Data-driven from MODE_TAXONOMY; a tiny local label map
 * here supplies the calm human surface names without touching the single
 * source used by rail, tree, stubs and palette.
 *
 * Presentation note (post M4 sharpen): rendered as a fixed centered overlay
 * (inset-0 z-50 pt-20 w-[760px] card, role=dialog aria-modal). The "drawer"
 * language in the broader spec is aspirational; the implementation is a
 * modal/overlay for immediate accessibility and keyboard parity with ⌘K.
 */
export function ProductsLauncher({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  const [writePieces, setWritePieces] = useState<LauncherWritePiece[]>([]);

  useEffect(() => {
    if (!open) {
      setQuery("");
      setActiveIndex(0);
      setWritePieces([]);
      return;
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    listDeliverables()
      .then((body) => {
        if (cancelled) return;
        const pieces = Array.isArray(body.deliverables)
          ? body.deliverables.flatMap((piece) => {
              const safe = safeWritePiece(piece);
              return safe ? [safe] : [];
            })
          : [];
        setWritePieces(pieces);
      })
      .catch(() => {
        if (!cancelled) setWritePieces([]);
      });
    return () => {
      cancelled = true;
    };
  }, [open]);

  // Two top-level groups only: workflow deep modes (the four workflows'
  // power surfaces, presented under their own human labels) vs the run
  // & settings bucket (every shared/operator entry exactly once, human
  // labeled, never using "shared" or class tokens in the UI).
  const { wfGroups, runModes, filteredWritePieces, flatItems } = useMemo(() => {
    const q = query.trim().toLowerCase();
    const match = (m: ModeEntry) =>
      !q ||
      m.label.toLowerCase().includes(q) ||
      m.blurb.toLowerCase().includes(q) ||
      m.id.toLowerCase().includes(q);
    const matchPiece = (p: LauncherWritePiece) =>
      !q ||
      p.title.toLowerCase().includes(q) ||
      p.subtitle.toLowerCase().includes(q) ||
      p.id.toLowerCase().includes(q) ||
      "write piece deliverable writing".includes(q);

    const wfGroups = WORKFLOW_ORDER.map((wf) => ({
      workflow: wf,
      label: WORKFLOWS[wf].label,
      modes: MODE_TAXONOMY.filter((m) => m.workflow === wf && match(m)),
    })).filter((g) => g.modes.length > 0);

    const rawRun = MODE_TAXONOMY.filter(
      (m) => m.workflow === "shared" && match(m),
    );
    const runModes = rawRun.map((m) => ({
      ...m,
      label: RUN_LABELS[m.id] ?? m.label,
    }));

    const filteredWritePieces = writePieces.filter(matchPiece);
    const flatItems: LauncherItem[] = [
      ...filteredWritePieces.map((piece) => ({
        kind: "write-piece" as const,
        key: `piece:${piece.id}`,
        piece,
      })),
      ...wfGroups.flatMap((g) =>
        g.modes.map((mode) => ({
          kind: "mode" as const,
          key: `mode:${mode.id}`,
          mode,
        })),
      ),
      ...rawRun.map((mode) => ({
        kind: "mode" as const,
        key: `mode:${mode.id}`,
        mode,
      })),
    ];
    return { wfGroups, runModes, filteredWritePieces, flatItems };
  }, [query, writePieces]);

  useEffect(() => {
    if (flatItems.length > 0 && activeIndex >= flatItems.length) {
      setActiveIndex(0);
    }
  }, [flatItems.length]);

  if (!open) return null;

  const openMode = (m: ModeEntry) => {
    const target = destinationForMode(m);
    if (!target) return;
    navigate(target);
    onClose();
  };

  const openWritePiece = (piece: LauncherWritePiece) => {
    navigate(`/write/${encodeURIComponent(piece.id)}`);
    onClose();
  };

  const openItem = (item: LauncherItem | undefined) => {
    if (!item) return;
    if (item.kind === "write-piece") {
      openWritePiece(item.piece);
    } else {
      openMode(item.mode);
    }
  };

  // SPR-09 M5 — the legacy additive "open in window" spawn, retained for the
  // window-eligible mode rows (Stats / Library / Documents) as a power affordance.
  // A window-eligible, built mode (contract-verified page) opens as a
  // transparent workspace window over the scene instead of navigating away.
  const openModeInWindow = (m: ModeEntry) => {
    const kind = windowKindForRoute(m.route);
    if (!m.built || !kind) return;
    openWindow(kind);
    onClose();
  };

  // SPR-04 M1/M3 — the DEFAULT product activation. Clicking a product
  // (Research / Read / Write / Speak) opens a `subaction` window over the scene
  // listing that workflow's sub-actions, rather than navigating full-page. This
  // is the windows-default keystone: the operator's first interaction with a
  // product is a floating window, not a page swap. A stable per-workflow id
  // means a second click on the same product FOCUSES the one window instead of
  // duplicating it. The window id is threaded into the payload so a sub-action
  // row click can close THIS window after it navigates to the chosen surface.
  const openProductWindow = (workflow: Workflow) => {
    const id = `win:subaction:${workflow}`;
    openWindow(
      "subaction",
      { workflow, __windowId: id },
      { id, title: WORKFLOWS[workflow as Exclude<Workflow, "shared">]?.label ?? "Sub-actions" },
    );
    onClose();
  };

  const onSearchKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveIndex((i) => Math.min(i + 1, Math.max(0, flatItems.length - 1)));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveIndex((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter") {
      openItem(flatItems[activeIndex]);
    }
  };

  // Active visual treatment matches the sibling CommandPalette (activeIdx
  // + highlight, not DOM roving focus). This gives power users the two-action
  // bar (More then arrow+enter, or type filter+enter) without tabbing.
  const isActive = (key: string) => flatItems[activeIndex]?.key === key;
  const modeRowButton = (m: ModeEntry) => {
    const destination = destinationForMode(m);
    const enabled = destination !== null;
    return (
      <button
        type="button"
        disabled={!enabled}
        onClick={() => openMode(m)}
        title={m.blurb}
        data-mode-id={m.id}
        className={
          "flex-1 text-left px-2 py-1.5 rounded flex items-center gap-2 " +
          (enabled
            ? "hover:bg-sun/20 dark:hover:bg-sun/10 text-ink dark:text-bright cursor-pointer"
            : "text-ink-mute dark:text-moonlight cursor-default opacity-70") +
          (isActive(`mode:${m.id}`) ? " bg-sun/10 dark:bg-sun/5" : "")
        }
      >
        <span className="flex-1 min-w-0 truncate text-[13px]">
          {m.label}
        </span>
        {!m.built && (
          <LemonTag colour="muted" className="shrink-0 text-[10px]">
            not yet
          </LemonTag>
        )}
      </button>
    );
  };

  return (
    <div
      className="fixed inset-0 z-50 bg-ink/40 flex items-start justify-center pt-20"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label="More"
    >
      <div
        className="w-[760px] max-w-[92vw] max-h-[80vh] bg-ice-0 dark:bg-charcoal-2 border border-rule dark:border-charcoal-1 rounded-lg shadow-2xl overflow-hidden flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="px-5 pt-4 pb-3 border-b border-rule dark:border-charcoal-1">
          <h2 className="font-serif text-lg text-ink dark:text-bright">
            More
          </h2>
          <p className="text-[12px] text-shadow-1 dark:text-moonlight mt-0.5">
            Deep modes for each workflow and the operator, trust, and settings
            surfaces. Greyed entries are not built yet and are shown honestly.
          </p>
          <input
            type="text"
            autoFocus
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setActiveIndex(0);
            }}
            onKeyDown={onSearchKeyDown}
            placeholder="Filter…"
            className="mt-3 w-full px-3 py-2 text-sm bg-ice-2 dark:bg-charcoal-1 border border-rule dark:border-charcoal-1 rounded text-ink dark:text-bright placeholder:text-ink-mute dark:placeholder:text-moonlight outline-none focus:border-sun"
          />
        </div>

        <div className="overflow-y-auto p-5 space-y-6">
          {/* SPR-12 M1 — the unified branded home, featured at the top of
              the launcher so it is one click away from anywhere (the rail
              logo is the other path). Not a MODE_TAXONOMY entry (Home is
              shell chrome, not a workflow mode — it has no modes/Home/
              index.tsx, so the completeness glob does not treat it as a
              mode). Always shown, never filtered, so the front door is
              never buried. */}
          <div>
            <div className="font-mono text-[11px] uppercase tracking-wider text-shadow-1 dark:text-moonlight mb-2">
              Home
            </div>
            <button
              type="button"
              data-testid="launcher-home"
              onClick={() => {
                navigate("/home");
                onClose();
              }}
              className="w-full text-left px-2 py-1.5 rounded flex items-center gap-2 hover:bg-sun/20 dark:hover:bg-sun/10 text-ink dark:text-bright cursor-pointer"
            >
              <span className="flex-1 min-w-0 truncate text-[13px]">
                Antiek home — what you can do, and where to start
              </span>
            </button>
          </div>

          {wfGroups.length === 0 && runModes.length === 0 && filteredWritePieces.length === 0 ? (
            <p className="text-sm italic text-shadow-1 dark:text-moonlight">
              No surfaces match “{query}”.
            </p>
          ) : (
            <>
              {filteredWritePieces.length > 0 && (
                <div>
                  <div className="font-mono text-[11px] uppercase tracking-wider text-shadow-1 dark:text-moonlight mb-2">
                    Recent writing
                  </div>
                  <ul className="space-y-0.5">
                    {filteredWritePieces.map((piece) => (
                      <li key={piece.id}>
                        <button
                          type="button"
                          onClick={() => openWritePiece(piece)}
                          title={`Open ${piece.title} in Write`}
                          className={
                            "w-full text-left px-2 py-1.5 rounded flex items-center gap-2 hover:bg-sun/20 dark:hover:bg-sun/10 text-ink dark:text-bright cursor-pointer" +
                            (isActive(`piece:${piece.id}`) ? " bg-sun/10 dark:bg-sun/5" : "")
                          }
                        >
                          <span aria-hidden="true" className="shrink-0 text-ink-mute dark:text-moonlight">
                            ✎
                          </span>
                          <span className="flex-1 min-w-0 truncate text-[13px]">
                            {piece.title}
                          </span>
                          <span className="shrink-0 text-[11px] text-shadow-1 dark:text-moonlight">
                            {piece.subtitle}
                          </span>
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {wfGroups.length > 0 && (
                <div>
                  <div className="font-mono text-[11px] uppercase tracking-wider text-shadow-1 dark:text-moonlight mb-2">
                    Open a product — or go deeper
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-8 gap-y-5">
                    {wfGroups.map((g) => (
                      <section key={g.workflow} aria-label={g.label}>
                        {/* SPR-04 M1/M3 — the PRODUCT header is the default
                            product activation: clicking it opens a sub-action
                            window over the scene (a window, not a navigation).
                            The deep-mode rows below it remain direct navigates
                            into specific surfaces. */}
                        <h3 className="mb-2">
                          <button
                            type="button"
                            data-product-window={g.workflow}
                            onClick={() => openProductWindow(g.workflow as Workflow)}
                            title={`Open ${g.label} — its sub-actions, in a window over the scene`}
                            // The product-activation (sub-action) window and the
                            // eligible-mode ⊞ "open in window" affordance share an
                            // accessible-name STEM ("Open … in a window"). Today the
                            // label sets are disjoint (workflow labels
                            // Research/Read/Write/Speak vs the only eligible-mode
                            // labels Substrate stats / Library — verified against
                            // workflowTaxonomy.ts), but the namespaces could converge
                            // if a future workflow label ever equalled an
                            // eligible-mode label, making every getByRole({name}) in
                            // the gates ambiguous. The interposed "workflow" keyword
                            // keeps the two name-spaces provably disjoint by
                            // construction (a product header is "Open <Workflow>
                            // workflow in a window"; an eligible mode is "Open <Mode>
                            // in a window" with no "workflow" token).
                            aria-label={`Open ${g.label} workflow in a window`}
                            className="w-full text-left font-mono text-[11px] uppercase tracking-wider text-shadow-1 dark:text-moonlight hover:text-ink dark:hover:text-bright cursor-pointer flex items-center gap-1.5"
                          >
                            <span className="flex-1 min-w-0 truncate">{g.label}</span>
                            <span aria-hidden="true" className="shrink-0 normal-case tracking-normal opacity-70">
                              ⊞
                            </span>
                          </button>
                        </h3>
                        <ul className="space-y-0.5">
                          {g.modes.map((m) => (
                            <li key={m.id} className="flex items-center gap-1">
                              {modeRowButton(m)}
                              {m.built && windowKindForRoute(m.route) && (
                                <button
                                  type="button"
                                  data-mode-window={m.id}
                                  onClick={() => openModeInWindow(m)}
                                  title={`Open ${m.label} in a floating window over the scene`}
                                  aria-label={`Open ${m.label} in a window`}
                                  className="shrink-0 px-1.5 py-1 rounded text-[12px] text-shadow-1 dark:text-moonlight hover:bg-sun/20 dark:hover:bg-sun/10 hover:text-ink dark:hover:text-bright"
                                >
                                  ⊞
                                </button>
                              )}
                            </li>
                          ))}
                        </ul>
                      </section>
                    ))}
                  </div>
                </div>
              )}

              {runModes.length > 0 && (
                <div>
                  <div className="font-mono text-[11px] uppercase tracking-wider text-shadow-1 dark:text-moonlight mb-2">
                    Run & settings
                  </div>
                  <ul className="space-y-0.5 grid grid-cols-1 sm:grid-cols-2 gap-x-8">
                    {runModes.map((m) => (
                      <li key={m.id} className="flex items-center gap-1">
                        {modeRowButton(m)}
                        {m.built && windowKindForRoute(m.route) && (
                          <button
                            type="button"
                            data-mode-window={m.id}
                            onClick={() => openModeInWindow(m)}
                            title={`Open ${m.label} in a floating window over the scene`}
                            aria-label={`Open ${m.label} in a window`}
                            className="shrink-0 px-1.5 py-1 rounded text-[12px] text-shadow-1 dark:text-moonlight hover:bg-sun/20 dark:hover:bg-sun/10 hover:text-ink dark:hover:text-bright"
                          >
                            ⊞
                          </button>
                        )}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </>
          )}
        </div>

        <footer className="px-5 py-2.5 border-t border-rule dark:border-charcoal-1 bg-ice-1 dark:bg-charcoal-2 text-[11px] font-mono text-shadow-1 dark:text-moonlight flex items-center justify-between">
          <span>Esc to close · ⌘K for deep search</span>
          <span>{MODE_TAXONOMY.length} surfaces</span>
        </footer>
      </div>
    </div>
  );
}

export default ProductsLauncher;
