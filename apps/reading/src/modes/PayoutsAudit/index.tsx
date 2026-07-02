import { useCallback, useEffect, useMemo, useState } from "react";

import { apiFetch } from "../../lib/api";

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

function record(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function nonEmptyString(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

function nullableString(value: unknown): string | null {
  return value == null ? null : nonEmptyString(value);
}

function nonNegativeFiniteNumber(value: unknown): number | null {
  const parsed =
    typeof value === "number"
      ? value
      : typeof value === "string" && value.trim() !== ""
        ? Number(value)
        : Number.NaN;
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : null;
}

function safeCents(value: unknown): number {
  return Math.floor(nonNegativeFiniteNumber(value) ?? 0);
}

function centsToUsd(value: unknown): string {
  const cents = safeCents(value);
  return `$${(cents / 100).toFixed(2)}`;
}

function safePayoutRow(value: unknown): PayoutRow | null {
  const row = record(value);
  const transferAttemptId = nonEmptyString(row?.transfer_attempt_id);
  const decisionId = nonEmptyString(row?.decision_id);
  if (!row || !transferAttemptId || !decisionId) return null;
  return {
    transfer_attempt_id: transferAttemptId,
    decision_id: decisionId,
    stripe_transfer_id: nullableString(row.stripe_transfer_id),
    recipient_account_id: nullableString(row.recipient_account_id),
    amount_usd_cents: safeCents(row.amount_usd_cents),
    status: nonEmptyString(row.status) ?? "pending",
    note: nullableString(row.note),
    initiated_at: nullableString(row.initiated_at),
  };
}

function safePayoutRows(value: unknown): PayoutRow[] {
  const body = record(value);
  const transfers = Array.isArray(body?.transfers) ? body.transfers : [];
  return transfers.flatMap((item) => {
    const row = safePayoutRow(item);
    return row ? [row] : [];
  });
}

export default function PayoutsAudit() {
  const [rows, setRows] = useState<PayoutRow[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
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
      setRows(safePayoutRows(await resp.json()));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [filter, recipientFilter]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const totals = useMemo(() => {
    const acc: Record<string, { count: number; amount_cents: number }> = {};
    for (const r of rows) {
      const k = r.status;
      acc[k] = acc[k] ?? { count: 0, amount_cents: 0 };
      acc[k].count += 1;
      acc[k].amount_cents += safeCents(r.amount_usd_cents);
    }
    return acc;
  }, [rows]);

  return (
    <div className="flex flex-col h-screen">
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
                  {totals[s]?.count ?? 0}
                </p>
                <p className="text-[10px] font-mono text-shadow-1 dark:text-moonlight uppercase">
                  {s.replace(/_/g, " ")}
                </p>
                <p className="text-[10px] font-mono text-shadow-1 dark:text-moonlight">
                  {centsToUsd(totals[s]?.amount_cents)}
                </p>
              </div>
            ))}
          </section>

          {error && (
            <p className="text-sm text-emperor border border-red-200 bg-red-50 px-3 py-2 rounded">
              {error}
            </p>
          )}

          {loading && (
            <p className="text-sm text-shadow-1 dark:text-moonlight italic">Loading…</p>
          )}

          {!loading && rows.length === 0 && !error && (
            <p className="text-sm text-shadow-1 dark:text-moonlight italic">
              No transfers match this filter.
            </p>
          )}

          {rows.length > 0 && (
            <section className="border border-rule dark:border-charcoal-1 rounded-md divide-y divide-rule dark:divide-charcoal-1">
              {rows.map((r) => (
                <article
                  key={r.transfer_attempt_id}
                  className="px-4 py-3 grid grid-cols-12 gap-3 items-center"
                >
                  <span
                    className={`col-span-2 text-[10px] uppercase tracking-wider font-mono px-2 py-0.5 rounded text-center ${
                      r.status === "transferred"
                        ? "bg-emerald-100 text-emerald-700"
                        : r.status === "failed"
                          ? "bg-red-50 text-emperor"
                          : "bg-ice-3 dark:bg-charcoal-1 text-ink dark:text-bright"
                    }`}
                  >
                    {r.status.replace(/_/g, " ")}
                  </span>
                  <div className="col-span-7 min-w-0">
                    <p className="text-sm font-mono text-ink dark:text-bright truncate">
                      {r.recipient_account_id ?? "—"}
                    </p>
                    <p className="text-[11px] font-mono text-shadow-1 dark:text-moonlight truncate">
                      decision={r.decision_id}
                      {r.stripe_transfer_id ? ` · stripe=${r.stripe_transfer_id}` : ""}
                    </p>
                    {r.note && (
                      <p className="text-[11px] text-shadow-1 dark:text-moonlight italic truncate">
                        {r.note}
                      </p>
                    )}
                  </div>
                  <div className="col-span-3 text-right">
                    <p className="text-sm font-mono text-ink dark:text-bright">
                      {centsToUsd(r.amount_usd_cents)}
                    </p>
                    <p className="text-[10px] font-mono text-shadow-1 dark:text-moonlight">
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
