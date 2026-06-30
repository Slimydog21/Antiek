import { useCallback, useEffect, useState } from "react";

import { apiFetch } from "../../lib/api";

/**
 * AdvertiserConsole — Sprint 23-24 operator-only inventory + campaign
 * management surface (master-spec §9.4 lead-gen ads + §9.6).
 *
 * Lead-gen advertiser onboarding in the manual-curation phase:
 *   - inventory entry (slot kind, target topic, creative)
 *   - campaign creation with sector + intent targeting
 *   - performance reporting per campaign
 *
 * Sprint 25+ adds advertiser self-service (conditional on aggregate
 * spend > §9.6 threshold); that surface lives at /advertiser-self-service.
 */

interface AdvertiserCampaign {
  campaign_id: string;
  advertiser_name: string;
  sector: string;
  intent: string;
  creative_headline: string;
  creative_url: string;
  daily_budget_cents: number;
  status: string;
  impressions: number;
  clicks: number;
  spend_cents: number;
}

interface AdvertiserListResponse {
  campaigns: AdvertiserCampaign[];
}

const STATUS_COLOR: Record<string, string> = {
  active: "bg-emerald-100 text-emerald-700",
  paused: "bg-sun/20 text-sun-deep dark:text-sun",
  draft: "bg-ice-3 dark:bg-charcoal-1 text-ink-soft dark:text-starlight",
  rejected: "bg-emperor/20 text-emperor",
};

const USD = (cents: number) =>
  `$${(cents / 100).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;

const CTR = (impressions: number, clicks: number) => {
  if (impressions === 0) return "—";
  return `${((clicks / impressions) * 100).toFixed(2)}%`;
};

const eCPM = (impressions: number, spend_cents: number) => {
  if (impressions === 0) return "—";
  return USD(Math.round((spend_cents / impressions) * 1000));
};

export default function AdvertiserConsole() {
  const [campaigns, setCampaigns] = useState<AdvertiserCampaign[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<string>("all");

  const reload = useCallback(async () => {
    try {
      const resp = await apiFetch("/operator/advertiser-campaigns");
      if (!resp.ok) {
        // Endpoint not yet implemented — show empty state, not error.
        if (resp.status === 404) {
          setCampaigns([]);
          return;
        }
        throw new Error(`HTTP ${resp.status}`);
      }
      const data: AdvertiserListResponse = await resp.json();
      setCampaigns(data.campaigns);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  const visible =
    statusFilter === "all"
      ? campaigns
      : campaigns.filter((c) => c.status === statusFilter);

  const totals = campaigns.reduce(
    (acc, c) => ({
      impressions: acc.impressions + c.impressions,
      clicks: acc.clicks + c.clicks,
      spend_cents: acc.spend_cents + c.spend_cents,
    }),
    { impressions: 0, clicks: 0, spend_cents: 0 },
  );

  return (
    <div className="flex flex-col h-screen">
      <main className="flex-1 overflow-y-auto bg-ice-0 dark:bg-charcoal-2">
        <div className="max-w-5xl mx-auto px-8 py-10 space-y-8">
          <header className="space-y-3">
            <h1 className="text-3xl font-serif text-ink dark:text-bright">
              Advertiser console
            </h1>
            <p className="text-base text-ink dark:text-bright leading-relaxed">
              Operator-mediated lead-gen advertiser inventory and
              campaign management. Vertical SaaS, consulting,
              recruiting — targeted by sector + audience intent.
              Self-service onboarding unlocks at the §9.6 threshold
              (default $50K/mo aggregate spend); below that, all
              campaign activation flows through this console.
            </p>
          </header>

          {error && (
            <p className="text-sm text-emperor border border-red-200 bg-red-50 px-3 py-2 rounded">
              {error}
            </p>
          )}

          <section className="grid grid-cols-3 gap-4">
            <Card label="Total campaigns" value={campaigns.length} />
            <Card
              label="Total impressions"
              value={totals.impressions.toLocaleString()}
            />
            <Card label="Total spend" value={USD(totals.spend_cents)} />
          </section>

          <section className="space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="text-xl font-serif text-ink dark:text-bright">Campaigns</h2>
              <div className="flex gap-1">
                {["all", "active", "paused", "draft", "rejected"].map((s) => (
                  <button
                    key={s}
                    onClick={() => setStatusFilter(s)}
                    className={`text-[11px] font-mono uppercase tracking-wider px-2 py-1 rounded border ${
                      statusFilter === s
                        ? "bg-ink text-white border-ink dark:border-bright"
                        : "bg-ice-0 dark:bg-charcoal-2 text-ink-soft dark:text-starlight border-rule dark:border-charcoal-1 hover:bg-ice-1 dark:bg-charcoal-2"
                    }`}
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>

            {visible.length === 0 ? (
              <p className="text-sm text-ink-soft dark:text-starlight italic">
                No campaigns {statusFilter !== "all" ? `in status "${statusFilter}"` : "yet"}.
                Create one via the operator CRUD endpoint at
                <code className="mx-1 px-1 bg-ice-3 dark:bg-charcoal-1 rounded">
                  POST /operator/advertiser-campaigns
                </code>
                (substrate side persists; UI affordance ships in Sprint 25+).
              </p>
            ) : (
              <ul className="divide-y divide-rule dark:divide-charcoal-1 border border-rule dark:border-charcoal-1 rounded">
                {visible.map((c) => (
                  <li key={c.campaign_id} className="p-4 space-y-2">
                    <div className="flex items-center justify-between">
                      <div>
                        <h3 className="text-base font-serif text-ink dark:text-bright">
                          {c.advertiser_name}
                        </h3>
                        <p className="text-xs font-mono text-shadow-1 dark:text-moonlight">
                          {c.sector} · {c.intent} · daily budget {USD(c.daily_budget_cents)}
                        </p>
                      </div>
                      <span
                        className={`text-[11px] font-mono px-2 py-0.5 rounded ${
                          STATUS_COLOR[c.status] ?? "bg-ice-3 dark:bg-charcoal-1 text-ink-soft dark:text-starlight"
                        }`}
                      >
                        {c.status}
                      </span>
                    </div>
                    <p className="text-sm text-ink dark:text-bright leading-snug">
                      {c.creative_headline}{" "}
                      <a
                        href={c.creative_url}
                        target="_blank"
                        rel="noreferrer noopener"
                        className="text-shadow-1 dark:text-moonlight underline ml-1"
                      >
                        ({c.creative_url})
                      </a>
                    </p>
                    <div className="grid grid-cols-4 gap-4 text-xs font-mono">
                      <Metric label="impressions" value={c.impressions.toLocaleString()} />
                      <Metric label="clicks" value={c.clicks.toLocaleString()} />
                      <Metric label="CTR" value={CTR(c.impressions, c.clicks)} />
                      <Metric label="eCPM" value={eCPM(c.impressions, c.spend_cents)} />
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </div>
      </main>
    </div>
  );
}

function Card({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="border border-rule dark:border-charcoal-1 rounded px-4 py-3">
      <div className="text-[11px] uppercase tracking-wide text-shadow-1 dark:text-moonlight">
        {label}
      </div>
      <div className="text-xl font-mono text-ink dark:text-bright mt-1">{value}</div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col">
      <span className="text-[10px] uppercase tracking-wide text-shadow-1 dark:text-moonlight">
        {label}
      </span>
      <span className="text-ink dark:text-bright">{value}</span>
    </div>
  );
}
