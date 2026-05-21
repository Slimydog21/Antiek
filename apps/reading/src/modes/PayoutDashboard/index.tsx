import { useCallback, useEffect, useState } from "react";

import { apiFetch } from "../../lib/api";
import HeaderBar from "../shared/HeaderBar";

/**
 * PayoutDashboard — Sprint 25+ unified creator + publisher
 * accrual view (master-spec §13.9 + §9.10 convergence).
 *
 * Operator-facing surface that renders BOTH economic loops in one
 * place, with mixed-attribution audit hooks. Distinct from
 * PayoutsAudit (full transfer log) and CreatorPayouts (per-user
 * self-service view): this surface is the operator's full
 * marketplace cash-flow picture.
 *
 * Backend contract: GET /operator/payouts/dashboard. The endpoint
 * supplies creator and publisher lines aggregated for the current
 * month + lifetime totals; this UI sums and visualises them.
 */

interface RevenueLine {
  recipient_kind: "creator" | "publisher";
  recipient_ref: string;
  recipient_name: string;
  current_month_cents: number;
  lifetime_cents: number;
  status: string;
  kyc_complete: boolean;
}

interface PayoutDashboardData {
  current_month_label: string;
  lines: RevenueLine[];
  platform_residual_month_cents: number;
  unallocated_rounding_month_cents: number;
}

const USD = (cents: number) =>
  `$${(cents / 100).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;

const KIND_COLOR: Record<string, string> = {
  creator: "bg-emerald-50 text-emerald-700 border-emerald-200",
  publisher: "bg-blue-50 text-blue-700 border-blue-200",
};

const STATUS_BADGE: Record<string, string> = {
  active: "bg-emerald-100 text-emerald-700",
  pending_kyc: "bg-sun/20 text-sun-deep dark:text-sun",
  escrow_only: "bg-ice-3 dark:bg-charcoal-1 text-ink-soft dark:text-starlight",
  forfeited: "bg-emperor/20 text-emperor",
};

export default function PayoutDashboard() {
  const [data, setData] = useState<PayoutDashboardData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [kindFilter, setKindFilter] = useState<"all" | "creator" | "publisher">("all");

  const reload = useCallback(async () => {
    try {
      const resp = await apiFetch("/operator/payouts/dashboard");
      if (!resp.ok) {
        if (resp.status === 404) {
          setData(null);
          return;
        }
        throw new Error(`HTTP ${resp.status}`);
      }
      setData(await resp.json());
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  const lines = data?.lines ?? [];
  const filtered =
    kindFilter === "all"
      ? lines
      : lines.filter((l) => l.recipient_kind === kindFilter);

  const monthTotals = lines.reduce(
    (acc, l) => ({
      creator_cents:
        acc.creator_cents + (l.recipient_kind === "creator" ? l.current_month_cents : 0),
      publisher_cents:
        acc.publisher_cents + (l.recipient_kind === "publisher" ? l.current_month_cents : 0),
    }),
    { creator_cents: 0, publisher_cents: 0 },
  );

  return (
    <div className="flex flex-col h-screen">
      <HeaderBar />
      <main className="flex-1 overflow-y-auto bg-ice-0 dark:bg-charcoal-2">
        <div className="max-w-5xl mx-auto px-8 py-10 space-y-8">
          <header className="space-y-3">
            <h1 className="text-3xl font-serif text-ink dark:text-bright">
              Payout dashboard
            </h1>
            <p className="text-base text-ink dark:text-bright leading-relaxed">
              The operator's unified view of every dollar Antiek owes
              this month — to creators (§13.9 user-as-IP-holder
              share) and to publishers (§9.10 opted-in escrow share).
              Mixed attribution splits stay proportional;
              unallocated-rounding cents land in the platform
              residual ledger and never double-pay.
            </p>
          </header>

          {error && (
            <p className="text-sm text-emperor border border-red-200 bg-red-50 px-3 py-2 rounded">
              {error}
            </p>
          )}

          {data ? (
            <>
              <section className="grid grid-cols-4 gap-4">
                <Card label="Current month" value={data.current_month_label} mono />
                <Card label="Creator share (month)" value={USD(monthTotals.creator_cents)} />
                <Card label="Publisher share (month)" value={USD(monthTotals.publisher_cents)} />
                <Card label="Platform residual (month)" value={USD(data.platform_residual_month_cents)} />
              </section>

              {data.unallocated_rounding_month_cents > 0 && (
                <div className="text-xs font-mono text-shadow-1 dark:text-moonlight border-l-2 border-rule dark:border-charcoal-1 pl-3 py-1">
                  Unallocated rounding this month:{" "}
                  {USD(data.unallocated_rounding_month_cents)} — these
                  cents fell off mixed-attribution splits and accrued
                  to the platform residual.
                </div>
              )}

              <section className="space-y-3">
                <div className="flex items-center justify-between">
                  <h2 className="text-xl font-serif text-ink dark:text-bright">
                    Per-recipient lines
                  </h2>
                  <div className="flex gap-1">
                    {(["all", "creator", "publisher"] as const).map((k) => (
                      <button
                        key={k}
                        onClick={() => setKindFilter(k)}
                        className={`text-[11px] font-mono uppercase tracking-wider px-2 py-1 rounded border ${
                          kindFilter === k
                            ? "bg-ink text-white border-ink dark:border-bright"
                            : "bg-ice-0 dark:bg-charcoal-2 text-ink-soft dark:text-starlight border-rule dark:border-charcoal-1 hover:bg-ice-1 dark:bg-charcoal-2"
                        }`}
                      >
                        {k}
                      </button>
                    ))}
                  </div>
                </div>

                {filtered.length === 0 ? (
                  <p className="text-sm text-ink-soft dark:text-starlight italic">
                    No payout lines this month. When the rev-share
                    pipeline routes its first creator or publisher
                    share, a line appears here.
                  </p>
                ) : (
                  <ul className="divide-y divide-rule dark:divide-charcoal-1 border border-rule dark:border-charcoal-1 rounded">
                    {filtered.map((l) => (
                      <li
                        key={`${l.recipient_kind}-${l.recipient_ref}`}
                        className="p-3 flex items-center justify-between"
                      >
                        <div className="flex items-center gap-3">
                          <span
                            className={`text-[10px] font-mono uppercase tracking-wider px-2 py-0.5 rounded border ${
                              KIND_COLOR[l.recipient_kind] ??
                              "bg-ice-3 dark:bg-charcoal-1 text-ink-soft dark:text-starlight border-rule dark:border-charcoal-1"
                            }`}
                          >
                            {l.recipient_kind}
                          </span>
                          <div className="flex flex-col">
                            <span className="text-sm text-ink dark:text-bright">
                              {l.recipient_name}
                            </span>
                            <span className="text-[11px] font-mono text-shadow-1 dark:text-moonlight">
                              {l.recipient_ref}
                              {!l.kyc_complete && " · KYC incomplete"}
                            </span>
                          </div>
                        </div>
                        <div className="flex items-center gap-4">
                          <div className="flex flex-col items-end">
                            <span className="text-sm font-mono text-ink dark:text-bright">
                              {USD(l.current_month_cents)}
                            </span>
                            <span className="text-[10px] font-mono text-shadow-1 dark:text-moonlight">
                              this month · lifetime {USD(l.lifetime_cents)}
                            </span>
                          </div>
                          <span
                            className={`text-[10px] font-mono px-2 py-0.5 rounded ${
                              STATUS_BADGE[l.status] ?? "bg-ice-3 dark:bg-charcoal-1 text-ink-soft dark:text-starlight"
                            }`}
                          >
                            {l.status}
                          </span>
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </section>
            </>
          ) : (
            <p className="text-sm text-ink-soft dark:text-starlight italic">
              No data available. The backend endpoint at{" "}
              <code className="px-1 bg-ice-3 dark:bg-charcoal-1 rounded">
                GET /operator/payouts/dashboard
              </code>{" "}
              wires once the substrate-side persistence ledger lands.
              Until then this surface renders the empty state.
            </p>
          )}
        </div>
      </main>
    </div>
  );
}

function Card({
  label,
  value,
  mono,
}: {
  label: string;
  value: string | number;
  mono?: boolean;
}) {
  return (
    <div className="border border-rule dark:border-charcoal-1 rounded px-4 py-3">
      <div className="text-[11px] uppercase tracking-wide text-shadow-1 dark:text-moonlight">
        {label}
      </div>
      <div
        className={`text-xl ${mono ? "font-mono" : "font-mono"} text-ink dark:text-bright mt-1`}
      >
        {value}
      </div>
    </div>
  );
}
