import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

/**
 * ProductsLauncher — the honest, full inventory of every surface,
 * grouped and demoted off the rail. Portfolio-shell IA: the rail shows
 * the five surfaces you act through; everything else lives here (and in
 * ⌘K). Opened by the rail's ⊞ button via the window event
 * `antiek:launcher:toggle`; closed by Escape or scrim click.
 *
 * Only destinations that exist as routes in App.tsx are listed — no
 * dead links. See `docs/ui_redesign_posthog/redesign_v1_portfolio.html`.
 */
type Product = { to: string; name: string; desc: string };
type Group = { label: string; surface?: boolean; items: Product[] };

const GROUPS: Group[] = [
  {
    label: "Workspaces — the five surfaces",
    surface: true,
    items: [
      { to: "/", name: "Research", desc: "Chat-first investigation · Loop 1" },
      { to: "/wrestle", name: "Wrestle", desc: "Single-document deep read" },
      { to: "/brainstorm", name: "Brainstorm ★", desc: "Talk to notes · slot Legos" },
      { to: "/create", name: "Create", desc: "Insight blocks → deliverables" },
      { to: "/interviews", name: "Interview", desc: "Voice + AI-led acquisition" },
    ],
  },
  {
    label: "Content & analysis",
    items: [
      { to: "/notebooks", name: "Notebooks", desc: "Literate substrate-backed docs" },
      { to: "/documents", name: "Documents", desc: "The source corpus" },
      { to: "/sources", name: "Sources", desc: "Acquisition + ingestion" },
      { to: "/investigations", name: "Investigations", desc: "All chase trees" },
      { to: "/map", name: "Graph map", desc: "Spatial view of the graph" },
      { to: "/outcomes", name: "Outcomes", desc: "Operator-graded results" },
      { to: "/stats", name: "Stats", desc: "Compounding metrics" },
    ],
  },
  {
    label: "Money & account",
    items: [
      { to: "/billing", name: "Billing", desc: "Pay-as-you-go token budget" },
      { to: "/pricing", name: "Pricing", desc: "Three-tier calculator" },
      { to: "/payouts", name: "Payouts", desc: "IP attribution audit" },
    ],
  },
  {
    label: "Trust & system",
    items: [
      { to: "/trust", name: "Trust center", desc: "Public privacy posture" },
      { to: "/privacy", name: "Privacy", desc: "Partition controls" },
      { to: "/operator", name: "Operator", desc: "Internal ops dashboard" },
      { to: "/skill-rules", name: "Skill rules", desc: "Harness rule editor" },
      { to: "/federation", name: "Federation", desc: "Cross-graph citations" },
      { to: "/cross-graph/citations", name: "Cross-graph", desc: "Citation graph" },
      { to: "/loop-3", name: "Loop 3", desc: "Self-iteration" },
    ],
  },
];

export function ProductsLauncher() {
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    const toggle = () => setOpen((o) => !o);
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("antiek:launcher:toggle", toggle);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("antiek:launcher:toggle", toggle);
      window.removeEventListener("keydown", onKey);
    };
  }, []);

  if (!open) return null;

  const goto = (to: string) => {
    navigate(to);
    setOpen(false);
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="All products"
      className="fixed inset-0 z-[120] flex items-center justify-center bg-ink/55 backdrop-blur-sm p-4"
      onClick={(e) => {
        if (e.target === e.currentTarget) setOpen(false);
      }}
    >
      <div className="w-[min(880px,94vw)] max-h-[84vh] overflow-auto bg-ice-1 dark:bg-charcoal-2 border-edge border-sun rounded-hog-lg shadow-z3 dark:shadow-z3-night p-6">
        <div className="flex items-start justify-between mb-1">
          <h2 className="text-[19px] font-bold text-ink dark:text-bright">All products</h2>
          <button
            type="button"
            aria-label="Close"
            onClick={() => setOpen(false)}
            className="text-ink-mute dark:text-moonlight hover:text-ink dark:hover:text-bright text-[20px] leading-none"
          >
            ✕
          </button>
        </div>
        <p className="text-[12.5px] text-ink-mute dark:text-moonlight mb-5">
          Five workspaces do the work. Everything else is here or in ⌘K — kept out of
          your way until you need it.
        </p>

        {GROUPS.map((g) => (
          <div key={g.label} className="mb-5">
            <div className="font-mono text-[10px] uppercase tracking-[0.16em] text-ink-mute dark:text-moonlight mb-2.5">
              {g.label}
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2.5">
              {g.items.map((p) => (
                <button
                  key={p.to + p.name}
                  type="button"
                  onClick={() => goto(p.to)}
                  className={
                    "flex items-start gap-2.5 text-left rounded-hog p-3 bg-ice-0 dark:bg-space-2 transition-transform hover:-translate-x-px hover:-translate-y-px " +
                    (g.surface
                      ? "border-edge border-sun shadow-z1 dark:shadow-z1-night"
                      : "border border-rule dark:border-charcoal-1 hover:border-sun hover:shadow-z1 dark:hover:shadow-z1-night")
                  }
                >
                  <span
                    className={
                      "w-[30px] h-[30px] shrink-0 grid place-items-center rounded-md " +
                      (g.surface ? "bg-sun text-ink" : "bg-ink text-sun dark:bg-void")
                    }
                    aria-hidden="true"
                  >
                    {g.surface ? "◆" : "·"}
                  </span>
                  <span className="min-w-0">
                    <span className="block font-bold text-[12.5px] text-ink dark:text-bright">
                      {p.name}
                    </span>
                    <span className="block text-[10.5px] leading-tight text-ink-mute dark:text-moonlight">
                      {p.desc}
                    </span>
                  </span>
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export default ProductsLauncher;
