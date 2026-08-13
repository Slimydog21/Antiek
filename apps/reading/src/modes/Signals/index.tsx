import { useCallback, useEffect, useMemo, useState } from "react";

import type { SignalActionView, SignalInventoryResponse } from "../../api/ownYourMind";
import { getSignalInventory } from "../../api/ownYourMind";
import { useServedImpression } from "../../lib/servedImpression";
import { LemonTable } from "../../components/lemon/LemonTable";
import { LemonTag } from "../../components/lemon/LemonTag";

/**
 * Signals — the signal-inventory publication surface (Own Your Mind P0, L15).
 *
 * Route: /signals. Fetches GET /ops/signal-inventory — a static, versioned
 * document generated mechanically from the event schema (ActionType enum +
 * typed payloads in substrate/schemas/events.py) — and renders it as a
 * filterable table:
 *
 *   domain | ActionType | payload class | emitted-by note (when present)
 *
 * The filter is a plain client-side match over every field. Read-only: this
 * page publishes what the substrate collects; it records nothing itself.
 */

function matches(row: SignalActionView, q: string): boolean {
  if (!q) return true;
  const haystack = [
    row.action_type,
    row.domain,
    row.payload_class ?? "",
    row.emitted_by ?? "",
  ]
    .join(" ")
    .toLowerCase();
  return haystack.includes(q);
}

export function Signals() {
  const [data, setData]
  // P0 §5: audit-only served-impression record.
  useServedImpression({ surface: "signals", itemKind: "surface", itemId: "/signals" }); = useState<SignalInventoryResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState<string>("");

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await getSignalInventory());
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  const rows = data?.signals ?? [];

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return rows.filter((row) => matches(row, q));
  }, [rows, query]);

  const domains = useMemo(
    () => [...new Set(rows.map((r) => r.domain).filter(Boolean))].sort(),
    [rows],
  );

  // "Emitted by" is a reserved column: rendered only when the backend
  // payload carries emitter notes (the component map is not in the P0
  // schema introspection). Honest — never a column of fabricated "—".
  const anyEmitter = rows.some((r) => Boolean(r.emitted_by));

  return (
    <div className="flex flex-col h-screen">
      <main className="flex-1 overflow-y-auto bg-ice-0 dark:bg-charcoal-2">
        <div className="max-w-5xl mx-auto px-8 py-10 space-y-6">
          <header className="space-y-2">
            <h1 className="text-2xl font-serif text-ink dark:text-bright">
              Signal inventory
            </h1>
            <p className="text-sm text-ink-soft dark:text-starlight leading-relaxed">
              Every signal the substrate can collect — the ActionType enum
              from substrate/schemas/events.py with its typed payload class
              and domain. Generated from the schema itself at request time,
              never a hand-maintained duplicate.
            </p>
            <div className="flex items-center gap-2 flex-wrap text-[10px] font-mono text-ink-mute dark:text-moonlight">
              {data?.schema_version !== undefined && (
                <span>schema v{data.schema_version}</span>
              )}
              {data?.generated_at && (
                <span>generated {new Date(data.generated_at).toLocaleString()}</span>
              )}
              <span>{data?.count ?? rows.length} action types</span>
              <span>{domains.length} domains</span>
            </div>
          </header>

          {error && (
            <p className="text-sm text-emperor border border-red-200 bg-red-50 px-3 py-2 rounded">
              {error}
            </p>
          )}

          {loading && (
            <p className="text-sm text-shadow-1 dark:text-moonlight italic">Loading…</p>
          )}

          {!loading && !error && rows.length === 0 && (
            <p className="text-sm text-shadow-1 dark:text-moonlight italic">
              The signal-inventory endpoint returned no signals.
            </p>
          )}

          {rows.length > 0 && (
            <section className="space-y-3">
              <div className="flex items-center gap-2 flex-wrap">
                <input
                  type="text"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="filter by action type, domain, payload class…"
                  className="flex-1 min-w-[260px] text-xs font-mono text-ink dark:text-bright border border-rule dark:border-charcoal-1 rounded p-2 bg-ice-0 dark:bg-charcoal-2 placeholder:text-ink-mute dark:placeholder:text-moonlight"
                />
                <LemonTag colour="muted">
                  {filtered.length} / {rows.length}
                </LemonTag>
              </div>

              <LemonTable<SignalActionView>
                rows={filtered}
                columns={[
                  {
                    key: "domain",
                    header: "Domain",
                    render: (r) => (
                      <span className="font-mono text-[11px] uppercase text-shadow-1 dark:text-moonlight">
                        {r.domain}
                      </span>
                    ),
                    width: "14%",
                  },
                  {
                    key: "action_type",
                    header: "ActionType",
                    render: (r) => (
                      <span className="font-mono text-xs text-ink dark:text-bright">
                        {r.action_type}
                      </span>
                    ),
                  },
                  {
                    key: "payload_class",
                    header: "Payload class",
                    render: (r) =>
                      r.payload_class ? (
                        <span className="font-mono text-[11px] text-ink-soft dark:text-starlight">
                          {r.payload_class}
                          {!r.typed && (
                            <span className="ml-1 text-ink-mute dark:text-moonlight italic">
                              (untyped)
                            </span>
                          )}
                        </span>
                      ) : (
                        <span className="text-ink-mute dark:text-moonlight italic">—</span>
                      ),
                    width: "26%",
                  },
                  ...(anyEmitter
                    ? [
                        {
                          key: "emitted_by",
                          header: "Emitted by",
                          render: (r: SignalActionView) =>
                            r.emitted_by ? (
                              <span className="font-mono text-[11px] text-ink-soft dark:text-starlight">
                                {r.emitted_by}
                              </span>
                            ) : (
                              <span className="text-ink-mute dark:text-moonlight italic">—</span>
                            ),
                          width: "20%",
                        },
                      ]
                    : []),
                ]}
                rowKey={(r) => r.action_type}
                emptyState={
                  query
                    ? `No action types match “${query}”.`
                    : "No action types."
                }
                dense
              />
            </section>
          )}
        </div>
      </main>
    </div>
  );
}

export default Signals;
