import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import PublicLane from "../Speak/lanes/PublicLane";
import {
  listPublicFeed,
  listPublicOpportunities,
  speakPublicHonesty,
  type FeedItem,
  type PublicOpportunity,
} from "../../lib/speakApi";
import { GATE_PHRASES, PUBLIC_LANE_LABELS, PUSHES_COPY } from "../../lib/speakVocab";

/**
 * Unauthenticated public Speak browse (Anti-Ek Speak / spine SPR-03).
 *
 * Sibling to `/speak/invite/:token` — logged-out visitors can read the
 * public-intent feed + heuristic opportunities without RequireAuth.
 * G7 open contribution (when live): visitor CTA mints via open-contribute.
 * Private projects stay invite-only.
 */
export default function SpeakPublicBrowse() {
  const [feed, setFeed] = useState<FeedItem[]>([]);
  const [feedLoading, setFeedLoading] = useState(true);
  const [opps, setOpps] = useState<PublicOpportunity[]>([]);
  const [g7Live, setG7Live] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    setFeedLoading(true);
    setError(null);
    try {
      const [f, o, g7] = await Promise.all([
        listPublicFeed(),
        listPublicOpportunities().catch(() => [] as PublicOpportunity[]),
        speakPublicHonesty().catch(() => ({
          openContributionLive: false,
          publicPublishingLive: false,
          disbursementLive: false,
          moneyModel: "",
        })),
      ]);
      setFeed(f);
      setOpps(o);
      setG7Live(Boolean(g7 && typeof g7 === "object" ? g7.openContributionLive : g7));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
      setFeed([]);
      setOpps([]);
      setG7Live(false);
    } finally {
      setFeedLoading(false);
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  return (
    <div
      className="min-h-screen bg-ice-0 px-4 py-10 dark:bg-charcoal-2"
      data-testid="speak-public-browse"
    >
      <div className="mx-auto max-w-2xl space-y-6">
        <header>
          <p className="font-mono text-[10px] uppercase tracking-wider text-ink-mute dark:text-moonlight">
            Antiek Speak
          </p>
          <h1 className="mt-1 font-serif text-[24px] font-semibold text-ink dark:text-bright">
            {PUBLIC_LANE_LABELS.browseHeading}
          </h1>
          <p className="mt-2 font-serif text-[14px] text-ink-mute dark:text-moonlight">
            {g7Live
              ? PUBLIC_LANE_LABELS.browseSubheadLive
              : PUBLIC_LANE_LABELS.browseSubhead}
          </p>
          <p className="mt-3 font-serif text-[12px]">
            <Link to="/login" className="text-sun-deep underline dark:text-sun">
              Sign in
            </Link>
            {" · "}
            <Link to="/trust" className="text-sun-deep underline dark:text-sun">
              Trust
            </Link>
          </p>
        </header>

        <aside
          role="note"
          className="rounded border-2 border-ink bg-ice-0 p-3 dark:border-charcoal-1 dark:bg-charcoal-1"
          data-testid="browse-g7-banner"
        >
          <p className="font-serif text-[12px] text-ink dark:text-bright">
            {g7Live
              ? PUBLIC_LANE_LABELS.openContributionLive
              : GATE_PHRASES.publicEcosystem.whenGated}
          </p>
        </aside>

        {error && (
          <p className="font-mono text-[12px] text-emperor" role="alert">
            {error}
          </p>
        )}

        <PublicLane feedLoading={feedLoading} feed={feed} visitorMode />

        <section
          className="rounded-md border-2 border-ink bg-ice-0 p-4 shadow-z1 dark:border-charcoal-1 dark:bg-charcoal-1"
          data-testid="browse-opportunities"
        >
          <h2 className="font-mono text-[11px] font-semibold uppercase tracking-wider text-ink-mute dark:text-moonlight">
            {PUSHES_COPY.publicHeading}
          </h2>
          <p className="mt-1 font-serif text-[11px] text-ink-mute dark:text-moonlight">
            {PUSHES_COPY.rankingSignals}
          </p>
          {opps.length === 0 ? (
            <p className="mt-2 font-serif text-[13px] text-ink-mute dark:text-moonlight">
              {PUSHES_COPY.publicEmpty}
            </p>
          ) : (
            <ul className="mt-2 space-y-2">
              {opps.map((o) => (
                <li key={o.projectId} className="border-b border-rule pb-2 dark:border-charcoal-1">
                  <p className="font-serif text-[15px] text-ink dark:text-bright">
                    {o.subjectRef ?? o.title}
                  </p>
                  <p className="font-serif text-[11px] text-ink-mute dark:text-moonlight">
                    {o.rankReason}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </div>
  );
}
