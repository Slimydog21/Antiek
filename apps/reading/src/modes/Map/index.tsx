import { Link } from "react-router-dom";

import SessionBrandChrome from "../../brand/SessionBrandChrome";

/**
 * Application map — operator-facing index of every route.
 *
 * The substrate has grown enough that the operator benefits from
 * a single page listing every surface with a one-line description.
 * Routes are grouped by category (workstation / governance / audit /
 * config / Storybook) so the operator can locate any surface
 * without leaving home.
 */

interface RouteEntry {
  path: string;
  title: string;
  description: string;
}

const GROUPS: { title: string; routes: RouteEntry[] }[] = [
  {
    title: "Workstation",
    routes: [
      { path: "/", title: "Research workstation", description: "Mode A — chat-first investigation surface" },
      { path: "/wrestle", title: "Document wrestler", description: "Mode B — PDF reading + region selection" },
      { path: "/create", title: "Creation studio", description: "Mode C — lego-block writing" },
      { path: "/brainstorm", title: "Brainstorm station", description: "Mode E — watch-for-later + thought partner" },
      { path: "/investigations", title: "Investigations index", description: "List + create investigations" },
      { path: "/documents", title: "Documents", description: "Substrate-attached sources by tier" },
      { path: "/notebooks", title: "Notebooks", description: "Wedge 2 literate-analysis surface" },
      { path: "/sources", title: "Sources", description: "Acquisition adapters" },
      { path: "/interviews", title: "Interviews", description: "Loop 4 informant projects + invites" },
      { path: "/skill-rules", title: "Skill rules", description: "Cross-user discovered rules" },
    ],
  },
  {
    title: "Governance",
    routes: [
      { path: "/privacy", title: "Privacy dashboard", description: "ε budgets + delete-all (§13.3)" },
      { path: "/trust", title: "Trust Center", description: "Substrate-wide DP + control posture" },
      { path: "/federation", title: "Federation config", description: "Cross-substrate citation policy (§13.9 Phase 3)" },
      { path: "/loop-3", title: "Loop 3 checklist", description: "RL unlock criteria + env gate (§14.2)" },
      { path: "/operator", title: "Operator dashboard", description: "Composite operator-facing snapshot" },
    ],
  },
  {
    title: "Audit + analytics",
    routes: [
      { path: "/stats", title: "Substrate stats", description: "Per-table cardinality dashboard" },
      { path: "/outcomes", title: "Outcomes audit", description: "Cross-investigation grading history" },
      { path: "/payouts", title: "Payouts audit", description: "Stripe Connect transfer log" },
      { path: "/billing", title: "Billing", description: "Free-tier usage + margin breakdown" },
    ],
  },
  {
    title: "Pricing + replay",
    routes: [
      { path: "/pricing", title: "Pricing", description: "OpenRouter-style pay-as-you-go calculator" },
    ],
  },
];

const KEYBOARD_HINTS: { label: string; key: string }[] = [
  { label: "Command palette", key: "⌘K" },
  { label: "AI sidecar", key: "⌘J" },
];

export default function Map() {
  return (
    <div className="flex flex-col h-screen">
      <main className="flex-1 overflow-y-auto bg-ice-0 dark:bg-charcoal-2">
        <div className="max-w-4xl mx-auto px-8 py-10 space-y-8">
          <SessionBrandChrome
            testIdPrefix="map-home"
            title="Application map"
          >
            <p className="text-sm text-ink-soft dark:text-starlight leading-relaxed">
              Every operator-facing surface in the substrate.
              Routes route through the same auth middleware; the
              left-side categories group by intent (workstation
              for daily work, governance for policy, audit for
              after-the-fact review).
            </p>
            <div className="flex flex-wrap gap-3 pt-1">
              {KEYBOARD_HINTS.map((h) => (
                <span
                  key={h.label}
                  className="text-[11px] font-mono text-shadow-1 dark:text-moonlight bg-ice-3 dark:bg-charcoal-1 px-2 py-1 rounded"
                >
                  {h.label}: <kbd className="font-mono">{h.key}</kbd>
                </span>
              ))}
            </div>
          </SessionBrandChrome>

          {GROUPS.map((group) => (
            <section
              key={group.title}
              className="space-y-3"
            >
              <h2 className="text-base font-serif text-ink dark:text-bright border-b border-rule dark:border-charcoal-1 pb-1">
                {group.title}
              </h2>
              <ul className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                {group.routes.map((r) => (
                  <li key={r.path}>
                    <Link
                      to={r.path}
                      className="block border border-rule dark:border-charcoal-1 rounded-md px-3 py-2 hover:bg-ice-1 dark:bg-charcoal-2 transition-colors"
                    >
                      <p className="text-sm font-serif text-ink dark:text-bright">
                        {r.title}
                      </p>
                      <p className="text-[11px] font-mono text-shadow-1 dark:text-moonlight truncate">
                        {r.path}
                      </p>
                      <p className="text-xs text-ink-soft dark:text-starlight mt-1">
                        {r.description}
                      </p>
                    </Link>
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      </main>
    </div>
  );
}
