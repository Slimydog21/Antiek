import { useCallback, useEffect, useState } from "react";

import { apiFetch } from "../../lib/api";
import HeaderBar from "../shared/HeaderBar";

/**
 * Marketplace Metrics — Sprint 25+ §2 dashboard.
 *
 * Operator-only surface that aggregates the three economic loops
 * (creators / publishers / advertisers) into a single health
 * verdict per the Sprint 25+ doc exit criteria: "operator can
 * answer 'is the marketplace healthy' without manual SQL."
 *
 * Reads /marketplace/snapshot — the GET path returns whatever data
 * the substrate currently persists (publisher state from ip_holders).
 * Operator-supplied overrides for creator + advertiser totals are
 * available via POST; this UI ships the read-only GET view.
 */

interface EarningsBucket {
  lower_cents: number;
  upper_cents: number;
  creator_count: number;
}

interface CreatorDistribution {
  creator_count: number;
  total_paid_cents: number;
  median_cents: number;
  p90_cents: number;
  p99_cents: number;
  long_tail_mass: number;
  buckets: EarningsBucket[];
}

interface PublisherStatusCounts {
  pre_onboarded: number;
  invited: number;
  claimed: number;
  opted_out: number;
  total: number;
  claim_rate: number;
  opt_out_rate: number;
}

interface PublisherEscrow {
  status_counts: PublisherStatusCounts;
  total_escrow_accrued_cents: number;
  total_escrow_paid_cents: number;
  unclaimed_escrow_cents: number;
  publishers_with_nontrivial_accrual: number;
}

interface AdvertiserRetention {
  advertiser_count_current: number;
  advertiser_count_prior: number;
  retained_advertiser_count: number;
  new_advertiser_count: number;
  churned_advertiser_count: number;
  total_spend_current_cents: number;
  total_spend_prior_cents: number;
  retention_rate: number;
  crosses_self_service_threshold: boolean;
}

interface MarketplaceSnapshot {
  creators: CreatorDistribution;
  publishers: PublisherEscrow;
  advertisers: AdvertiserRetention;
  health: "healthy" | "watch" | "unhealthy";
  health_signals: string[];
}

const USD = (cents: number) =>
  `$${(cents / 100).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;

const PCT = (frac: number) => `${(frac * 100).toFixed(1)}%`;

function bucketLabel(b: EarningsBucket): string {
  const lo = b.lower_cents;
  const hi = b.upper_cents;
  if (hi === -1) return `${USD(lo)}+`;
  if (lo === 0) return `< ${USD(hi)}`;
  return `${USD(lo)} – ${USD(hi - 1)}`;
}

export default function MarketplaceMetrics() {
  const [data, setData] = useState<MarketplaceSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    try {
      const resp = await apiFetch("/marketplace/snapshot");
      if (!resp.ok) {
        throw new Error(`GET /marketplace/snapshot failed: HTTP ${resp.status}`);
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
        <div className="max-w-4xl mx-auto px-8 py-10 space-y-10">
          <header className="space-y-3">
            <h1 className="text-3xl font-serif text-ink dark:text-bright">
              Marketplace metrics
            </h1>
            <p className="text-base text-ink dark:text-bright leading-relaxed">
              The three economic loops — creators, publishers,
              advertisers — rolled up with a derived health verdict.
              This is the input to the §9.4 "is programmatic display
              warranted" gate and to the Sprint 30+ federation
              thread-trigger evaluation. Numbers below are pulled
              live from the substrate.
            </p>
          </header>

          {error && (
            <p className="text-sm text-emperor border border-red-200 bg-red-50 px-3 py-2 rounded">
              {error}
            </p>
          )}

          {data && (
            <>
              <HealthBanner
                health={data.health}
                signals={data.health_signals}
              />

              <Section title="Creators (§13.9 user-as-IP-holder)">
                <Stat label="Total creators" value={data.creators.creator_count} />
                <Stat
                  label="Total paid"
                  value={USD(data.creators.total_paid_cents)}
                />
                <Stat
                  label="Median earnings"
                  value={USD(data.creators.median_cents)}
                />
                <Stat
                  label="p90"
                  value={USD(data.creators.p90_cents)}
                />
                <Stat
                  label="p99"
                  value={USD(data.creators.p99_cents)}
                />
                <Stat
                  label="Long-tail mass"
                  value={PCT(data.creators.long_tail_mass)}
                  hint="bottom-50% share of total earnings; higher = healthier long tail"
                />
                {data.creators.buckets.length > 0 && (
                  <div className="mt-4">
                    <h3 className="text-xs uppercase tracking-wide text-shadow-1 dark:text-moonlight mb-2">
                      Distribution
                    </h3>
                    <ul className="divide-y divide-rule dark:divide-charcoal-1">
                      {data.creators.buckets.map((b) => (
                        <li
                          key={`${b.lower_cents}-${b.upper_cents}`}
                          className="py-1.5 flex items-center justify-between text-sm"
                        >
                          <span className="font-mono text-ink dark:text-bright">
                            {bucketLabel(b)}
                          </span>
                          <span className="font-mono text-ink dark:text-bright">
                            {b.creator_count} creators
                          </span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </Section>

              <Section title="Publishers (§9.10 pre-onboarded escrow)">
                <Stat
                  label="Pre-onboarded"
                  value={data.publishers.status_counts.pre_onboarded}
                />
                <Stat
                  label="Invited"
                  value={data.publishers.status_counts.invited}
                />
                <Stat
                  label="Claimed"
                  value={data.publishers.status_counts.claimed}
                />
                <Stat
                  label="Opted out"
                  value={data.publishers.status_counts.opted_out}
                />
                <Stat
                  label="Claim rate"
                  value={PCT(data.publishers.status_counts.claim_rate)}
                  hint="claimed / (invited + claimed + opted_out)"
                />
                <Stat
                  label="Opt-out rate"
                  value={PCT(data.publishers.status_counts.opt_out_rate)}
                />
                <Stat
                  label="Escrow accrued"
                  value={USD(data.publishers.total_escrow_accrued_cents)}
                />
                <Stat
                  label="Escrow paid"
                  value={USD(data.publishers.total_escrow_paid_cents)}
                />
                <Stat
                  label="Unclaimed escrow"
                  value={USD(data.publishers.unclaimed_escrow_cents)}
                  hint="awaiting opt-in claim"
                />
              </Section>

              <Section title="Advertisers (§9.6 retention)">
                <Stat
                  label="Current period"
                  value={data.advertisers.advertiser_count_current}
                />
                <Stat
                  label="Prior period"
                  value={data.advertisers.advertiser_count_prior}
                />
                <Stat
                  label="Retained"
                  value={data.advertisers.retained_advertiser_count}
                />
                <Stat
                  label="New"
                  value={data.advertisers.new_advertiser_count}
                />
                <Stat
                  label="Churned"
                  value={data.advertisers.churned_advertiser_count}
                />
                <Stat
                  label="Retention rate"
                  value={PCT(data.advertisers.retention_rate)}
                  hint="retained / prior_count"
                />
                <Stat
                  label="Current spend"
                  value={USD(data.advertisers.total_spend_current_cents)}
                />
                <Stat
                  label="Prior spend"
                  value={USD(data.advertisers.total_spend_prior_cents)}
                />
                <Stat
                  label="Self-service threshold"
                  value={
                    data.advertisers.crosses_self_service_threshold
                      ? "Crossed (§9.6 default $50K/mo)"
                      : "Not crossed"
                  }
                  hint="self-service console unlocks when current spend ≥ threshold"
                />
              </Section>
            </>
          )}
        </div>
      </main>
    </div>
  );
}

function HealthBanner({
  health,
  signals,
}: {
  health: "healthy" | "watch" | "unhealthy";
  signals: string[];
}) {
  const color =
    health === "healthy"
      ? "bg-emerald-50 border-emerald-200 text-emerald-900"
      : health === "watch"
        ? "bg-sun/10 border-amber-200 text-amber-900"
        : "bg-red-50 border-red-200 text-red-900";
  const label =
    health === "healthy"
      ? "HEALTHY"
      : health === "watch"
        ? "WATCH"
        : "UNHEALTHY";
  return (
    <div className={`border rounded-md px-4 py-3 ${color}`}>
      <div className="flex items-center justify-between">
        <span className="text-xs font-mono uppercase tracking-wider">
          Marketplace health
        </span>
        <span className="text-sm font-mono font-bold">{label}</span>
      </div>
      <ul className="mt-2 space-y-1 text-xs font-mono">
        {signals.map((s) => (
          <li key={s}>· {s}</li>
        ))}
      </ul>
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
      <div className="grid grid-cols-2 gap-x-6 gap-y-2">{children}</div>
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
