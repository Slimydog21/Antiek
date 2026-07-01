import { Link } from "react-router-dom";

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
      { path: "/home", title: "Antiek home", description: "Front door to the four workflows" },
      { path: "/", title: "Research workstation", description: "Mode A — chat-first investigation surface" },
      { path: "/deep-research", title: "Deep Research Workspace", description: "Cascade monitor and steerable research sessions" },
      { path: "/wrestle", title: "Document wrestler", description: "Mode B — PDF reading + region selection" },
      { path: "/write", title: "Write home", description: "Blocks → outline → draft → editor loop" },
      { path: "/create", title: "Creation studio", description: "Mode C — lego-block writing" },
      { path: "/brainstorm", title: "Brainstorm station", description: "Mode E — watch-for-later + thought partner" },
      { path: "/library", title: "Library", description: "Read shelf over the servable corpus" },
      { path: "/library/browse", title: "Library browse", description: "Paginated catalog over every servable work" },
      { path: "/readings", title: "Your readings", description: "Saved reads and created deliverables" },
      { path: "/meta-readings", title: "All meta-docs", description: "Created deliverables only" },
      { path: "/read/meta-reading", title: "Meta-reading", description: "Research across your owned reading space" },
      { path: "/my-research", title: "My research", description: "One monitor over running + completed research" },
      { path: "/documents", title: "Documents", description: "Saved sources by quality tier" },
      { path: "/notebooks", title: "Notebooks", description: "Wedge 2 literate-analysis surface" },
      { path: "/sources", title: "Sources", description: "Acquisition adapters" },
      { path: "/speak", title: "Speak", description: "One door for interview projects + invited voices" },
      { path: "/biography", title: "Biography", description: "Template that composes Research, Write, and Speak" },
      { path: "/skill-rules", title: "Skill rules", description: "Cross-user discovered rules" },
    ],
  },
  {
    title: "Governance",
    routes: [
      { path: "/privacy", title: "Privacy dashboard", description: "Privacy budgets and deletion controls" },
      { path: "/trust", title: "Trust Center", description: "Published privacy, deletion, and training commitments" },
      { path: "/settings", title: "Settings", description: "Application settings and control links" },
      { path: "/coordination", title: "Coordination", description: "Gate ledger, roadmap, unified cost, escrow, and consent" },
      { path: "/coordination/cost-consent", title: "Cost & consent", description: "Unified spend, escrow, and consent status" },
      { path: "/federation", title: "Federation config", description: "Cross-substrate citation policy (§13.9 Phase 3)" },
      { path: "/cross-graph/citations", title: "Cross-graph citations", description: "Record citations and revenue share" },
      { path: "/loop-3", title: "Loop 3 checklist", description: "RL unlock criteria + env gate (§14.2)" },
      { path: "/operator", title: "Operator dashboard", description: "Composite operator-facing snapshot" },
      { path: "/operator/advertiser-campaigns", title: "Advertiser console", description: "Operator-managed lead-gen campaigns" },
      { path: "/operator/payouts/dashboard", title: "Payout dashboard", description: "Unified creator + publisher accrual view" },
      { path: "/me/payouts", title: "Creator payouts", description: "Your scoped creator payout ledger" },
      { path: "/marketplace", title: "Marketplace metrics", description: "Creator, publisher, and advertiser health snapshot" },
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
      { path: "/map", title: "Application map", description: "Index of every operator-facing surface" },
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
          <header className="space-y-2">
            <h1 className="text-2xl font-serif text-ink dark:text-bright">
              Application map
            </h1>
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
          </header>

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
