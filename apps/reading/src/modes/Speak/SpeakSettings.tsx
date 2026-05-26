import { LemonButton } from "../../components/lemon";
import type { EconomicsView } from "../../lib/speakApi";

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
}

export default function SpeakSettings({
  willBePublic,
  subjectStatusWord,
  economics,
  onPublish,
  onQuoteBook,
  actionNote,
  busy = false,
}: SpeakSettingsProps) {
  const splitApplies = economics?.splitApplies ?? willBePublic;

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
            <p className="mt-2 font-serif text-[13px] text-ink dark:text-bright">
              Earned so far:{" "}
              <span className="font-mono font-semibold">$0.00</span>
              <span className="ml-2 text-ink-mute dark:text-moonlight">
                — no buyers or ad revenue yet
              </span>
            </p>
            <p className="mt-2 font-serif text-[12px] text-ink-mute dark:text-moonlight">
              This is what each voice is owed, not a payment. Payouts open once
              the legal review is complete; nothing is paid out before then.
            </p>
          </>
        ) : (
          <p className="mt-1 font-serif text-[13px] text-ink dark:text-bright">
            A private story isn't monetised, so there's no contributor split —
            you carry the cost. Make it public to share earnings 70% with the
            people who contributed.
          </p>
        )}
      </section>

      {/* Publishing — gated */}
      <section>
        <h3 className="font-mono text-[11px] font-semibold uppercase tracking-wider text-ink-mute dark:text-moonlight">
          Publishing
        </h3>
        <p className="mt-1 font-serif text-[13px] text-ink-mute dark:text-moonlight">
          Going public — and any earnings with it — is on hold until the legal
          review is complete. You can try; we'll tell you plainly if it's not
          ready yet.
        </p>
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
