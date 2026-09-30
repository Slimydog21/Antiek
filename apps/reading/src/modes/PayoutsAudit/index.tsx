import { useCallback, useEffect, useMemo, useState } from "react";

import { apiFetch } from "../../lib/api";
import { LemonButton } from "../../components/lemon";
import { ErrorBanner } from "../../components/lemon/ErrorBanner";

/**
 * Payout transfers audit (master-spec §13.7 + §9.10).
 *
 * Operator surface for the persistent transfer log emitted by the
 * Stripe Connect transfer initiator. Read-only by design — the
 * substrate is the writer; this surface displays.
 *
 * Status state machine: pending → transferred | skipped_escrow |
 * skipped_platform | failed. Filterable by status and recipient
 * Connect account id.
 */

interface PayoutRow {
  transfer_attempt_id: string;
  decision_id: string;
  stripe_transfer_id: string | null;
  recipient_account_id: string | null;
  amount_usd_cents: number;
  status: string;
  note: string | null;
  initiated_at: string | null;
}

const STATUS_FILTERS = [
  "all",
  "transferred",
  "skipped_escrow",
  "skipped_platform",
  "failed",
  "pending",
] as const;

export default function PayoutsAudit() {
  // null until the log answers, and again after a failed load: the totals
  // and the list are unknown then, never zero or empty.
  const [rows, setRows] = useState<PayoutRow[] | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  // Raw failure detail; shown only as a title, never as the sentence.
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<(typeof STATUS_FILTERS)[number]>("all");
  const [recipientFilter, setRecipientFilter] = useState<string>("");

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (filter !== "all") params.set("status", filter);
      if (recipientFilter.trim()) {
        params.set("recipient_account_id", recipientFilter.trim());
      }
      params.set("limit", "500");
      const resp = await apiFetch(`/payouts/transfers?${params.toString()}`);
      if (!resp.ok) {
        throw new Error(`GET /payouts/transfers: HTTP ${resp.status}`);
      }
      const data = await resp.json();
      setRows(data.transfers ?? []);
    } catch (e: unknown) {
      setRows(null);
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [filter, recipientFilter]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const totals = useMemo(() => {
    if (rows === null) return null;
    const acc: Record<string, { count: number; amount_cents: number }> = {};
    for (const r of rows) {
      const k = r.status;
      acc[k] = acc[k] ?? { count: 0, amount_cents: 0 };
      acc[k].count += 1;
      acc[k].amount_cents += r.amount_usd_cents;
    }
    return acc;
  }, [rows]);

  return (
    <div className="flex flex-col h-full">
      <main className="flex-1 overflow-y-auto bg-ice-0 dark:bg-charcoal-2">
        <div className="max-w-5xl mx-auto px-8 py-10 space-y-6">
          <header className="space-y-2">
            <h1 className="text-2xl font-serif text-ink dark:text-bright">
              Payout transfers audit
            </h1>
            <p className="text-sm text-ink-soft dark:text-starlight leading-relaxed">
              Persistent log of every Stripe Connect transfer the
              substrate initiated. Per master-spec §13.7: the
              operator can reconstruct the full transfer history from
              this surface without touching Stripe's dashboard.
              Pre-onboarded publisher transfers are held in escrow
              per §9.10; platform residual is recorded but no
              transfer fires.
            </p>
          </header>

          <section className="border border-rule dark:border-charcoal-1 rounded-md p-4 space-y-3">
            <div className="flex flex-wrap items-center gap-2">
              {STATUS_FILTERS.map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => setFilter(s)}
                  className={`px-2.5 py-1 rounded-md text-xs font-mono transition-colors ${
                    filter === s
                      ? "bg-ink text-white"
                      : "bg-ice-3 dark:bg-charcoal-1 text-ink dark:text-bright hover:bg-ice-4 dark:bg-charcoal-1"
                  }`}
                >
                  {s.replace(/_/g, " ")}
                </button>
              ))}
            </div>
            <input
              type="text"
              value={recipientFilter}
              onChange={(e) => setRecipientFilter(e.target.value)}
              placeholder="filter by recipient_account_id (Stripe Connect acct_...)"
              className="w-full text-xs font-mono text-ink dark:text-bright border border-rule dark:border-charcoal-1 rounded p-2"
            />
          </section>

          <section className="grid grid-cols-2 gap-3 sm:grid-cols-5">
            {STATUS_FILTERS.filter((s) => s !== "all").map((s) => (
              <div
                key={s}
                className="border border-rule dark:border-charcoal-1 rounded-md px-3 py-2"
              >
                <p className="text-base font-serif text-ink dark:text-bright">
                  {totals ? (totals[s]?.count ?? 0) : loading ? "…" : "—"}
                </p>
                <p className="text-xxs font-mono text-shadow-1 dark:text-moonlight uppercase">
                  {s.replace(/_/g, " ")}
                </p>
                {totals && (
                  <p className="text-xxs font-mono text-shadow-1 dark:text-moonlight">
                    ${((totals[s]?.amount_cents ?? 0) / 100).toFixed(2)}
                  </p>
                )}
              </div>
            ))}
          </section>

          {error && (
            <ErrorBanner className="flex flex-wrap items-center justify-between gap-3">
              <span title={error}>Transfers didn't load.</span>
              <LemonButton variant="secondary" size="sm" type="button" onClick={() => void reload()}>
                Try again
              </LemonButton>
            </ErrorBanner>
          )}

          {loading && (
            <p className="text-sm text-shadow-1 dark:text-moonlight italic">Loading…</p>
          )}

          {!loading && rows !== null && rows.length === 0 && (
            <p className="text-sm text-shadow-1 dark:text-moonlight italic">
              No transfers match this filter.
            </p>
          )}

          {rows !== null && rows.length > 0 && (
            <section className="border border-rule dark:border-charcoal-1 rounded-md divide-y divide-rule dark:divide-charcoal-1">
              {rows.map((r) => (
                <article
                  key={r.transfer_attempt_id}
                  className="px-4 py-3 grid grid-cols-12 gap-3 items-center"
                >
                  <span
                    className={`col-span-2 text-xxs uppercase tracking-wider font-mono px-2 py-0.5 rounded text-center ${
                      r.status === "transferred"
                        ? "bg-success/10 text-success"
                        : r.status === "failed"
                          ? "bg-danger/10 text-danger"
                          : "bg-ice-3 dark:bg-charcoal-1 text-ink dark:text-bright"
                    }`}
                  >
                    {r.status.replace(/_/g, " ")}
                  </span>
                  <div className="col-span-7 min-w-0">
                    <p className="text-sm font-mono text-ink dark:text-bright truncate">
                      {r.recipient_account_id ?? "—"}
                    </p>
                    <p className="text-xs font-mono text-shadow-1 dark:text-moonlight truncate">
                      decision={r.decision_id}
                      {r.stripe_transfer_id ? ` · stripe=${r.stripe_transfer_id}` : ""}
                    </p>
                    {r.note && (
                      <p className="text-xs text-shadow-1 dark:text-moonlight italic truncate">
                        {r.note}
                      </p>
                    )}
                  </div>
                  <div className="col-span-3 text-right">
                    <p className="text-sm font-mono text-ink dark:text-bright">
                      ${(r.amount_usd_cents / 100).toFixed(2)}
                    </p>
                    <p className="text-xxs font-mono text-shadow-1 dark:text-moonlight">
                      {r.initiated_at ?? "—"}
                    </p>
                  </div>
                </article>
              ))}
            </section>
          )}
        </div>
      </main>
    </div>
  );
}
