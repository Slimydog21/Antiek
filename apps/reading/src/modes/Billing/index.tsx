import {
  type FormEvent,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import Werner from "../../brand/Werner";
import environment from "../../brand/werner/billing/billing_usage_observatory_environment_v1.webp";
import { track } from "../../lib/analytics";
import { apiFetch } from "../../lib/api";
import "./billing-usage-observatory.css";

/**
 * Billing Usage Observatory (master-spec §13.5).
 *
 * Operator-facing event-derived billable-estimate view. Reads
 * GET /billing/summary/{user_id}/{period}.
 *
 * Truth contract (from live code):
 *   - Only __operator__ currently scans event logs.
 *   - Every DispatchCall is classified PAID_PRIVATE; free/public
 *     values therefore remain zero today.
 *   - Aggregation is on-demand and may be slow.
 *   - Response has no completeness/availability metadata.
 *
 * This instrument is NOT an invoice, charged amount, settled amount,
 * API-key budget, or full provider ledger. It is an event-derived
 * billable estimate.
 */

// ── Types ───────────────────────────────────────────────────────────

export interface BillingSummary {
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

export type ObservatoryState = "idle" | "loading" | "ready" | "empty" | "error";

export type BillingViewProps = {
  state: ObservatoryState;
  userId: string;
  period: string;
  data: BillingSummary | null;
  userIdError: string | null;
  periodError: string | null;
  onUserIdChange: (value: string) => void;
  onPeriodChange: (value: string) => void;
  onApply: () => void;
  onRetry: () => void;
  fixtureTheme?: "dark";
};

// ── Validation ──────────────────────────────────────────────────────

const PERIOD_RE = /^\d{4}-(0[1-9]|1[0-2])$/;
const NONNEG_DECIMAL_RE = /^(0|[1-9]\d*)(?:\.(\d+))?(?:[eE]([+-]?\d+))?$/;
const FREE_TIER_CAP = 5_000_000;
const MAX_EXPANDED_DECIMAL_LENGTH = 512;

const isValidPeriod = (value: string): boolean => PERIOD_RE.test(value);
const isValidUserId = (value: string): boolean => value.trim().length > 0;

/**
 * Safe runtime validation for payload fields.
 *
 * - Integers: must be safe and nonnegative.
 * - USD strings: nonnegative decimal strings, including the exponent form
 *   emitted by Python Decimal. Expanded values are bounded before allocation.
 */
const isSafeInt = (value: unknown): value is number =>
  typeof value === "number" && Number.isSafeInteger(value) && value >= 0;

const expandDecimal = (value: unknown): string | null => {
  if (typeof value !== "string" || value.length > 96) return null;
  const match = NONNEG_DECIMAL_RE.exec(value);
  if (!match) return null;
  const integer = match[1];
  const fraction = match[2] ?? "";
  const exponent = BigInt(match[3] ?? "0");
  const digits = integer + fraction;
  const pointBig = BigInt(integer.length) + exponent;
  const expandedLength = pointBig <= 0n
    ? 2n - pointBig + BigInt(digits.length)
    : pointBig >= BigInt(digits.length)
      ? pointBig
      : BigInt(digits.length + 1);
  if (expandedLength > BigInt(MAX_EXPANDED_DECIMAL_LENGTH)) return null;
  const point = Number(pointBig);
  if (point <= 0) return `0.${"0".repeat(-point)}${digits}`;
  if (point >= digits.length) return `${digits}${"0".repeat(point - digits.length)}`;
  return `${digits.slice(0, point)}.${digits.slice(point)}`;
};

const isNonnegDecimalString = (value: unknown): value is string =>
  expandDecimal(value) !== null;

const isZeroDecimal = (value: unknown) => {
  const expanded = expandDecimal(value);
  return expanded !== null && !/[1-9]/.test(expanded);
};

type ExactDecimal = { coefficient: bigint; scale: number };

const exactDecimal = (value: unknown): ExactDecimal | null => {
  const expanded = expandDecimal(value);
  if (expanded === null) return null;
  const [integer, fraction = ""] = expanded.split(".");
  return { coefficient: BigInt(integer + fraction), scale: fraction.length };
};

const alignedCoefficient = (value: ExactDecimal, scale: number): bigint =>
  value.coefficient * (10n ** BigInt(scale - value.scale));

const decimalRelation = (
  left: unknown,
  right: unknown,
  result: unknown,
  leftMultiplier = 1n,
  rightMultiplier = 1n,
): boolean => {
  const a = exactDecimal(left);
  const b = exactDecimal(right);
  const expected = exactDecimal(result);
  if (!a || !b || !expected) return false;
  const scale = Math.max(a.scale, b.scale, expected.scale);
  return alignedCoefficient(a, scale) * leftMultiplier +
    alignedCoefficient(b, scale) * rightMultiplier ===
    alignedCoefficient(expected, scale);
};

const decimalEqual = (left: unknown, right: unknown): boolean =>
  decimalRelation(left, "0", right);

const isBillingSummary = (value: unknown): value is BillingSummary => {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const r = value as Record<string, unknown>;
  const fieldsValid = (
    typeof r.user_id === "string" && r.user_id.trim().length > 0 &&
    typeof r.period === "string" && isValidPeriod(r.period) &&
    isSafeInt(r.free_tokens_consumed) &&
    isSafeInt(r.free_tokens_remaining) &&
    isNonnegDecimalString(r.paid_public_token_cost_usd) &&
    isNonnegDecimalString(r.paid_public_margin_usd) &&
    isNonnegDecimalString(r.paid_private_token_cost_usd) &&
    isNonnegDecimalString(r.paid_private_margin_usd) &&
    isNonnegDecimalString(r.total_raw_usd) &&
    isNonnegDecimalString(r.total_margin_usd) &&
    isNonnegDecimalString(r.total_billable_usd) &&
    isSafeInt(r.record_count)
  );
  if (!fieldsValid) return false;
  const liveAdapterInvariants = r.free_tokens_consumed === 0 &&
    r.free_tokens_remaining === FREE_TIER_CAP &&
    isZeroDecimal(r.paid_public_token_cost_usd) &&
    isZeroDecimal(r.paid_public_margin_usd) &&
    decimalEqual(r.paid_private_token_cost_usd, r.total_raw_usd) &&
    decimalEqual(r.paid_private_margin_usd, r.total_margin_usd) &&
    decimalRelation(r.paid_private_token_cost_usd, r.paid_private_margin_usd, r.total_billable_usd) &&
    decimalRelation(r.paid_private_margin_usd, r.paid_private_margin_usd, r.paid_private_token_cost_usd);
  if (!liveAdapterInvariants) return false;
  return r.record_count !== 0 || [
    r.paid_private_token_cost_usd,
    r.paid_private_margin_usd,
    r.total_billable_usd,
  ].every(isZeroDecimal);
};

const safePayload = (value: unknown): BillingSummary | null =>
  isBillingSummary(value) ? value : null;

// ── Formatting ──────────────────────────────────────────────────────

function formatUSD(value: string): string {
  const expanded = expandDecimal(value);
  if (expanded === null) return "$—";
  const [rawInteger, rawFraction = ""] = expanded.split(".");
  const integer = rawInteger.replace(/^0+(?=\d)/, "");
  const meaningfulFraction = rawFraction.replace(/0+$/, "");
  const fraction = meaningfulFraction.padEnd(2, "0");
  return `$${integer.replace(/\B(?=(\d{3})+(?!\d))/g, ",")}.${fraction}`;
}

function currentPeriod(): string {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

// ── BillingView (pure) ─────────────────────────────────────────────

export function BillingView({
  state,
  userId,
  period,
  data,
  userIdError,
  periodError,
  onUserIdChange,
  onPeriodChange,
  onApply,
  onRetry,
  fixtureTheme,
}: BillingViewProps) {
  const formValid = isValidUserId(userId) && isValidPeriod(period);

  const submit = useCallback(
    (event: FormEvent) => {
      event.preventDefault();
      if (formValid) onApply();
    },
    [formValid, onApply],
  );

  const pctConsumed = useMemo(() => {
    if (!data) return 0;
    return Math.min(100, Math.round((data.free_tokens_consumed / FREE_TIER_CAP) * 100));
  }, [data]);

  const wernerMood = state === "error" ? "empty" : state === "loading" ? "thinking" : "idle";

  return (
    <main className="buo-shell" data-theme={fixtureTheme}>
      <img
        className="buo-environment"
        src={environment}
        alt=""
        aria-hidden="true"
      />
      <div className="buo-veil" aria-hidden="true" />

      <div className="buo-content">
        {/* ── Hero ──────────────────────────────────── */}
        <header className="buo-hero">
          <div>
            <p className="buo-eyebrow">Operator &middot; event-derived usage</p>
            <h1>Billing Usage Observatory</h1>
            <p className="buo-lede">
              Inspect the substrate&rsquo;s event-derived billable estimate
              for a given user and period. Aggregation is on-demand and
              may be slow.
            </p>
          </div>
          <Werner
            mood={wernerMood}
            size={58}
            label={`Werner ${wernerMood === "empty" ? "found no data" : wernerMood === "thinking" ? "is listening" : "watches the observatory"}`}
          />
        </header>

        {/* ── Truth boundary ────────────────────────── */}
        <aside className="buo-truth" aria-label="Observatory boundary">
          <p className="buo-eyebrow">What this instrument establishes</p>
          <p>
            This is an <strong>event-derived billable estimate</strong>, not
            an invoice, charged amount, settled amount, API-key budget, or
            full provider ledger. The total below is labelled accordingly.
          </p>
          <p>
            Currently, only the <strong>__operator__</strong> identity scans
            event logs. Non-operator identities return an empty result set.
            The current event-log adapter classifies all observed dispatches
            as <strong>paid-private</strong>; free and public values therefore
            remain zero today.
          </p>
          <p>
            The response carries no completeness or availability metadata.
            An unavailable state never infers zero — absence of data is
            displayed as such.
          </p>
        </aside>

        {/* ── Form ──────────────────────────────────── */}
        <section className="buo-station buo-form" aria-labelledby="buo-query-heading">
          <header className="buo-form-header">
            <div>
              <p className="buo-eyebrow">Query parameters</p>
              <h2 id="buo-query-heading">Observatory window</h2>
            </div>
          </header>
          <form onSubmit={submit} role="search">
            <div className="buo-form-grid">
              <label>
                <span>User ID</span>
                <input
                  type="text"
                  value={userId}
                  onChange={(e) => onUserIdChange(e.target.value)}
                  placeholder="__operator__"
                  aria-invalid={Boolean(userIdError)}
                  aria-describedby={userIdError ? "buo-user-hint" : undefined}
                  autoComplete="off"
                />
              </label>
              {userIdError && (
                <p className="buo-form__hint" id="buo-user-hint" role="alert">
                  {userIdError}
                </p>
              )}
              <label>
                <span>Period (YYYY-MM)</span>
                <input
                  type="text"
                  value={period}
                  onChange={(e) => onPeriodChange(e.target.value)}
                  placeholder="2026-07"
                  aria-invalid={Boolean(periodError)}
                  aria-describedby={periodError ? "buo-period-hint" : undefined}
                  autoComplete="off"
                />
              </label>
              {periodError && (
                <p className="buo-form__hint" id="buo-period-hint" role="alert">
                  {periodError}
                </p>
              )}
              <button type="submit" disabled={!formValid || state === "loading"}>
                Read signals
              </button>
            </div>
          </form>
        </section>

        {/* ── Loading ───────────────────────────────── */}
        {state === "loading" && (
          <section className="buo-state" aria-live="polite">
            <h2>Listening for usage signals&hellip;</h2>
            <p>
              Aggregation is on-demand and may be slow. No zero totals
              are inferred while the receiver responds.
            </p>
          </section>
        )}

        {/* ── Error ─────────────────────────────────── */}
        {state === "error" && (
          <section className="buo-state buo-state--error" role="alert">
            <h2>Usage signals unavailable</h2>
            <p>
              The response was unavailable or malformed. No empty ledger
              or zero amount is inferred. Raw backend errors are not
              rendered.
            </p>
            <button type="button" onClick={onRetry}>
              Try again
            </button>
          </section>
        )}

        {/* ── Empty (legitimate empty, not error) ───── */}
        {state === "empty" && (
          <section className="buo-state" aria-live="polite">
            <h2>No usage records returned</h2>
            <p>
              No event-derived usage was recorded for this user and
              period, or the current event-log adapter found no matching
              dispatches. Non-operator identities currently return empty
              results.
            </p>
          </section>
        )}

        {/* ── Results ───────────────────────────────── */}
        {state === "ready" && data && (
          <>
            <section className="buo-results" aria-labelledby="buo-results-heading">
              <header className="buo-results-header">
                <div>
                  <p className="buo-eyebrow">
                    {data.period} &middot; user {data.user_id}
                  </p>
                  <h2 id="buo-results-heading">
                    {data.record_count} usage {data.record_count === 1 ? "record" : "records"}
                  </h2>
                </div>
                <strong title="Event-derived billable estimate">
                  {formatUSD(data.total_billable_usd)}
                </strong>
              </header>
              <p className="buo-results-subtitle">
                The total is an event-derived billable estimate from
                {data.record_count} aggregated usage record
                {data.record_count === 1 ? "" : "s"} this period — not
                a settled charge.
              </p>

              {/* Measures */}
              <div className="buo-measures">
                <div className="buo-measure">
                  <span>{formatUSD(data.total_raw_usd)}</span>
                  <p>Raw provider cost</p>
                </div>
                <div className="buo-measure">
                  <span>{formatUSD(data.total_margin_usd)}</span>
                  <p>Platform margin</p>
                </div>
                <div className="buo-measure">
                  <span>{pctConsumed}%</span>
                  <p>Free-tier consumed</p>
                </div>
              </div>
            </section>

            {/* Free-tier progress */}
            <section className="buo-station" aria-labelledby="buo-freetier-heading">
              <header className="buo-section-heading">
                <h2 id="buo-freetier-heading">Free-tier usage</h2>
                <p>
                  {FREE_TIER_CAP.toLocaleString()} tokens/month cap
                </p>
              </header>
              <div
                role="progressbar"
                aria-valuenow={pctConsumed}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-label={`Free-tier ${pctConsumed}% consumed`}
                style={{
                  height: 10,
                  borderRadius: 5,
                  background: "var(--inset, var(--ice-3))",
                  overflow: "hidden",
                }}
              >
                <div
                  style={{
                    height: "100%",
                    width: `${pctConsumed}%`,
                    borderRadius: 5,
                    background: pctConsumed >= 90 ? "var(--emperor)" : "var(--sun-deep)",
                    transition: "width 150ms ease",
                  }}
                />
              </div>
              <p style={{ marginTop: 8, font: "400 12px/1.4 var(--mono)", color: "var(--muted)" }}>
                {data.free_tokens_consumed.toLocaleString()} /{" "}
                {FREE_TIER_CAP.toLocaleString()} tokens &middot;{" "}
                {data.free_tokens_remaining.toLocaleString()} remaining
              </p>
              <p style={{ marginTop: 4, font: "400 11px/1.4 var(--mono)", color: "var(--muted)" }}>
                Currently zero: all dispatches are classified paid-private.
              </p>
            </section>

            {/* Cost split */}
            <section className="buo-station" aria-labelledby="buo-split-heading">
              <header className="buo-section-heading">
                <h2 id="buo-split-heading">Cost split</h2>
                <p>By dispatch classification</p>
              </header>
              <div className="buo-split">
                <article className="buo-split-card">
                  <span className="buo-margin-tag">10% margin</span>
                  <h3>Paid public</h3>
                  <dl>
                    <div>
                      <dt>Raw</dt>
                      <dd>{formatUSD(data.paid_public_token_cost_usd)}</dd>
                    </div>
                    <div>
                      <dt>Margin</dt>
                      <dd>{formatUSD(data.paid_public_margin_usd)}</dd>
                    </div>
                  </dl>
                  <p style={{ marginTop: 8, font: "400 11px/1.4 var(--mono)", color: "var(--muted)" }}>
                    Currently zero: no paid-public dispatches observed.
                  </p>
                </article>
                <article className="buo-split-card">
                  <span className="buo-margin-tag">50% margin</span>
                  <h3>Paid private</h3>
                  <dl>
                    <div>
                      <dt>Raw</dt>
                      <dd>{formatUSD(data.paid_private_token_cost_usd)}</dd>
                    </div>
                    <div>
                      <dt>Margin</dt>
                      <dd>{formatUSD(data.paid_private_margin_usd)}</dd>
                    </div>
                  </dl>
                  <p style={{ marginTop: 8, font: "400 11px/1.4 var(--mono)", color: "var(--muted)" }}>
                    All observed dispatches are classified paid-private.
                  </p>
                </article>
              </div>
            </section>

            {/* Totals */}
            <section className="buo-totals" aria-labelledby="buo-totals-heading">
              <h2 id="buo-totals-heading">Totals</h2>
              <div className="buo-total-row">
                <span>Total raw provider cost</span>
                <span>{formatUSD(data.total_raw_usd)}</span>
              </div>
              <div className="buo-total-row">
                <span>Total margin</span>
                <span>{formatUSD(data.total_margin_usd)}</span>
              </div>
              <div className="buo-total-row buo-total-row--emphasis">
                <span>Event-derived billable estimate</span>
                <span>{formatUSD(data.total_billable_usd)}</span>
              </div>
              <p className="buo-record-count">
                {data.record_count} usage {data.record_count === 1 ? "record" : "records"}{" "}
                aggregated this period &middot; event-derived, not settled
              </p>
            </section>
          </>
        )}

        {/* ── Idle ──────────────────────────────────── */}
        {state === "idle" && (
          <section className="buo-state" aria-live="polite">
            <h2>Ready to observe</h2>
            <p>
              Enter a user ID and period, then press &ldquo;Read
              signals&rdquo; to fetch the event-derived billable
              estimate.
            </p>
          </section>
        )}
      </div>
    </main>
  );
}

// ── Controller (default export) ─────────────────────────────────────

export default function Billing() {
  const [userId, setUserId] = useState("__operator__");
  const [period, setPeriod] = useState(currentPeriod());
  const [data, setData] = useState<BillingSummary | null>(null);
  const [state, setState] = useState<ObservatoryState>("idle");
  const [userIdError, setUserIdError] = useState<string | null>(null);
  const [periodError, setPeriodError] = useState<string | null>(null);
  const requestRef = useRef(0);

  useEffect(() => {
    track("billing_viewed");
  }, []);

  // Stale-response guard: increment token on each request; discard
  // responses whose token no longer matches the current one.
  // Unmount guard: the cleanup bumps the token so in-flight responses
  // are discarded on unmount.
  const load = useCallback(async (uid: string, per: string) => {
    const token = ++requestRef.current;
    setState("loading");
    try {
      const resp = await apiFetch(
        `/billing/summary/${encodeURIComponent(uid)}/${encodeURIComponent(per)}`,
      );
      if (token !== requestRef.current) return; // stale or unmounted
      if (!resp.ok) {
        setState("error");
        return;
      }
      const parsed = safePayload(await resp.json());
      if (token !== requestRef.current) return; // stale after await
      if (!parsed) {
        setState("error");
        return;
      }
      if (parsed.user_id !== uid || parsed.period !== per) {
        setState("error");
        return;
      }
      // Empty result: zero records with all zeros is still a legitimate
      // empty — but we show the "empty" state so we never infer zero
      // from absence.
      if (parsed.record_count === 0) {
        setData(parsed);
        setState("empty");
      } else {
        setData(parsed);
        setState("ready");
      }
    } catch {
      if (token !== requestRef.current) return;
      setState("error");
    }
  }, []);

  useEffect(() => {
    return () => {
      // Unmount guard: invalidate any in-flight request
      requestRef.current += 1;
    };
  }, []);

  const handleUserIdChange = useCallback((value: string) => {
    requestRef.current += 1;
    setData(null);
    setState("idle");
    setUserId(value);
    setUserIdError(
      value.trim().length === 0 ? "User ID is required" : null,
    );
  }, []);

  const handlePeriodChange = useCallback((value: string) => {
    requestRef.current += 1;
    setData(null);
    setState("idle");
    setPeriod(value);
    if (!value) {
      setPeriodError("Period is required");
    } else if (!isValidPeriod(value)) {
      setPeriodError("Use YYYY-MM format (e.g. 2026-07)");
    } else {
      setPeriodError(null);
    }
  }, []);

  const handleApply = useCallback(() => {
    const uidValid = isValidUserId(userId);
    const perValid = isValidPeriod(period);
    setUserIdError(uidValid ? null : "User ID is required");
    setPeriodError(
      perValid ? null : !period ? "Period is required" : "Use YYYY-MM format (e.g. 2026-07)",
    );
    if (uidValid && perValid) {
      void load(userId.trim(), period);
    }
  }, [userId, period, load]);

  const handleRetry = handleApply;

  return (
    <BillingView
      state={state}
      userId={userId}
      period={period}
      data={data}
      userIdError={userIdError}
      periodError={periodError}
      onUserIdChange={handleUserIdChange}
      onPeriodChange={handlePeriodChange}
      onApply={handleApply}
      onRetry={handleRetry}
    />
  );
}
