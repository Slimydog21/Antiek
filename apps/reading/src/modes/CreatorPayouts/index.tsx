import { useCallback, useEffect, useState } from "react";

import { apiFetch } from "../../lib/api";
import HeaderBar from "../shared/HeaderBar";

/**
 * Creator Payouts — Sprint 23-24 user-facing self-service view.
 *
 * Per master-spec §13.9 + §9.5: each user sees their own accrual +
 * paid history under strict per-user scope. The substrate is the
 * writer; this surface is read-only.
 *
 * Status state machine context:
 *   accruing → notice_sent (month 9) → forfeited (month 12)
 *   accruing → settled (when threshold crossed)
 *
 * Below the $10 threshold balances roll over; at month 9 a notice
 * goes out; at month 12 the balance forfeits to the platform residual.
 */

interface RolloverHistoryEntry {
  at: string;
  kind: string;
  cents: number;
}

interface PayoutTransfer {
  transfer_attempt_id: string;
  stripe_transfer_id: string | null;
  amount_usd_cents: number;
  status: string;
  initiated_at: string | null;
  note: string | null;
}

interface CreatorPayouts {
  user_id: string;
  current_balance_cents: number;
  minimum_payout_cents: number;
  rollover_state: string;
  rollover_started_month: number | null;
  accrual_history: RolloverHistoryEntry[];
  transfers: PayoutTransfer[];
  total_paid_cents: number;
}

const USD = (cents: number) =>
  `$${(cents / 100).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;

const STATUS_COLOR: Record<string, string> = {
  transferred: "bg-emerald-100 text-emerald-700",
  pending: "bg-sun/20 text-sun-deep dark:text-sun",
  failed: "bg-emperor/20 text-emperor",
  skipped_escrow: "bg-ice-3 dark:bg-charcoal-1 text-ink-soft dark:text-starlight",
  skipped_platform: "bg-ice-3 dark:bg-charcoal-1 text-ink-soft dark:text-starlight",
};

export default function CreatorPayouts() {
  const [data, setData] = useState<CreatorPayouts | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    try {
      const resp = await apiFetch("/me/payouts");
      if (!resp.ok) {
        throw new Error(`GET /me/payouts failed: HTTP ${resp.status}`);
      }
      setData(await resp.json());
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  return (
    <div className="flex flex-col h-screen">
      <HeaderBar />
      <main className="flex-1 overflow-y-auto bg-ice-0 dark:bg-charcoal-2">
        <div className="max-w-3xl mx-auto px-8 py-10 space-y-10">
          <header className="space-y-3">
            <h1 className="text-3xl font-serif text-ink dark:text-bright">
              Payouts
            </h1>
            <p className="text-base text-ink dark:text-bright leading-relaxed">
              Your accrued ad-revenue share, your minimum payout
              threshold, and the history of transfers Antiek has
              initiated to your Stripe Connect account. Below the
              $10 threshold, balances roll over to the next month;
              after twelve months a small notice precedes forfeit.
            </p>
          </header>

          {error && (
            <p className="text-sm text-emperor border border-red-200 bg-red-50 px-3 py-2 rounded">
              {error}
            </p>
          )}

          {data && (
            <>
              <Section title="Current balance">
                <div className="grid grid-cols-2 gap-x-6 gap-y-2">
                  <Stat
                    label="Accrued (in-window)"
                    value={USD(data.current_balance_cents)}
                  />
                  <Stat
                    label="Minimum payout"
                    value={USD(data.minimum_payout_cents)}
                    hint="§9.5 threshold; below this, balance rolls to next month"
                  />
                  <Stat
                    label="State"
                    value={data.rollover_state}
                  />
                  <Stat
                    label="Months held"
                    value={
                      data.rollover_started_month === null
                        ? "—"
                        : `started month ${data.rollover_started_month}`
                    }
                  />
                  <Stat
                    label="Total paid (lifetime)"
                    value={USD(data.total_paid_cents)}
                  />
                </div>
              </Section>

              <Section title="Transfer history">
                {data.transfers.length === 0 ? (
                  <p className="text-sm text-ink-soft dark:text-starlight italic">
                    No transfers initiated yet. When your balance
                    crosses the §9.5 minimum threshold, Antiek will
                    initiate a transfer to your Stripe Connect account
                    automatically.
                  </p>
                ) : (
                  <ul className="divide-y divide-rule dark:divide-charcoal-1">
                    {data.transfers.map((t) => (
                      <li
                        key={t.transfer_attempt_id}
                        className="py-3 flex items-center justify-between"
                      >
                        <div className="flex flex-col">
                          <span className="text-sm font-mono text-ink dark:text-bright">
                            {USD(t.amount_usd_cents)}
                          </span>
                          <span className="text-[11px] font-mono text-shadow-1 dark:text-moonlight">
                            {t.initiated_at ?? "—"} ·{" "}
                            {t.stripe_transfer_id ?? t.transfer_attempt_id}
                          </span>
                          {t.note && (
                            <span className="text-[11px] text-shadow-1 dark:text-moonlight italic">
                              {t.note}
                            </span>
                          )}
                        </div>
                        <span
                          className={`text-[11px] font-mono px-2 py-0.5 rounded ${
                            STATUS_COLOR[t.status] ?? "bg-ice-3 dark:bg-charcoal-1 text-ink-soft dark:text-starlight"
                          }`}
                        >
                          {t.status}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </Section>

              {data.accrual_history.length > 0 && (
                <Section title="Accrual history">
                  <ul className="divide-y divide-rule dark:divide-charcoal-1">
                    {data.accrual_history.map((e, i) => (
                      <li
                        key={`${e.at}-${i}`}
                        className="py-2 flex items-center justify-between"
                      >
                        <div className="flex flex-col">
                          <span className="text-sm font-mono text-ink dark:text-bright">
                            {USD(e.cents)}
                          </span>
                          <span className="text-[11px] font-mono text-shadow-1 dark:text-moonlight">
                            {e.at}
                          </span>
                        </div>
                        <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-ice-3 dark:bg-charcoal-1 text-ink dark:text-bright">
                          {e.kind}
                        </span>
                      </li>
                    ))}
                  </ul>
                </Section>
              )}
            </>
          )}
        </div>
      </main>
    </div>
  );
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <section className="space-y-3 border-t border-rule dark:border-charcoal-1 pt-6 first:border-0 first:pt-0">
      <h2 className="text-xl font-serif text-ink dark:text-bright">{title}</h2>
      {children}
    </section>
  );
}

function Stat({
  label,
  value,
  hint,
}: {
  label: string;
  value: string | number;
  hint?: string;
}) {
  return (
    <div className="flex flex-col py-1">
      <span className="text-xs uppercase tracking-wide text-shadow-1 dark:text-moonlight">
        {label}
      </span>
      <span className="text-base font-mono text-ink dark:text-bright">{value}</span>
      {hint && (
        <span className="text-[11px] text-shadow-1 dark:text-moonlight italic mt-0.5">
          {hint}
        </span>
      )}
    </div>
  );
}
