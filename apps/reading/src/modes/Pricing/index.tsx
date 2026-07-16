import { useEffect, useId, useMemo, useState } from "react";

import plannerEnvironment from "../../brand/werner/pricing/expedition_cost_planner_environment_v1.webp";
import { track } from "../../lib/analytics";
import "./expedition-cost-planner.css";

export const EXPEDITION_POLICY_EXAMPLE = {
  publicAllowanceTokens: 5_000_000,
  privateMarginRate: 0.5,
  publicMarginRate: 0.1,
} as const;

export const EXPEDITION_PLANNER_LIMITS = {
  tokens: 50_000_000,
  ratePerMillion: 100,
} as const;

export type ExpeditionPlan = {
  privateTokens: number;
  publicTokens: number;
  assumedRatePerMillion: number;
  publicTokensWithinAllowance: number;
  publicTokensAboveAllowance: number;
  privateRaw: number;
  privateMargin: number;
  publicRaw: number;
  publicMargin: number;
  estimatedTotal: number;
};

export function sanitizeNonNegative(value: number): number {
  return Number.isFinite(value) && value > 0 ? value : 0;
}

function clampPlanningInput(value: number, maximum: number): number {
  return Math.min(sanitizeNonNegative(value), maximum);
}

export function calculateExpeditionPlan(
  privateTokensInput: number,
  publicTokensInput: number,
  assumedRateInput: number,
): ExpeditionPlan {
  const privateTokens = clampPlanningInput(
    privateTokensInput,
    EXPEDITION_PLANNER_LIMITS.tokens,
  );
  const publicTokens = clampPlanningInput(
    publicTokensInput,
    EXPEDITION_PLANNER_LIMITS.tokens,
  );
  const assumedRatePerMillion = clampPlanningInput(
    assumedRateInput,
    EXPEDITION_PLANNER_LIMITS.ratePerMillion,
  );
  const publicTokensWithinAllowance = Math.min(
    publicTokens,
    EXPEDITION_POLICY_EXAMPLE.publicAllowanceTokens,
  );
  const publicTokensAboveAllowance = Math.max(
    0,
    publicTokens - publicTokensWithinAllowance,
  );
  const privateRaw = (privateTokens / 1_000_000) * assumedRatePerMillion;
  const privateMargin =
    privateRaw * EXPEDITION_POLICY_EXAMPLE.privateMarginRate;
  const publicRaw =
    (publicTokensAboveAllowance / 1_000_000) * assumedRatePerMillion;
  const publicMargin = publicRaw * EXPEDITION_POLICY_EXAMPLE.publicMarginRate;

  return {
    privateTokens,
    publicTokens,
    assumedRatePerMillion,
    publicTokensWithinAllowance,
    publicTokensAboveAllowance,
    privateRaw,
    privateMargin,
    publicRaw,
    publicMargin,
    estimatedTotal: privateRaw + privateMargin + publicRaw + publicMargin,
  };
}

type PlannerProps = {
  initialPrivateTokens?: number;
  initialPublicTokens?: number;
  initialRatePerMillion?: number;
  visualFixture?: boolean;
};

export default function PricingPage() {
  useEffect(() => {
    track("pricing_viewed");
  }, []);
  return <ExpeditionCostPlanner />;
}

export function ExpeditionCostPlanner({
  initialPrivateTokens = 1_000_000,
  initialPublicTokens = 0,
  initialRatePerMillion = 5,
  visualFixture = false,
}: PlannerProps) {
  const [privateTokens, setPrivateTokens] = useState(initialPrivateTokens);
  const [publicTokens, setPublicTokens] = useState(initialPublicTokens);
  const [assumedRate, setAssumedRate] = useState(initialRatePerMillion);
  const privateId = useId();
  const publicId = useId();
  const rateId = useId();
  const plan = useMemo(
    () => calculateExpeditionPlan(privateTokens, publicTokens, assumedRate),
    [privateTokens, publicTokens, assumedRate],
  );

  return (
    <div
      className="expedition-planner"
      data-visual-fixture={visualFixture || undefined}
    >
      <img
        className="expedition-planner__environment"
        src={plannerEnvironment}
        alt=""
        aria-hidden="true"
        draggable={false}
      />
      <div className="expedition-planner__veil" aria-hidden="true" />

      <div className="expedition-planner__content">
        <header className="expedition-planner__hero">
          <p className="expedition-planner__eyebrow">
            Expedition outfitter · planning instrument
          </p>
          <h1 id="expedition-planner-title">
            Chart the cost before you set out.
          </h1>
          <p className="expedition-planner__lede">
            Set an assumed provider rate and sketch a month of public and
            private work. Antiek shows the arithmetic openly, so an expedition
            can be resized before any model is called.
          </p>
          <p className="expedition-planner__authority" role="note">
            This illustration reads no account, live provider price, usage
            ledger, or billing data. It is not a quote or an invoice.
          </p>
        </header>

        <section
          className="expedition-planner__station"
          aria-labelledby="assumptions-title"
        >
          <div className="expedition-planner__section-heading">
            <p>01 · Pack the assumptions</p>
            <h2 id="assumptions-title">Your planning figures</h2>
          </div>
          <div className="expedition-planner__controls">
            <PlannerControl
              id={privateId}
              label="Private tokens per month"
              hint="Research over private documents and your private graph."
              value={privateTokens}
              max={EXPEDITION_PLANNER_LIMITS.tokens}
              step={100_000}
              onChange={setPrivateTokens}
            />
            <PlannerControl
              id={publicId}
              label="Public tokens per month"
              hint="Work over sources available to the public research graph."
              value={publicTokens}
              max={EXPEDITION_PLANNER_LIMITS.tokens}
              step={100_000}
              onChange={setPublicTokens}
            />
            <PlannerControl
              id={rateId}
              label="Your assumed provider rate"
              hint="US dollars per million tokens. Check your provider before relying on it."
              value={assumedRate}
              max={EXPEDITION_PLANNER_LIMITS.ratePerMillion}
              step={0.25}
              onChange={setAssumedRate}
              unit="$/M"
            />
          </div>
        </section>

        <section
          className="expedition-planner__station"
          aria-labelledby="policy-title"
        >
          <div className="expedition-planner__section-heading">
            <p>02 · Inspect the proposal</p>
            <h2 id="policy-title">Policy example, not active billing</h2>
          </div>
          <div className="expedition-planner__policy-grid">
            <PolicyCard
              value="5M"
              label="public-token allowance"
              detail="each month in this example"
            />
            <PolicyCard
              value="50%"
              label="private-use margin"
              detail="on assumed raw provider cost"
            />
            <PolicyCard
              value="10%"
              label="public margin"
              detail="only above the example allowance"
            />
          </div>
          <p className="expedition-planner__policy-note">
            These are proposed policy figures for planning. They do not prove
            that a tier is active, that a provider or model is available, or
            that any charge will occur.
          </p>
        </section>

        <section
          className="expedition-planner__station expedition-planner__ledger"
          aria-labelledby="estimate-title"
        >
          <div className="expedition-planner__section-heading">
            <p>03 · Weigh the supplies</p>
            <h2 id="estimate-title">Illustrative monthly estimate</h2>
          </div>
          <div className="expedition-planner__ledger-grid">
            <LedgerRow label="Private raw cost" value={plan.privateRaw} />
            <LedgerRow
              label="Private example margin"
              value={plan.privateMargin}
            />
            <LedgerRow
              label="Public tokens inside example allowance"
              tokenValue={plan.publicTokensWithinAllowance}
            />
            <LedgerRow
              label="Public above-allowance raw cost"
              value={plan.publicRaw}
            />
            <LedgerRow
              label="Public example margin"
              value={plan.publicMargin}
            />
          </div>
          <div
            className="expedition-planner__total"
            role="status"
            aria-live="polite"
            aria-atomic="true"
          >
            <span>Estimated planning total</span>
            <strong>{formatUsd(plan.estimatedTotal)}</strong>
          </div>
          <p className="expedition-planner__fineprint">
            Calculation: visible token assumptions × your assumed rate, then the
            proposed margins above. Taxes, provider-specific token classes,
            caching, discounts, reservations, and actual usage are not included.
          </p>
        </section>
      </div>
    </div>
  );
}

function PlannerControl({
  id,
  label,
  hint,
  value,
  max,
  step,
  unit,
  onChange,
}: {
  id: string;
  label: string;
  hint: string;
  value: number;
  max: number;
  step: number;
  unit?: string;
  onChange: (value: number) => void;
}) {
  const normalized = clampPlanningInput(value, max);
  const update = (raw: string) =>
    onChange(clampPlanningInput(Number(raw), max));
  return (
    <div className="expedition-planner__control">
      <div className="expedition-planner__label-row">
        <label htmlFor={id}>{label}</label>
        <span>
          {unit
            ? `${formatNumber(normalized)} ${unit}`
            : formatNumber(normalized)}
        </span>
      </div>
      <p id={`${id}-hint`}>{hint}</p>
      <input
        id={id}
        type="number"
        min="0"
        max={max}
        step={step}
        value={normalized}
        aria-describedby={`${id}-hint`}
        onChange={(event) => update(event.currentTarget.value)}
      />
      <input
        className="expedition-planner__range"
        type="range"
        min="0"
        max={max}
        step={step}
        value={Math.min(normalized, max)}
        aria-label={`${label} slider`}
        onChange={(event) => update(event.currentTarget.value)}
      />
    </div>
  );
}

function PolicyCard({
  value,
  label,
  detail,
}: {
  value: string;
  label: string;
  detail: string;
}) {
  return (
    <article>
      <strong>{value}</strong>
      <span>{label}</span>
      <small>{detail}</small>
    </article>
  );
}

function LedgerRow({
  label,
  value,
  tokenValue,
}: {
  label: string;
  value?: number;
  tokenValue?: number;
}) {
  return (
    <div>
      <span>{label}</span>
      <strong>
        {tokenValue === undefined
          ? formatUsd(value ?? 0)
          : formatNumber(tokenValue)}
      </strong>
    </div>
  );
}

function formatNumber(value: number): string {
  return sanitizeNonNegative(value).toLocaleString(undefined, {
    maximumFractionDigits: 2,
  });
}

function formatUsd(value: number): string {
  return `$${sanitizeNonNegative(value).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}
