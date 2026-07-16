import { useState } from "react";

import { LemonButton } from "../../components/lemon";
import type { EconomicsView, PayoutReleaseView } from "../../lib/speakApi";
import { GATE_PHRASES, PAYOUT_COPY } from "../../lib/speakVocab";
import { emitWernerExperience } from "../../werner/reactionBus";

/**
 * SpeakSettings — the one calm tap (Product Depth SPR-08 M4).
 *
 * The old console scattered economics, publishing, consent, contributor
 * mapping and physical-book quotes across a flat wall of action verbs
 * ("corroborate · generate draft · publish · quote paperback") — the literal
 * "looks ugly" the operator named. This gathers all of it behind one calm
 * Settings panel, so the project page itself stays warm (invite · voices ·
 * what everyone agrees on · the assembling story).
 *
 * Two honesty disciplines are encoded here, not decorated on:
 *
 *  1. SPLIT SHOWN, NOT PAID. For a public work the algorithmic contributor
 *     split (70% to the people who contributed) is DISPLAYED — that's the
 *     promise to contributors. But disbursement is gated (G2 payouts + G3
 *     publishing). So the panel shows the split as attribution, labels it
 *     "not paid yet", and shows the honest balance ($0 — no buyers, no ad
 *     revenue). There is deliberately NO disburse / pay button on this
 *     surface; the only money-touching control is the (gated) publish action,
 *     which the backend refuses (409) until the legal gate closes.
 *
 *  2. PUBLISH IS GATED. The publish control says plainly that going public is
 *     gated on the legal review; pressing it surfaces the backend's refusal
 *     rather than pretending it shipped.
 */
export interface SpeakSettingsProps {
  willBePublic: boolean;
  subjectStatusWord: string | null;
  economics: EconomicsView | null;
  /** Run the (gated) publish action — the only money-adjacent control. */
  onPublish: () => void;
  /** Request a physical-book quote (surfacing the affordance; not fulfilment). */
  onQuoteBook: () => void;
  /** The result/refusal text from the last gated action, shown verbatim. */
  actionNote: string | null;
  /** True while a gated action is in flight. */
  busy?: boolean;
  /**
   * Release graded payout (M3). The requester sets the goal + budget + cap;
   * an AI verifier (not the requester) grades each interview; payout scales
   * with the graded quality and routes via §9 into ESCROW (never disbursed
   * pre-gate). Returns the honest accrued figure ($0 with no buyers).
   */
  onReleasePayout?: (args: {
    informationGoal: string;
    budgetUsd: string;
    perInterviewCapUsd: string;
  }) => Promise<PayoutReleaseView>;
}

export default function SpeakSettings({
  willBePublic,
  subjectStatusWord,
  economics,
  onPublish,
  onQuoteBook,
  actionNote,
  busy = false,
  onReleasePayout,
}: SpeakSettingsProps) {
  const splitApplies = economics?.splitApplies ?? willBePublic;
  // Read-only gate state. Deny-by-default; the surface shows these gated and
  // never offers to close them — closing is an operator action, not a click.
  const publishingGated = !(economics?.publicPublishingAllowed ?? false);
  // M2 — read disbursement state LIVE from economics (deny-by-default). The
  // share FRACTION accrues now; the $ amount is honestly $0 with no buyers; and
  // nothing is paid until G2/G3 clears. The inline split copy below branches on
  // this — gated today vs (hypothetically) allowed — with NO close affordance.
  const disbursementAllowed = economics?.disbursementAllowed ?? false;
  const disbursementGated = !disbursementAllowed;

  // M3 — the requester's information goal + budget + cap. Numbers come from
  // the requester here, never from the air.
  const [goal, setGoal] = useState("");
  const [budget, setBudget] = useState("");
  const [cap, setCap] = useState("");
  const [release, setRelease] = useState<PayoutReleaseView | null>(null);
  const [releaseBusy, setReleaseBusy] = useState(false);
  const [releaseErr, setReleaseErr] = useState<string | null>(null);

  const doRelease = async () => {
    if (!onReleasePayout || !goal.trim()) return;
    setReleaseBusy(true);
    setReleaseErr(null);
    try {
      setRelease(
        await onReleasePayout({
          informationGoal: goal.trim(),
          budgetUsd: budget.trim() || "0",
          perInterviewCapUsd: cap.trim() || "0",
        }),
      );
    } catch (e: unknown) {
      setReleaseErr(e instanceof Error ? e.message : String(e));
    } finally {
      setReleaseBusy(false);
    }
  };

  return (
    <div className="space-y-5 rounded-md border-2 border-ink bg-ice-0 p-4 shadow-z1 dark:border-charcoal-1 dark:bg-charcoal-1 dark:shadow-z1-night">
      {/* How it's shared */}
      <section>
        <h3 className="font-mono text-[11px] font-semibold uppercase tracking-wider text-ink-mute dark:text-moonlight">
          How this story is shared
        </h3>
        <p className="mt-1 font-serif text-[13px] text-ink dark:text-bright">
          {willBePublic
            ? "This story will be shared publicly."
            : "This story is kept private — only you can see the assembled draft."}
        </p>
        {subjectStatusWord && (
          <p className="mt-0.5 font-serif text-[12px] text-ink-mute dark:text-moonlight">
            About someone {subjectStatusWord}.
          </p>
        )}
      </section>

      {/* M2 — the publish/invite matrix, mapped to the shipped backend. The
          two dimensions (who can be invited × whether it's published) and
          what each implies. The current project's cell is highlighted. */}
      <section className="rounded border border-rule p-3 dark:border-charcoal-1">
        <h3 className="font-mono text-[11px] font-semibold uppercase tracking-wider text-ink-mute dark:text-moonlight">
          How invites &amp; publishing work
        </h3>
        <div className="mt-2 grid grid-cols-2 gap-2">
          <MatrixCell
            title="Invite-only · kept private"
            body="You invite the people who knew them. Nothing is published; you carry the cost. No earnings split."
            active={!willBePublic}
          />
          <MatrixCell
            title="Invite-only · published"
            body="Invited voices, shared publicly. Ad-supported, so 70% of earnings goes to the contributors (no per-interview fee from you)."
            active={willBePublic}
          />
          <MatrixCell
            title="Open to chime in · kept private"
            body="Anyone with the link can add a memory, but it stays private. (Open public contribution is gated until the multi-user phase.)"
            active={false}
          />
          <MatrixCell
            title="Open to chime in · published"
            body="A public remembrance anyone can add to, shared with ad-economics and the 70% contributor split."
            active={false}
          />
        </div>
        <p className="mt-2 font-serif text-[12px] text-ink-mute dark:text-moonlight">
          A public story always shares 70% of earnings with contributors —
          that's fixed, not something a requester can switch off.
        </p>
      </section>

      {/* The honest split — shown, not paid */}
      <section className="rounded border border-rule p-3 dark:border-charcoal-1">
        <h3 className="font-mono text-[11px] font-semibold uppercase tracking-wider text-ink-mute dark:text-moonlight">
          What contributors are owed
        </h3>
        {splitApplies ? (
          <>
            <p className="mt-1 font-serif text-[13px] text-ink dark:text-bright">
              When a story is public, 70% of what it earns goes to the people
              who contributed their voices — divided by how much each one
              shaped the story.
            </p>
            {/* M3 — HOW the share is decided, in human words. §9.3 Option-B
                basis (shared verbatim with the public lane via PAYOUT_COPY),
                the slop-earns-$0 rule, and verifier-not-requester. No formula,
                no per-second/airtime model. */}
            <p className="mt-2 font-serif text-[12px] text-ink-mute dark:text-moonlight">
              {PAYOUT_COPY.basis}
            </p>
            <p className="mt-1 font-serif text-[12px] text-ink-mute dark:text-moonlight">
              {PAYOUT_COPY.slopEarnsZero}
            </p>
            <p className="mt-1 font-serif text-[12px] text-ink-mute dark:text-moonlight">
              {PAYOUT_COPY.verifierNotRequester}
            </p>
            {/* M2 — the share FRACTION accrues now; the $ AMOUNT is honestly $0
                with no buyers (shown as $0, never a projection). */}
            <p className="mt-2 font-serif text-[13px] text-ink dark:text-bright">
              Each voice's share accrues now. Earned so far:{" "}
              <span className="font-mono font-semibold">$0.00</span>
              <span className="ml-2 text-ink-mute dark:text-moonlight">
                — no buyers or ad revenue yet
              </span>
            </p>
            {/* M2 — owed-not-paid, branched on the LIVE disbursement gate. The
                allowed branch is hypothetical today (deny-by-default); neither
                branch offers a close/enable affordance. */}
            {disbursementAllowed ? (
              <p className="mt-2 font-serif text-[12px] text-ink-mute dark:text-moonlight">
                This is what each voice is owed. Payouts are open — money routes
                to contributors as a public story earns.
              </p>
            ) : (
              <p className="mt-2 font-serif text-[12px] text-ink-mute dark:text-moonlight">
                This is what each voice is owed, not a payment. The share accrues
                now; nothing is paid out until the legal review (G2/G3) is
                complete.
              </p>
            )}
          </>
        ) : (
          <p className="mt-1 font-serif text-[13px] text-ink dark:text-bright">
            A private story isn't monetised, so there's no contributor split —
            you carry the cost. Make it public to share earnings 70% with the
            people who contributed.
          </p>
        )}
      </section>

      {/* Publishing — gated. The gate STATE is read from the backend and
          shown; there is no affordance here to close it (operator-only). */}
      <section>
        <h3 className="font-mono text-[11px] font-semibold uppercase tracking-wider text-ink-mute dark:text-moonlight">
          Publishing
        </h3>
        <div className="mt-1 flex flex-wrap gap-2">
          <GatePill
            label="Public publishing"
            gated={publishingGated}
          />
          <GatePill label="Payouts" gated={disbursementGated} />
        </div>
        {publishingGated ? (
          // Single-sourced from speakVocab.GATE_PHRASES so the gateHonesty
          // contract test covers exactly what this surface renders (and the
          // copy can't drift from the lanes). publicSharing = going public;
          // disbursement = the earnings that ride on it.
          <>
            <p className="mt-2 font-serif text-[13px] text-ink-mute dark:text-moonlight">
              {GATE_PHRASES.publicSharing.whenGated}
            </p>
            <p className="mt-1 font-serif text-[13px] text-ink-mute dark:text-moonlight">
              {GATE_PHRASES.disbursement.whenGated} You can try; we'll tell you
              plainly if it's not ready yet.
            </p>
          </>
        ) : (
          <p className="mt-2 font-serif text-[13px] text-ink-mute dark:text-moonlight">
            Publishing is open. Going public shares the assembled story and
            routes the contributor split.
          </p>
        )}
        <div className="mt-2 flex flex-wrap gap-2">
          <LemonButton variant="secondary" size="sm" disabled={busy} onClick={onPublish}>
            Try to publish
          </LemonButton>
          <LemonButton variant="tertiary" size="sm" disabled={busy} onClick={onQuoteBook}>
            Get a paperback quote
          </LemonButton>
        </div>
        {actionNote && (
          <p className="mt-2 font-serif text-[12px] text-ink dark:text-bright">
            {actionNote}
          </p>
        )}
      </section>

      {/* M3 — AI-graded payout. The requester sets a goal + budget + cap; an
          AI verifier (NOT the requester) grades each interview against the
          goal; payout scales with the graded quality, routes via the §9
          contributor split, and ACCRUES TO ESCROW (never disbursed pre-gate).
          A requester cannot deny a passing interview — that guard lives in
          the backend, not as a switch here. */}
      {onReleasePayout && splitApplies && (
        <section className="rounded border border-rule p-3 dark:border-charcoal-1">
          <h3 className="font-mono text-[11px] font-semibold uppercase tracking-wider text-ink-mute dark:text-moonlight">
            What you're hoping to learn (and the budget for it)
          </h3>
          {/* M3 — the §9.3 Option-B basis, slop-earns-$0, and
              verifier-not-requester, single-sourced from PAYOUT_COPY so this
              surface and the public lane cannot drift. No formula, no
              per-second/airtime model. */}
          <p className="mt-1 font-serif text-[12px] text-ink-mute dark:text-moonlight">
            {PAYOUT_COPY.verifierNotRequester}
          </p>
          <p className="mt-1 font-serif text-[12px] text-ink-mute dark:text-moonlight">
            {PAYOUT_COPY.basis} {PAYOUT_COPY.slopEarnsZero}
          </p>
          <p className="mt-1 font-serif text-[12px] text-ink-mute dark:text-moonlight">
            Nothing is paid out before the legal review — this only sets aside
            what's owed.
          </p>
          <div className="mt-3 space-y-2">
            <textarea
              value={goal}
              onChange={(e) => setGoal(e.target.value)}
              rows={2}
              placeholder="e.g. What was his work, and what was he like during the war years?"
              aria-label="What you're hoping to learn"
              className="w-full rounded border border-rule bg-ice-0 p-2 font-serif text-[13px] text-ink dark:border-charcoal-1 dark:bg-charcoal-2 dark:text-bright"
            />
            <div className="flex flex-wrap gap-2">
              <label className="flex items-center gap-1 font-serif text-[12px] text-ink-mute dark:text-moonlight">
                Total budget $
                <input
                  value={budget}
                  onChange={(e) => setBudget(e.target.value)}
                  inputMode="decimal"
                  placeholder="0"
                  aria-label="Total budget in dollars"
                  className="w-20 rounded border border-rule bg-ice-0 px-2 py-1 font-mono text-[12px] text-ink dark:border-charcoal-1 dark:bg-charcoal-2 dark:text-bright"
                />
              </label>
              <label className="flex items-center gap-1 font-serif text-[12px] text-ink-mute dark:text-moonlight">
                Most per voice $
                <input
                  value={cap}
                  onChange={(e) => setCap(e.target.value)}
                  inputMode="decimal"
                  placeholder="0"
                  aria-label="Most per voice in dollars"
                  className="w-20 rounded border border-rule bg-ice-0 px-2 py-1 font-mono text-[12px] text-ink dark:border-charcoal-1 dark:bg-charcoal-2 dark:text-bright"
                />
              </label>
            </div>
            <LemonButton
              variant="secondary"
              size="sm"
              disabled={releaseBusy || !goal.trim()}
              onClick={() => void doRelease()}
            >
              {releaseBusy ? "Grading…" : "Grade what's been shared & set aside what's owed"}
            </LemonButton>
            {releaseErr && (
              <p className="font-mono text-[11px] text-emperor">{releaseErr}</p>
            )}
            {release && (
              <p className="font-serif text-[12px] text-ink dark:text-bright">
                Set aside so far:{" "}
                <span className="font-mono font-semibold">${release.spentUsd}</span>
                {release.budgetExhausted && " — budget reached"}
                {release.cappedCount > 0 &&
                  ` · ${release.cappedCount} voice${release.cappedCount === 1 ? "" : "s"} hit the per-voice cap`}
                <span className="ml-1 text-ink-mute dark:text-moonlight">
                  (owed, not paid — payouts open after the legal review)
                </span>
              </p>
            )}
          </div>
        </section>
      )}

      {/* Consent + removal */}
      <section>
        <h3 className="font-mono text-[11px] font-semibold uppercase tracking-wider text-ink-mute dark:text-moonlight">
          Consent &amp; removal
        </h3>
        <p className="mt-1 font-serif text-[12px] text-ink-mute dark:text-moonlight">
          Everyone who contributes chooses what they're comfortable with, and
          can ask for their words to be removed at any time. A public story
          also needs the subject's consent (or a documented reason when that
          isn't possible).
        </p>
      </section>
    </div>
  );
}

/** One cell of the publish/invite matrix (M2). The project's current cell is
 *  highlighted; the others explain the options. */
function MatrixCell({
  title,
  body,
  active,
}: {
  title: string;
  body: string;
  active: boolean;
}) {
  return (
    <div
      className={`rounded border p-2 ${
        active
          ? "border-sun bg-sun/10 dark:border-sun"
          : "border-rule dark:border-charcoal-1"
      }`}
    >
      <p className="font-mono text-[10px] font-semibold uppercase tracking-wider text-ink dark:text-bright">
        {title}
        {active && <span className="ml-1 text-sun-deep dark:text-sun">· now</span>}
      </p>
      <p className="mt-1 font-serif text-[12px] text-ink-mute dark:text-moonlight">{body}</p>
    </div>
  );
}

/** A read-only pill showing an operator gate's state. There is deliberately
 *  no control to CLOSE a gate — that is an operator action, never a click. */
function GatePill({ label, gated }: { label: string; gated: boolean }) {
  return (
    <span
      className={`rounded-full border px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider ${
        gated
          ? "border-rule text-ink-mute dark:border-charcoal-1 dark:text-moonlight"
          : "border-sun text-ink dark:text-bright"
      }`}
    >
      {label}: {gated ? "not yet activated" : "open"}
    </span>
  );
}
