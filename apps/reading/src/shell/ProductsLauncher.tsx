import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { LemonTag } from "../components/lemon/LemonTag";
import {
  MODE_TAXONOMY,
  WORKFLOWS,
  WORKFLOW_ORDER,
  type ModeEntry,
  type Workflow,
} from "./workflowTaxonomy";

/**
 * ProductsLauncher (SPR-04 zone-1 ⊞) — the honest full inventory of
 * EVERY mode, grouped by workflow + a shared/operator section, with each
 * mode's build status shown truthfully.
 *
 * This is the pressure-release valve that lets the rail stay at four
 * entries: deep modes (the ~39-mode reality) live here + in ⌘K, never on
 * the rail. It is also the honesty surface — an unbuilt mode is shown
 * dimmed with a "not yet" tag rather than hidden (hiding it would lie
 * about the product's shape) and rather than linked (linking it would
 * present absent capability as present).
 *
 * Data-driven from MODE_TAXONOMY: add/remove/reclassify a mode and the
 * launcher follows. No hand-maintained list.
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

  useEffect(() => {
    if (!open) {
      setQuery("");
      return;
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  // Group modes: the four workflows in order, then shared.
  const groups = useMemo(() => {
    const q = query.trim().toLowerCase();
    const match = (m: ModeEntry) =>
      !q ||
      m.label.toLowerCase().includes(q) ||
      m.blurb.toLowerCase().includes(q) ||
      m.id.toLowerCase().includes(q);

    const order: Workflow[] = [...WORKFLOW_ORDER, "shared"];
    return order
      .map((wf) => ({
        workflow: wf,
        label: wf === "shared" ? "Shared · operator" : WORKFLOWS[wf].label,
        modes: MODE_TAXONOMY.filter((m) => m.workflow === wf && match(m)),
      }))
      .filter((g) => g.modes.length > 0);
  }, [query]);

  if (!open) return null;

  /** Built modes navigate; param routes resolve to their index where one
   *  exists, else the workflow default. Unbuilt modes never navigate. */
  const openMode = (m: ModeEntry) => {
    if (!m.built || !m.route) return;
    // A bare route (no :param) navigates directly; a param route falls
    // back to the workflow's default landing so we never push a route
    // with an unresolved :id.
    const target = m.route.includes(":")
      ? m.workflow === "shared"
        ? "/operator"
        : WORKFLOWS[m.workflow].defaultRoute
      : m.route;
    navigate(target);
    onClose();
  };

  return (
    <div
      className="fixed inset-0 z-50 bg-ink/40 flex items-start justify-center pt-20"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label="All products"
    >
      <div
        className="w-[760px] max-w-[92vw] max-h-[80vh] bg-ice-0 dark:bg-charcoal-2 border border-rule dark:border-charcoal-1 rounded-lg shadow-2xl overflow-hidden flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="px-5 pt-4 pb-3 border-b border-rule dark:border-charcoal-1">
          <h2 className="font-serif text-lg text-ink dark:text-bright">
            All products
          </h2>
          <p className="text-[12px] text-shadow-1 dark:text-moonlight mt-0.5">
            Every surface, grouped by workflow. Greyed entries aren't built
            yet — shown honestly, not hidden.
          </p>
          <input
            type="text"
            autoFocus
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Filter products…"
            className="mt-3 w-full px-3 py-2 text-sm bg-ice-2 dark:bg-charcoal-1 border border-rule dark:border-charcoal-1 rounded text-ink dark:text-bright placeholder:text-ink-mute dark:placeholder:text-moonlight outline-none focus:border-sun"
          />
        </div>

        <div className="overflow-y-auto p-5 grid grid-cols-1 sm:grid-cols-2 gap-x-8 gap-y-5">
          {groups.length === 0 ? (
            <p className="text-sm italic text-shadow-1 dark:text-moonlight col-span-full">
              No products match “{query}”.
            </p>
          ) : (
            groups.map((g) => (
              <section key={g.workflow} aria-label={g.label}>
                <h3 className="font-mono text-[11px] uppercase tracking-wider text-shadow-1 dark:text-moonlight mb-2">
                  {g.label}
                </h3>
                <ul className="space-y-0.5">
                  {g.modes.map((m) => (
                    <li key={m.id}>
                      <button
                        type="button"
                        disabled={!m.built}
                        onClick={() => openMode(m)}
                        title={m.blurb}
                        className={
                          "w-full text-left px-2 py-1.5 rounded flex items-center gap-2 " +
                          (m.built
                            ? "hover:bg-sun/20 dark:hover:bg-sun/10 text-ink dark:text-bright cursor-pointer"
                            : "text-ink-mute dark:text-moonlight cursor-default opacity-70")
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
                    </li>
                  ))}
                </ul>
              </section>
            ))
          )}
        </div>

        <footer className="px-5 py-2.5 border-t border-rule dark:border-charcoal-1 bg-ice-1 dark:bg-charcoal-2 text-[11px] font-mono text-shadow-1 dark:text-moonlight flex items-center justify-between">
          <span>Esc to close · ⌘K for deep search</span>
          <span>{MODE_TAXONOMY.length} products</span>
        </footer>
      </div>
    </div>
  );
}

export default ProductsLauncher;
