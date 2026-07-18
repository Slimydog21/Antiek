import { useEffect, useMemo, useState } from "react";

import SessionBrandChrome from "../../brand/SessionBrandChrome";
import { track } from "../../lib/analytics";

/**
 * Pricing surface (master-spec §13.5 + PostHog Wedge 6 template,
 * §5.6 PostHog design philosophy).
 *
 * Operator-decided pay-as-you-go pricing model, verbatim:
 *   "I will charge people like OpenRouter by allowing people to set
 *   a budget for tokens used, and for private documents I will charge
 *   for token usage on such documents at a 50% margin. I guess I will
 *   charge users for public token consumption at a 10% margin, but
 *   will allow rev share of 70% to them on the ad placement."
 *
 * Calculator-driven page per the PostHog Wedge 6 template:
 * transparent voice, free-tier limits prominent, no card on free.
 */
export default function PricingPage() {
  useEffect(() => {
    track("pricing_viewed");
  }, []);

  const [privateTokensMonthly, setPrivateTokensMonthly] = useState<number>(1_000_000);
  const [publicTokensMonthly, setPublicTokensMonthly] = useState<number>(0);
  const [pricePerMilTokens, setPricePerMilTokens] = useState<number>(5);

  const FREE_CAP = 5_000_000;
  const publicAboveCap = Math.max(0, publicTokensMonthly - FREE_CAP);
  const publicFree = Math.min(publicTokensMonthly, FREE_CAP);

  const rawPrivateUsd = useMemo(
    () => (privateTokensMonthly / 1_000_000) * pricePerMilTokens,
    [privateTokensMonthly, pricePerMilTokens],
  );
  const rawPublicAboveCapUsd = useMemo(
    () => (publicAboveCap / 1_000_000) * pricePerMilTokens,
    [publicAboveCap, pricePerMilTokens],
  );
  const privateMargin = rawPrivateUsd * 0.5;
  const publicMargin = rawPublicAboveCapUsd * 0.1;
  const totalUsd = rawPrivateUsd + privateMargin + rawPublicAboveCapUsd + publicMargin;

  return (
    <div className="flex flex-col h-screen">
      <main className="flex-1 overflow-y-auto bg-ice-0 dark:bg-charcoal-2">
        <div className="max-w-3xl mx-auto px-8 py-10 space-y-10">
          <SessionBrandChrome
            testIdPrefix="pricing-home"
            title="Pricing"
            titleClassName="text-3xl font-serif text-ink dark:text-bright"
          >
            <p className="text-base text-ink dark:text-bright leading-relaxed">
              Antiek prices like OpenRouter. You set a token budget;
              we bill against actual usage with a transparent margin
              per tier. No flat subscription. No seat fees. No card
              required for the free tier.
            </p>
          </SessionBrandChrome>

          <section className="space-y-4">
            <h2 className="text-xl font-serif text-ink dark:text-bright">The three tiers</h2>
            <TierCard
              title="Free public tier"
              caption="Up to 5M tokens / month on DeepSeek-Flash."
              margin="0% — ad-supported"
              points={[
                "Consume public-graph notes and book chunks (licensed publishers only).",
                "70% of ad revenue routes to the contributing creator.",
                "Cap auto-converts to Paid Public when you cross 5M tokens.",
                "No card required.",
              ]}
            />
            <TierCard
              title="Paid public (above cap)"
              caption="Pay-as-you-go on tokens beyond the free cap."
              margin="10% margin"
              points={[
                "Any model you pick: DeepSeek-Pro, Claude Sonnet, Opus.",
                "Ads stay on; creators still earn 70% of ad rev-share.",
                "Per-call cost = raw provider cost + 10%.",
                "Same per-query cost transparency as OpenRouter.",
              ]}
            />
            <TierCard
              title="Paid private use"
              caption="Brainstorming Workstation, private documents, private graph."
              margin="50% managed-service margin"
              points={[
                "No ads. Content stays in your private partition.",
                "50% on raw token cost in exchange for substrate value (graph + attribution + voice/style + recursive notes + brainstorming + privacy architecture).",
                "Per-graph encryption keys; ε-bounded telemetry.",
                "The surface that justifies the 50% (master-spec §13.5).",
              ]}
            />
          </section>

          <section className="space-y-4">
            <h2 className="text-xl font-serif text-ink dark:text-bright">Calculator</h2>
            <p className="text-sm text-ink dark:text-bright leading-relaxed">
              Estimate your monthly cost. Sliders are token volumes
              per month; the underlying model price tunes the raw
              cost. Margins apply per master-spec §13.5.
            </p>
            <CalculatorRow
              label={`Private tokens / month: ${privateTokensMonthly.toLocaleString()}`}
            >
              <input
                type="range"
                min={0}
                max={50_000_000}
                step={100_000}
                value={privateTokensMonthly}
                onChange={(e) => setPrivateTokensMonthly(Number(e.target.value))}
                className="w-full"
              />
            </CalculatorRow>
            <CalculatorRow
              label={`Public tokens / month: ${publicTokensMonthly.toLocaleString()}${
                publicFree ? ` (${publicFree.toLocaleString()} free)` : ""
              }`}
            >
              <input
                type="range"
                min={0}
                max={20_000_000}
                step={100_000}
                value={publicTokensMonthly}
                onChange={(e) => setPublicTokensMonthly(Number(e.target.value))}
                className="w-full"
              />
            </CalculatorRow>
            <CalculatorRow
              label={`Provider raw cost per million tokens: $${pricePerMilTokens.toFixed(2)}`}
            >
              <input
                type="range"
                min={1}
                max={20}
                step={1}
                value={pricePerMilTokens}
                onChange={(e) => setPricePerMilTokens(Number(e.target.value))}
                className="w-full"
              />
            </CalculatorRow>

            <div className="border-t border-rule dark:border-charcoal-1 pt-4 space-y-2">
              <CostRow label="Private raw" value={rawPrivateUsd} />
              <CostRow label="Private 50% margin" value={privateMargin} />
              <CostRow label="Public above-cap raw" value={rawPublicAboveCapUsd} />
              <CostRow label="Public 10% margin" value={publicMargin} />
              <div className="border-t border-rule dark:border-charcoal-1 pt-2">
                <CostRow label="Estimated total / month" value={totalUsd} bold />
              </div>
            </div>
          </section>

          <section className="space-y-3 border-t border-rule dark:border-charcoal-1 pt-6">
            <h2 className="text-lg font-serif text-ink dark:text-bright">
              Becoming a creator
            </h2>
            <p className="text-sm text-ink dark:text-bright leading-relaxed">
              Public notes you contribute become first-class IP. When
              another user's session attributes attention to your
              content, you earn 70% of the ad revenue from that
              session. Same architecture as publisher payouts; only
              the population differs (master-spec §13.9).
            </p>
          </section>
        </div>
      </main>
    </div>
  );
}

function TierCard({
  title,
  caption,
  margin,
  points,
}: {
  title: string;
  caption: string;
  margin: string;
  points: string[];
}) {
  return (
    <div className="border border-rule dark:border-charcoal-1 rounded-md px-5 py-4 space-y-3">
      <div className="flex items-baseline justify-between gap-3">
        <h3 className="text-base font-serif text-ink dark:text-bright">{title}</h3>
        <span className="text-xs font-mono text-ink dark:text-bright bg-ice-3 dark:bg-charcoal-1 px-2 py-0.5 rounded">
          {margin}
        </span>
      </div>
      <p className="text-sm text-ink-soft dark:text-starlight">{caption}</p>
      <ul className="text-sm text-ink dark:text-bright space-y-1 list-disc pl-5">
        {points.map((p) => (
          <li key={p}>{p}</li>
        ))}
      </ul>
    </div>
  );
}

function CalculatorRow({
  label,
  children,
}: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <p className="text-xs font-mono text-ink dark:text-bright">{label}</p>
      {children}
    </div>
  );
}

function CostRow({
  label,
  value,
  bold,
}: { label: string; value: number; bold?: boolean }) {
  return (
    <div
      className={`flex items-center justify-between text-sm ${
        bold ? "font-semibold text-ink dark:text-bright" : "text-ink dark:text-bright"
      }`}
    >
      <span>{label}</span>
      <span className="font-mono">${value.toFixed(2)}</span>
    </div>
  );
}
