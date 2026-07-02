import { Link } from "react-router-dom";

import { operatorRouteGroups } from "../../shell/operatorRoutes";

/**
 * Application map — operator-facing index of every route.
 *
 * The substrate has grown enough that the operator benefits from
 * a single page listing every surface with a one-line description.
 * Routes are grouped by the four product workflows first, then
 * governance and audit surfaces, so the operator can locate any
 * surface without leaving home.
 */

const GROUPS = operatorRouteGroups();

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
              sections group by intent: the four workflows for daily
              work, governance for policy, and audit for after-the-fact
              review.
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
