import WorkflowArt from "../../brand/WorkflowArt";
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ErrorBanner } from "../../components/lemon/ErrorBanner";

import { apiFetch } from "../../lib/api";
import { PUBLIC_LANE_LABELS } from "../../lib/speakVocab";

/**
 * Trust Center (master-spec §13.7 + PostHog Wedge 7).
 *
 * Public-facing transparency surface. Reads the backend
 * /trust-center endpoint and renders the operator's published
 * privacy/control posture. Per master-spec §13.7:
 *
 *   "A Trust Center is not a marketing artifact. It is the
 *    operator's standing commitment to the architecture; if a
 *    bullet here is wrong, the bullet is wrong, not the page."
 *
 * Per §16.2 binding rejection: differential-privacy ε budgets are
 * capped at 10. The endpoint surfaces them; the UI renders them and
 * the cap.
 */

interface WebsiteAdsHonesty {
  surface: string;
  serving_model: string;
  max_sdk_on_web: boolean;
  fill_ladder: string[];
  price_status_default: string;
  revenue_usd_cents_until_pricing: number;
  pricing_gate: string;
  legal_gate: string;
  settlement_open?: boolean;
  settlement_path?: string;
  settlement_requires?: string[];
  paid_fill_gated?: boolean;
  paid_fill_requires?: string[];
  paid_fill_default?: string;
  applovin_alignment?: string;
  speak_contributor_share: number;
  speak_platform_share: number;
  money_model: string;
  disbursement: string;
  decision_ref: string;
  spec_ref: string;
  rank01_decision_ref?: string;
  paid_fill_decision_ref?: string;
}

interface SpeakEconomicsHonesty {
  surface?: string;
  g2_counsel_gated?: boolean;
  g3_opt_in_gated?: boolean;
  public_publishing?: string;
  disbursement?: string;
  money_model?: string;
  paid_today?: boolean;
  synquery_partnership?: string;
  synquery_gated?: boolean;
  g2_requires?: string[];
  synquery_requires?: string[];
  decision_refs?: string[];
}

interface TrustCenterData {
  differential_privacy_epsilon_budgets: Record<string, number>;
  deletion_sla_days: number;
  substrate_controls: string[];
  compliance_frameworks: string[];
  loop_3_unlock_status: Record<string, boolean>;
  website_ads?: WebsiteAdsHonesty;
  speak_economics?: SpeakEconomicsHonesty;
}

const EPSILON_CAP = 10;

export default function TrustCenter() {
  const [data, setData] = useState<TrustCenterData | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    try {
      const resp = await apiFetch("/trust-center");
      if (!resp.ok) {
        throw new Error(`GET /trust-center failed: HTTP ${resp.status}`);
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
      <main className="flex-1 overflow-y-auto bg-ice-0 dark:bg-charcoal-2">
        <div className="max-w-3xl mx-auto px-8 py-10 space-y-10">
          <header className="space-y-3">
            <div className="flex items-center gap-3">
              <WorkflowArt workflow="trust" size={56} className="shrink-0" />
              <h1 className="text-2xl font-serif text-ink dark:text-bright">
                Trust Center
              </h1>
            </div>
            <p className="text-base text-ink dark:text-bright leading-relaxed">
              Antiek's standing commitments — privacy architecture,
              differential-privacy parameters, deletion SLA, and the
              gates that govern when the system learns from your
              behavior. The values below are pulled live from the
              substrate; if a bullet is wrong, the bullet is wrong.
            </p>
          </header>

          <aside
            className="rounded-md border-2 border-ink bg-ice-0 p-4 dark:border-charcoal-1 dark:bg-charcoal-1"
            data-testid="trust-speak-browse-link"
          >
            <p className="text-sm text-ink dark:text-bright leading-relaxed">
              {PUBLIC_LANE_LABELS.discoverBrowseBlurb}
            </p>
            <p className="mt-2">
              <Link
                to="/speak/browse"
                className="font-mono text-xs text-sun-deep underline dark:text-sun"
              >
                {PUBLIC_LANE_LABELS.discoverBrowseLink}
              </Link>
            </p>
          </aside>

          {error && (
            <ErrorBanner>
              {error}
            </ErrorBanner>
          )}

          {data && (
            <>
              <Section title="Differential-privacy ε budgets (§16.2)">
                <p className="text-sm text-ink-soft dark:text-starlight leading-relaxed">
                  Antiek hard-caps ε at {EPSILON_CAP} for every
                  category that ever leaves your private partition.
                  Any future category that would exceed this is
                  rejected at registration time. Categories you don't
                  see below contribute zero ε (they are not collected).
                </p>
                <ul className="divide-y divide-rule dark:divide-charcoal-1">
                  {Object.entries(
                    data.differential_privacy_epsilon_budgets,
                  ).map(([category, epsilon]) => (
                    <li
                      key={category}
                      className="py-2 flex items-center justify-between"
                    >
                      <span className="text-sm font-mono text-ink dark:text-bright">
                        {category}
                      </span>
                      <span className="text-sm font-mono text-ink dark:text-bright">
                        ε = {epsilon}
                      </span>
                    </li>
                  ))}
                </ul>
                <p className="text-xs font-mono text-shadow-1 dark:text-moonlight">
                  Hard cap: ε ≤ {EPSILON_CAP}. Beyond this is binding
                  REJECT per master-spec §16.2.
                </p>
              </Section>

              <Section title="Deletion SLA (§13.3)">
                <p className="text-sm text-ink dark:text-bright leading-relaxed">
                  Every deletion request — single-record or
                  delete-all — is honored within {data.deletion_sla_days}{" "}
                  days. The deletion path runs against the substrate,
                  not just the UI; chunks, embeddings, derived skills,
                  and per-user attribution shares all unwind.
                </p>
              </Section>

              <Section title="Substrate controls (§13.7)">
                <ul className="text-sm text-ink dark:text-bright space-y-1 list-disc pl-5">
                  {data.substrate_controls.map((c) => (
                    <li key={c}>{c}</li>
                  ))}
                </ul>
              </Section>

              <Section title="Compliance posture">
                <ul className="text-sm text-ink dark:text-bright space-y-1 list-disc pl-5">
                  {data.compliance_frameworks.map((c) => (
                    <li key={c}>{c}</li>
                  ))}
                </ul>
              </Section>

              {data.website_ads && (
                <Section title="Website advertising (Rank 0 / paid-fill gated)">
                  <p className="text-sm text-ink-soft dark:text-starlight leading-relaxed">
                    Antiek serves its own creatives on the website. There is no
                    AppLovin MAX SDK on web. Fills default to unpriced $0. Rank 0.1 settlement requires an explicit
                    pricing authority plus Rank 0.2 legal gate — never invented cents — Speak&apos;s
                    70% contributor share accrues only from settled revenue,
                    never invented cents.
                  </p>
                  <ul
                    className="text-sm text-ink dark:text-bright space-y-1 list-disc pl-5"
                    data-testid="trust-website-ads"
                  >
                    <li>
                      Serving model:{" "}
                      <code className="font-mono text-xs">
                        {data.website_ads.serving_model}
                      </code>{" "}
                      (MAX on web:{" "}
                      {data.website_ads.max_sdk_on_web ? "yes" : "no"})
                    </li>
                    <li>
                      Fill ladder:{" "}
                      {data.website_ads.fill_ladder.join(" → ")}
                    </li>
                    <li>
                      Default price status:{" "}
                      <code className="font-mono text-xs">
                        {data.website_ads.price_status_default}
                      </code>{" "}
                      / revenue until pricing: $
                      {(data.website_ads.revenue_usd_cents_until_pricing / 100).toFixed(2)}
                    </li>
                    <li>
                      Gates: {data.website_ads.pricing_gate} ·{" "}
                      {data.website_ads.legal_gate}
                    </li>
                    <li>
                      Settlement open:{" "}
                      {data.website_ads.settlement_open ? "yes" : "no"}
                      {data.website_ads.settlement_path
                        ? ` · path ${data.website_ads.settlement_path}`
                        : ""}
                    </li>
                    {data.website_ads.settlement_requires &&
                      data.website_ads.settlement_requires.length > 0 && (
                        <li>
                          Settled requires:{" "}
                          {data.website_ads.settlement_requires.join(" · ")}
                        </li>
                      )}
                    <li data-testid="trust-paid-fill-gated">
                      Paid fill gated:{" "}
                      {data.website_ads.paid_fill_gated === false ? "no" : "yes"}
                      {data.website_ads.paid_fill_default
                        ? ` · default ${data.website_ads.paid_fill_default}`
                        : ""}
                      {data.website_ads.applovin_alignment
                        ? ` · ${data.website_ads.applovin_alignment}`
                        : ""}
                    </li>
                    {data.website_ads.paid_fill_requires &&
                      data.website_ads.paid_fill_requires.length > 0 && (
                        <li>
                          Paid fill requires:{" "}
                          {data.website_ads.paid_fill_requires.join(" · ")}
                        </li>
                      )}
                    <li>
                      Speak escrow split (settled only):{" "}
                      {Math.round(data.website_ads.speak_contributor_share * 100)}%
                      contributors /{" "}
                      {Math.round(data.website_ads.speak_platform_share * 100)}%
                      platform
                    </li>
                    <li>
                      Money model:{" "}
                      <code className="font-mono text-xs">
                        {data.website_ads.money_model}
                      </code>
                    </li>
                    <li>
                      Disbursement:{" "}
                      <code className="font-mono text-xs">
                        {data.website_ads.disbursement}
                      </code>
                    </li>
                  </ul>
                  <p className="text-xs font-mono text-shadow-1 dark:text-moonlight">
                    {data.website_ads.decision_ref}
                  </p>
                </Section>
              )}

              {data.speak_economics && (
                <Section title="Speak economics · G2 counsel · Synquery">
                  <p className="text-sm text-ink-soft dark:text-starlight leading-relaxed">
                    Contributor shares accrue to escrow now; cash does not
                    route until G2 counsel + G3 opt-in clear. Synquery expert
                    network is partnership-gated — not a live booking surface
                    until the operator enables it after creation-surface PMF.
                    Nothing here invents a paid-today promise.
                  </p>
                  <ul
                    className="text-sm text-ink dark:text-bright space-y-1 list-disc pl-5"
                    data-testid="trust-speak-economics"
                  >
                    <li data-testid="trust-g2-counsel-gated">
                      G2 counsel gated:{" "}
                      {data.speak_economics.g2_counsel_gated === false
                        ? "no (publishing live)"
                        : "yes"}
                      {data.speak_economics.public_publishing
                        ? ` · publishing ${data.speak_economics.public_publishing}`
                        : ""}
                    </li>
                    <li>
                      Disbursement:{" "}
                      <code className="font-mono text-xs">
                        {data.speak_economics.disbursement ?? "gated"}
                      </code>
                      {data.speak_economics.paid_today === true
                        ? " · paid today: yes"
                        : " · paid today: no"}
                    </li>
                    <li data-testid="trust-synquery-gated">
                      Synquery partnership:{" "}
                      {data.speak_economics.synquery_partnership ?? "gated"}
                      {data.speak_economics.synquery_gated === false
                        ? " (flag live)"
                        : " (gated)"}
                    </li>
                    <li>
                      Money model:{" "}
                      <code className="font-mono text-xs">
                        {data.speak_economics.money_model ??
                          "accrue_escrow_now_disburse_after_legal_review"}
                      </code>
                    </li>
                    {data.speak_economics.g2_requires &&
                      data.speak_economics.g2_requires.length > 0 && (
                        <li>
                          G2 requires:{" "}
                          {data.speak_economics.g2_requires.join(" · ")}
                        </li>
                      )}
                    {data.speak_economics.synquery_requires &&
                      data.speak_economics.synquery_requires.length > 0 && (
                        <li>
                          Synquery requires:{" "}
                          {data.speak_economics.synquery_requires.join(" · ")}
                        </li>
                      )}
                  </ul>
                </Section>
              )}

              <Section title="Loop 3 (RL training) unlock criteria">
                <p className="text-sm text-ink-soft dark:text-starlight leading-relaxed">
                  Antiek does not train on your data until five
                  criteria are independently satisfied AND the
                  operator explicitly sets <code>ANTIEK_LOOP3_UNLOCKED=1</code>.
                  Criteria-met alone is not enough; the operator
                  authorizes the flip.
                </p>
                <ul className="divide-y divide-rule dark:divide-charcoal-1">
                  {Object.entries(data.loop_3_unlock_status).map(
                    ([criterion, met]) => (
                      <li
                        key={criterion}
                        className="py-2 flex items-center justify-between"
                      >
                        <span className="text-sm font-mono text-ink dark:text-bright">
                          {criterion}
                        </span>
                        <span
                          className={`text-xs font-mono px-2 py-0.5 rounded ${
                            met
                              ? "bg-success/10 text-success"
                              : "bg-ice-3 dark:bg-charcoal-1 text-shadow-1 dark:text-moonlight"
                          }`}
                        >
                          {met ? "MET" : "NOT MET"}
                        </span>
                      </li>
                    ),
                  )}
                </ul>
              </Section>
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
}: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-3 border-t border-rule dark:border-charcoal-1 pt-6 first:border-0 first:pt-0">
      <h2 className="text-xl font-serif text-ink dark:text-bright">{title}</h2>
      {children}
    </section>
  );
}
