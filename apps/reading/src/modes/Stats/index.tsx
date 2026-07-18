import { useCallback, useEffect, useState } from "react";

import SessionBrandChrome from "../../brand/SessionBrandChrome";
import LemonCard from "../../components/lemon/LemonCard";
import { useInWindow } from "../../components/windows/windowHostContext";
import { apiFetch } from "../../lib/api";

/**
 * Substrate stats summary UI (master-spec §13.7 audit).
 *
 * Operator-facing "what does the substrate look like right now"
 * dashboard. Pulls GET /stats and renders counts across every
 * load-bearing table. Warnings (e.g. table missing on a partial
 * install) surface verbatim so the operator sees them.
 */

interface StatsResponse {
  counts: Record<string, number>;
  warnings: string[];
}

const TABLE_GROUPS: { title: string; tables: string[] }[] = [
  {
    title: "Research",
    tables: ["investigations", "documents", "chunks", "nodes", "edges"],
  },
  {
    title: "Notebooks",
    tables: ["notebooks", "notebook_blocks"],
  },
  {
    title: "Interviews",
    tables: ["interview_projects", "interviews"],
  },
  {
    title: "IP + payouts",
    tables: ["ip_holders", "payout_transfers"],
  },
  {
    title: "Outcomes + shared substrate",
    tables: ["outcomes", "skill_rules"],
  },
  {
    title: "Privacy + governance",
    tables: ["deletion_requests"],
  },
];

export default function Stats() {
  // SPR-09 window-adaptation contract: when hosted inside a WorkspaceWindow,
  // fill the window container (h-full, not h-screen) and drop the opaque
  // full-bleed bg so the glass body + scene shows through. Both edits are
  // gated on this flag, so the full-page route renders unchanged.
  const inWindow = useInWindow();
  const [data, setData] = useState<StatsResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await apiFetch("/stats");
      if (!resp.ok) {
        throw new Error(`GET /stats: HTTP ${resp.status}`);
      }
      setData(await resp.json());
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  return (
    <div className={`flex flex-col ${inWindow ? "h-full" : "h-screen"}`}>
      <main
        className={`flex-1 overflow-y-auto ${inWindow ? "bg-transparent" : "bg-ice-0 dark:bg-charcoal-2"}`}
      >
        <div className="max-w-4xl mx-auto px-8 py-10 space-y-6">
          <div className="flex items-start justify-between gap-3">
            <SessionBrandChrome
              testIdPrefix="stats-home"
              title="Substrate stats"
            >
              <p className="text-sm text-ink-soft dark:text-starlight leading-relaxed">
                Cardinality across every load-bearing table. Per
                master-spec §13.7: this is the &lsquo;what does the
                substrate look like right now&rsquo; surface before grading
                outcomes or running the Phase 8 gate.
              </p>
            </SessionBrandChrome>
            <button
              type="button"
              onClick={() => void reload()}
              className="mt-1 shrink-0 text-xs font-mono text-ink dark:text-bright border border-rule dark:border-charcoal-1 px-2 py-1 rounded hover:bg-ice-1 dark:bg-charcoal-2"
            >
              Refresh
            </button>
          </div>

          {error && (
            <p className="text-sm text-emperor border border-red-200 bg-red-50 px-3 py-2 rounded">
              {error}
            </p>
          )}

          {loading && (
            <p className="text-sm text-shadow-1 dark:text-moonlight italic">Loading…</p>
          )}

          {data && data.warnings.length > 0 && (
            <section className="border border-amber-200 bg-sun/10 rounded-md p-4 space-y-1">
              <p className="text-xs font-mono uppercase text-amber-900">
                Warnings
              </p>
              <ul className="text-xs text-amber-900 list-disc pl-5 space-y-0.5">
                {data.warnings.map((w, i) => (
                  <li key={i}>{w}</li>
                ))}
              </ul>
            </section>
          )}

          {data &&
            TABLE_GROUPS.map((group) => (
              // S10 acceptance: each Stats group/metric → LemonCard.
              <LemonCard
                key={group.title}
                elevation="z2"
                title={group.title}
              >
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 p-4 pt-2">
                  {group.tables.map((t) => (
                    <LemonCard
                      key={t}
                      elevation="z1"
                      colour="glacial"
                      className="px-3 py-2 text-center"
                    >
                      <p className="text-2xl font-serif text-ink dark:text-bright">
                        {(data.counts[t] ?? 0).toLocaleString()}
                      </p>
                      <p className="text-[10px] font-mono text-shadow-1 dark:text-moonlight uppercase">
                        {t.replace(/_/g, " ")}
                      </p>
                    </LemonCard>
                  ))}
                </div>
              </LemonCard>
            ))}
        </div>
      </main>
    </div>
  );
}
