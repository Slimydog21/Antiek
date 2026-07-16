import { useCallback, useEffect, useState } from "react";

import SessionBrandChrome from "../../brand/SessionBrandChrome";
import { track } from "../../lib/analytics";
import { apiFetch } from "../../lib/api";

/**
 * Billing summary UI (master-spec §13.5).
 *
 * Operator-facing usage + margin view. Reads
 * GET /billing/summary/{user_id}/{period}. Shows the free-tier
 * progress bar, the public/private split by raw cost + margin,
 * and the total billable.
 *
 * Period defaults to the current month (YYYY-MM).
 */

interface BillingSummary {
  user_id: string;
  period: string;
  free_tokens_consumed: number;
  free_tokens_remaining: number;
  paid_public_token_cost_usd: string;
  paid_public_margin_usd: string;
  paid_private_token_cost_usd: string;
  paid_private_margin_usd: string;
  total_raw_usd: string;
  total_margin_usd: string;
  total_billable_usd: string;
  record_count: number;
}

const FREE_TIER_CAP = 5_000_000;

function currentPeriod(): string {
  const d = new Date();
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  return `${yyyy}-${mm}`;
}

export default function Billing() {
  const [period, setPeriod] = useState<string>(currentPeriod());
  const [userId, setUserId] = useState<string>("__operator__");
  const [data, setData] = useState<BillingSummary | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    track("billing_viewed");
  }, []);

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await apiFetch(
        `/billing/summary/${encodeURIComponent(userId)}/${encodeURIComponent(period)}`,
      );
      if (!resp.ok) {
        throw new Error(`GET /billing/summary: HTTP ${resp.status}`);
      }
      setData(await resp.json());
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [userId, period]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const pctConsumed = data
    ? Math.min(100, Math.round((data.free_tokens_consumed / FREE_TIER_CAP) * 100))
    : 0;

  return (
    <div className="flex flex-col h-screen">
      <main className="flex-1 overflow-y-auto bg-ice-0 dark:bg-charcoal-2">
        <div className="max-w-3xl mx-auto px-8 py-10 space-y-6">
          <SessionBrandChrome
            testIdPrefix="billing-home"
            title="Billing summary"
          >
            <p className="text-sm text-ink-soft dark:text-starlight leading-relaxed">
              Per master-spec §13.5: pay-as-you-go pricing. Free-tier
              cap is {FREE_TIER_CAP.toLocaleString()} tokens/month on
              DeepSeek-Flash; paid-public margin is 10%; paid-private
              margin is 50% (managed-service value).
            </p>
          </SessionBrandChrome>

          <section className="border border-rule dark:border-charcoal-1 rounded-md p-4 grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <label className="text-[10px] font-mono uppercase text-shadow-1 dark:text-moonlight">
                User
              </label>
              <input
                type="text"
                value={userId}
                onChange={(e) => setUserId(e.target.value)}
                className="w-full text-xs font-mono text-ink dark:text-bright border border-rule dark:border-charcoal-1 rounded p-2"
              />
            </div>
            <div className="space-y-1">
              <label className="text-[10px] font-mono uppercase text-shadow-1 dark:text-moonlight">
                Period (YYYY-MM)
              </label>
              <input
                type="text"
                value={period}
                onChange={(e) => setPeriod(e.target.value)}
                className="w-full text-xs font-mono text-ink dark:text-bright border border-rule dark:border-charcoal-1 rounded p-2"
              />
            </div>
          </section>

          {error && (
            <p className="text-sm text-emperor border border-red-200 bg-red-50 px-3 py-2 rounded">
              {error}
            </p>
          )}

          {loading && (
            <p className="text-sm text-shadow-1 dark:text-moonlight italic">Loading…</p>
          )}

          {data && (
            <>
              <section className="border border-rule dark:border-charcoal-1 rounded-md p-5 space-y-3">
                <h2 className="text-base font-serif text-ink dark:text-bright">
                  Free-tier usage
                </h2>
                <div className="h-3 bg-ice-3 dark:bg-charcoal-1 rounded overflow-hidden">
                  <div
                    className={`h-full transition-all ${
                      pctConsumed >= 90
                        ? "bg-sun/100"
                        : "bg-shadow-2"
                    }`}
                    style={{ width: `${pctConsumed}%` }}
                  />
                </div>
                <p className="text-xs font-mono text-ink-soft dark:text-starlight">
                  {data.free_tokens_consumed.toLocaleString()} /{" "}
                  {FREE_TIER_CAP.toLocaleString()} tokens · {pctConsumed}%
                </p>
                <p className="text-[11px] font-mono text-shadow-1 dark:text-moonlight">
                  remaining: {data.free_tokens_remaining.toLocaleString()}
                </p>
              </section>

              <section className="grid grid-cols-2 gap-3">
                <CostCard
                  title="Paid public"
                  margin="10%"
                  raw={data.paid_public_token_cost_usd}
                  marginValue={data.paid_public_margin_usd}
                />
                <CostCard
                  title="Paid private"
                  margin="50%"
                  raw={data.paid_private_token_cost_usd}
                  marginValue={data.paid_private_margin_usd}
                />
              </section>

              <section className="border border-rule dark:border-charcoal-1 rounded-md p-5 space-y-3">
                <h2 className="text-base font-serif text-ink dark:text-bright">
                  Totals
                </h2>
                <Row label="Total raw provider cost" value={data.total_raw_usd} />
                <Row label="Total margin" value={data.total_margin_usd} />
                <Row
                  label="Total billable"
                  value={data.total_billable_usd}
                  emphasize
                />
                <p className="text-[11px] font-mono text-shadow-1 dark:text-moonlight">
                  {data.record_count} usage records aggregated this period
                </p>
              </section>
            </>
          )}
        </div>
      </main>
    </div>
  );
}

function CostCard({
  title,
  margin,
  raw,
  marginValue,
}: { title: string; margin: string; raw: string; marginValue: string }) {
  return (
    <div className="border border-rule dark:border-charcoal-1 rounded-md p-4 space-y-2">
      <div className="flex items-baseline justify-between">
        <h3 className="text-sm font-serif text-ink dark:text-bright">{title}</h3>
        <span className="text-[10px] font-mono text-shadow-1 dark:text-moonlight bg-ice-3 dark:bg-charcoal-1 px-1.5 py-0.5 rounded">
          {margin} margin
        </span>
      </div>
      <Row label="Raw" value={`$${raw}`} small />
      <Row label="Margin" value={`$${marginValue}`} small />
    </div>
  );
}

function Row({
  label,
  value,
  small,
  emphasize,
}: {
  label: string;
  value: string;
  small?: boolean;
  emphasize?: boolean;
}) {
  return (
    <div
      className={`flex items-center justify-between ${
        small ? "text-xs" : "text-sm"
      } ${emphasize ? "font-semibold text-ink dark:text-bright" : "text-ink dark:text-bright"}`}
    >
      <span>{label}</span>
      <span className="font-mono">{value}</span>
    </div>
  );
}
