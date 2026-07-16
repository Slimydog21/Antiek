import { useCallback, useEffect, useState } from "react";

import thinkingArt from "../../brand/werner/poses/session/werner_thinking_session_v1.png";
import { LemonButton } from "../../components/lemon";
import AIActionFailure from "../../shared/AIActionFailure";
import {
  ApiError,
  getAttributionReport,
  getConsentView,
  type AttributionAlgorithmShares,
  type AttributionReportResponse,
  type ConsentViewResponse,
} from "../../lib/api";

/**
 * AccrualView — §9 made legible: whose work grounds a synthesis, and what
 * WOULD be owed for it, shown honestly and never paid (Product Depth SPR-10).
 *
 * Three honesty disciplines are encoded here, not decorated on:
 *
 *  1. ACCRUED, NOT OWED-TODAY. Every figure is "what would be owed," labelled
 *     not-yet-paid. The §9.0.1 truth is that Phase 1 monetisation is the
 *     pay-as-you-go token model, NOT IP payouts — no ad revenue flows yet, so
 *     a zero-buyer balance is honestly $0. This view is telemetry/illustration
 *     of the attribution promise, not a balance owed today.
 *
 *  2. NO MONEY PATH. There is deliberately NO disburse / pay / payout / publish
 *     control that moves money on this surface. The only gated affordance is
 *     "Try a payout", and it is a CLIENT-SIDE gate, not a label: while any
 *     disbursement gate is open (the backend's any_disbursable=false) it
 *     refuses here and fires only a refusal NOTIFICATION (onPayoutRefused),
 *     never a disbursement trigger — there is no host hook to "route a payout"
 *     to. Even the (today-unreachable) unlocked branch does not disburse; it
 *     points payouts at the operator-gated backend route. So a future
 *     maintainer cannot "finish the feature" by wiring this hook to money —
 *     they would have to add a NEW prop + code path and confront the §9.0
 *     legal gate (see the gated-affordance comment + the no-money-path test).
 *
 *  3. OPT-IN ONLY. Escrow accrues for a publisher; it is shown as
 *     escrow-framework-eligible, framed "we will pay you for prospective use
 *     once you opt in" — never "you have $X waiting" against an unconsenting
 *     rights holder (§9.10 / Google Books opt-out rejection). A pre_onboarded
 *     holder reads as eligible-on-opt-in, not as money owed.
 *
 * Attribution is ONE model everywhere. This view reads the SHIPPED §9.3
 * attribution (default Option B per §9.3) and the SHIPPED read-only consent /
 * escrow view; it does not re-implement attribution math in the client. The
 * Speak contributor split (SpeakSettings, SPR-08) and the §13.9
 * user-as-IP-holder framing render the same model — not per-surface
 * reinventions.
 */
export interface AccrualViewProps {
  /** The completed synthesis whose attribution + accrual we surface. */
  synthesisId: string;
  /**
   * Fired ONLY when a payout attempt is refused here — a refusal NOTIFICATION,
   * never a disbursement trigger. It receives the open legal gates (G2/G3) so a
   * host can log/telemeter the refusal; it cannot move money because this
   * surface has no disburse path to route to. Optional: the refusal renders
   * inline regardless. A maintainer cannot turn this into a payout without
   * adding a NEW prop + code path and confronting §9.0.
   */
  onPayoutRefused?: (reason: { openGates: string[] }) => void;
}

const USD = (cents: number) =>
  `$${(cents / 100).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;

const PCT = (frac: number) => `${(frac * 100).toFixed(0)}%`;

/** A per-contributor accrual row: who grounds the synthesis, their share of
 *  the attribution, and what WOULD be owed (clearly not-yet-paid). */
interface AccrualRow {
  documentId: string;
  title: string;
  ipHolderId: string | null;
  /** Lifecycle word (pre_onboarded … claimed); drives the opt-in framing. */
  status: string | null;
  /** Share of attribution under the §9.3 default algorithm (Option B). */
  share: number;
}

/** Build the per-contributor rows from the §9.3 default algorithm (Option B).
 *  A document with no resolved owner keeps an honest null (unknown owner). A
 *  §9.0-restricted source never reaches here — compute.py excludes it before
 *  the share map is built. */
function rowsFromOptionB(b: AttributionAlgorithmShares): AccrualRow[] {
  return Object.entries(b.shares)
    .map(([documentId, share]) => {
      const ipHolderId = b.document_ip_holders[documentId] ?? null;
      return {
        documentId,
        title: b.document_titles[documentId] || "an untitled source",
        ipHolderId,
        status: ipHolderId ? (b.document_ip_holder_status[ipHolderId] ?? "pre_onboarded") : null,
        share,
      };
    })
    .sort((a, b2) => b2.share - a.share);
}

/** Plain-words framing of an IP holder's escrow eligibility — opt-in only.
 *  Never "money waiting"; a pre_onboarded holder is eligible once they opt in. */
function eligibilityNote(status: string | null): string {
  switch (status) {
    case "claimed":
      return "opted in — escrow would route once payouts open";
    case "invited":
      return "invited — escrow eligible once they opt in";
    case "opted_out":
      return "opted out — no escrow accrues";
    case "pre_onboarded":
      return "escrow-eligible once they opt in";
    default:
      // No resolved owner: honest unknown, no fabricated eligibility.
      return "unknown owner — no payee to accrue to";
  }
}

export default function AccrualView({ synthesisId, onPayoutRefused }: AccrualViewProps) {
  const [report, setReport] = useState<AttributionReportResponse | null>(null);
  const [consent, setConsent] = useState<ConsentViewResponse | null>(null);
  const [failed, setFailed] = useState<{ reason: string | null } | null>(null);
  const [loading, setLoading] = useState(true);
  const [payoutNote, setPayoutNote] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setFailed(null);
    try {
      // The attribution report is the load-bearing read (whose work + shares).
      // The consent view is the escrow framing; it is operator-scoped and may
      // be absent without keys, so a failure there does not fail the page.
      const r = await getAttributionReport(synthesisId);
      setReport(r);
      try {
        setConsent(await getConsentView());
      } catch {
        setConsent(null);
      }
    } catch (e: unknown) {
      // Honest no-key / no-result state — never fabricate owed amounts.
      // A 404 / nothing-computed (the common no-provider case) carries NO
      // reason, so AIActionFailure renders the honest no-provider sentence.
      // Only a 5xx with a server-supplied body surfaces the diagnostic verbatim
      // — we never assert a guessed cause over the engine's own.
      const reason =
        e instanceof ApiError && e.status >= 500 && e.body ? e.body : null;
      setReport(null);
      setFailed({ reason });
    } finally {
      setLoading(false);
    }
  }, [synthesisId]);

  useEffect(() => {
    void load();
  }, [load]);

  // The gated payout attempt — the ONLY money-adjacent control on this surface.
  // GATE: G2 (lawyer review) + G3 (publisher opt-in), §9.0. This is a
  // CLIENT-SIDE gate, not a label: disbursement is BLOCKED unless the backend's
  // own any_disbursable is true AND no gate is open. Today that is never true,
  // so it always refuses and fires only the refusal notification — there is no
  // host hook to route a payout to. Even the (today-unreachable) unlocked
  // branch does NOT disburse: real payouts come from the operator-gated backend
  // route, never the client. A maintainer cannot "finish" a payout here.
  const handleAttemptPayout = useCallback(() => {
    const openGates = consent?.disbursement_gates_open ?? [];
    const disbursable = Boolean(consent?.any_disbursable) && openGates.length === 0;
    if (!disbursable) {
      const reasonGates = openGates.length ? openGates : ["G2", "G3"];
      setPayoutNote(
        `Payouts are on hold until the legal review and a publisher's opt-in are complete (${reasonGates.join(" + ")}). ` +
          "Nothing was paid — this only shows what would be owed.",
      );
      onPayoutRefused?.({ openGates: reasonGates });
      return;
    }
    // Reachable only after the operator closes G2 + G3 (any_disbursable=true).
    // Even then this view does NOT disburse: real payouts are issued from the
    // operator-gated backend route, never from the client.
    setPayoutNote(
      "Disbursement is unlocked, but payouts are issued from the operator-gated backend route — not from this view. Nothing was paid here.",
    );
  }, [consent, onPayoutRefused]);

  if (loading) {
    return (
      <p className="text-[12px] font-mono text-shadow-1 dark:text-moonlight italic px-1 py-2">
        working out whose work grounds this…
      </p>
    );
  }

  if (failed) {
    return (
      <AIActionFailure
        title="We couldn't work out the attribution"
        reason={failed.reason}
        onRetry={() => void load()}
      />
    );
  }

  const rows = report ? rowsFromOptionB(report.option_b) : [];
  const accruedCents = consent?.escrow_report.total_escrow_accrued_cents ?? 0;
  const paidCents = consent?.escrow_report.total_escrow_paid_cents ?? 0;

  return (
    <div className="space-y-5 rounded-md border-2 border-ink bg-ice-0 p-4 shadow-z1 dark:border-charcoal-1 dark:bg-charcoal-1 dark:shadow-z1-night">
      {/* What this is — honest framing up top */}
      <section>
        <div className="flex items-center gap-2">
          <img
            src={thinkingArt}
            alt=""
            aria-hidden="true"
            data-testid="accrual-view-werner-brand"
            className="h-7 w-7 shrink-0 object-contain"
          />
          <h3 className="font-mono text-[11px] font-semibold uppercase tracking-wider text-ink-mute dark:text-moonlight">
            What would be owed for this answer
          </h3>
        </div>
        <p className="mt-1 font-serif text-[13px] text-ink dark:text-bright">
          This is who grounds this answer and how attribution would split across
          their work — shown as the promise, not a payment. No ad revenue flows
          yet, so what is owed today is{" "}
          <span className="font-mono font-semibold">$0.00</span>.
        </p>
        <p className="mt-1 font-serif text-[12px] text-ink-mute dark:text-moonlight">
          Split by the same model used everywhere — higher-confidence claims in
          higher-trust sources count for more (§9.3 default).
        </p>
      </section>

      {/* Per-contributor accrual — whose work + share + opt-in eligibility */}
      <section className="rounded border border-rule p-3 dark:border-charcoal-1">
        <h3 className="font-mono text-[11px] font-semibold uppercase tracking-wider text-ink-mute dark:text-moonlight">
          Whose work grounds this
        </h3>
        {rows.length === 0 ? (
          <p className="mt-1 font-serif text-[13px] text-ink-mute dark:text-moonlight">
            No attributable source grounds this answer yet — nothing to accrue.
          </p>
        ) : (
          <ul className="mt-2 divide-y divide-rule dark:divide-charcoal-1">
            {rows.map((r) => (
              <li
                key={r.documentId}
                className="flex items-baseline justify-between gap-3 py-1.5"
              >
                <span className="min-w-0 font-serif text-[13px] text-ink dark:text-bright">
                  {r.title}
                  <span className="ml-1 text-[12px] text-ink-mute dark:text-moonlight">
                    — {eligibilityNote(r.status)}
                  </span>
                </span>
                <span className="flex-shrink-0 text-right">
                  <span className="block font-mono text-[13px] text-ink dark:text-bright">
                    {PCT(r.share)} of attribution
                  </span>
                  <span className="block font-mono text-[11px] text-ink-mute dark:text-moonlight">
                    would be owed · $0.00 today
                  </span>
                </span>
              </li>
            ))}
          </ul>
        )}
        <p className="mt-2 font-serif text-[12px] text-ink-mute dark:text-moonlight">
          A source we may not serve isn't shown here at all — only servable
          work earns attribution on this surface.
        </p>
      </section>

      {/* Escrow accrual — across publishers, opt-in only, not paid */}
      {consent && (
        <section className="rounded border border-rule p-3 dark:border-charcoal-1">
          <h3 className="font-mono text-[11px] font-semibold uppercase tracking-wider text-ink-mute dark:text-moonlight">
            Escrow, across publishers
          </h3>
          <p className="mt-1 font-serif text-[13px] text-ink dark:text-bright">
            Accrued so far:{" "}
            <span className="font-mono font-semibold">{USD(accruedCents)}</span>
            <span className="ml-2 text-ink-mute dark:text-moonlight">
              · paid out: {USD(paidCents)}
            </span>
          </p>
          <p className="mt-1 font-serif text-[12px] text-ink-mute dark:text-moonlight">
            Escrow accrues only for publishers who opt in. We'll pay for
            prospective use once a publisher opts in — there's no money waiting
            against anyone who hasn't.{" "}
            {consent.escrow_report.claimed} opted in ·{" "}
            {consent.escrow_report.pre_onboarded} eligible once they opt in.
          </p>
        </section>
      )}

      {/* Where ads would attribute (Read SPR-06) — explained, never served */}
      <section>
        <h3 className="font-mono text-[11px] font-semibold uppercase tracking-wider text-ink-mute dark:text-moonlight">
          How ads would pay the sources
        </h3>
        <p className="mt-1 font-serif text-[12px] text-ink-mute dark:text-moonlight">
          When a page someday carries an ad, the same split sends a share to the
          work that drove the page (§9.1). There's no live ad and no real
          revenue today — the ad slot is a placeholder, and this view shows
          where attribution would flow, not money that moved.
        </p>
      </section>

      {/* The single gated affordance — refuses with its reason, never pays */}
      <section>
        <h3 className="font-mono text-[11px] font-semibold uppercase tracking-wider text-ink-mute dark:text-moonlight">
          Payouts
        </h3>
        <p className="mt-1 font-serif text-[13px] text-ink-mute dark:text-moonlight">
          Paying out — to any publisher or contributor — is on hold until the
          legal review and a publisher's opt-in are complete. You can try; we'll
          tell you plainly that nothing is paid yet.
        </p>
        <div className="mt-2">
          <LemonButton variant="secondary" size="sm" onClick={handleAttemptPayout}>
            Try a payout
          </LemonButton>
        </div>
        {payoutNote && (
          <p className="mt-2 font-serif text-[12px] text-ink dark:text-bright">
            {payoutNote}
          </p>
        )}
      </section>
    </div>
  );
}
