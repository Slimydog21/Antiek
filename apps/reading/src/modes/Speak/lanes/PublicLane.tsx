import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { LemonButton, LemonInput } from "../../../components/lemon";
import { getEconomics, type EconomicsView, type FeedItem } from "../../../lib/speakApi";
import { GATE_PHRASES, PUBLIC_LANE_LABELS } from "../../../lib/speakVocab";

/**
 * PublicLane — the browsable "Public remembrances" tab body (SPR-03).
 *
 * SPR-01 M2 extracted this verbatim from SpeakIndex's public-feed branch so
 * SPR-03 could own the public lane without re-editing the shell. SPR-03 turns
 * it from an accidental dead-end into a designed, HONESTLY-locked surface: a
 * searchable feed of public-intent remembrances; a first-class panel naming the
 * G7 gate that opens open public contribution; a "how it will work" explainer
 * whose G2/G3 lines reflect LIVE gate state; and a CTA that is honest about who
 * can act today. The redesigned surface (search + G7 lock + explainer) renders
 * in EVERY state — including empty-and-unsearched — because a single operator
 * with no public-intent project today would otherwise see none of it (the
 * sprint's centerpiece would be invisible exactly when it matters most).
 *
 * ── THE GATE-READ SPLIT (read twice) ───────────────────────────────────────
 * G2/G3 — public publishing + payouts — ARE read LIVE. `getEconomics(projectId)`
 * returns `publicPublishingAllowed` / `disbursementAllowed`, which are GLOBAL
 * env-flag states surfaced per-project, so reading ANY project gives the correct
 * global answer. When the feed is non-empty we fetch `getEconomics(feed[0].id)`
 * once into internal lane state (this does NOT touch the shell's frozen
 * `{ feedLoading, feed }` props) and branch the explainer's publishing + payout
 * lines: gated copy when denied, an honest "now open" STATE sentence when the
 * gate has cleared. A fetch failure (or an empty feed → nothing to read) is
 * treated as gated — deny-by-default — and never crashes.
 *
 * G7 — open public contribution (the M2 lock panel) — STAYS STATIC. This is the
 * deliberate exception: there is genuinely NO front-end read of the G7 /
 * public-ecosystem gate. `getEconomics` carries ONLY G2/G3; it does NOT expose
 * G7. So the lane-level "open public contribution is not live yet" lock renders
 * the canonical future-tense copy `GATE_PHRASES.publicEcosystem.whenGated`
 * VERBATIM — a true statement, not a faked live read and not an invented
 * endpoint. G7 is a single-operator-until-Sprint-22 ecosystem gate; its state
 * is not, and need not be, a per-request FE read. See
 * docs/decisions/speak-private-public-spine.md.
 *
 * SPR-03 owns this file.
 */
export interface PublicLaneProps {
  /** True while the public feed is loading from `listPublicFeed`. */
  feedLoading: boolean;
  /** The feed of public-intent remembrances (humanized). */
  feed: FeedItem[];
}

const PANEL =
  "rounded-md border-2 border-ink bg-ice-0 p-4 shadow-z1 " +
  "dark:border-charcoal-1 dark:bg-charcoal-1 dark:shadow-z1-night";

export default function PublicLane({ feedLoading, feed }: PublicLaneProps) {
  const [query, setQuery] = useState("");

  // FIX 2 — LIVE G2/G3 read. `getEconomics` is per-project but G2/G3 are GLOBAL
  // env-flag states surfaced per-project, so any project's economics gives the
  // correct global answer. We read feed[0] once when the feed is non-empty and
  // hold the result in INTERNAL lane state (the shell's frozen
  // `{ feedLoading, feed }` prop contract is untouched). Deny-by-default: until
  // a successful read says otherwise, `econ` stays null and the explainer shows
  // the gated copy. A fetch failure resets to null (gated) and never crashes.
  // (G7, by contrast, has no FE read and stays static — see the header.)
  const [econ, setEcon] = useState<EconomicsView | null>(null);
  const probeId = feed.length > 0 ? feed[0].id : null;
  useEffect(() => {
    if (!probeId) {
      setEcon(null);
      return;
    }
    let live = true;
    getEconomics(probeId)
      .then((view) => {
        if (live) setEcon(view);
      })
      .catch(() => {
        // Honest deny-by-default on failure — no crash, treated as gated.
        if (live) setEcon(null);
      });
    return () => {
      live = false;
    };
  }, [probeId]);

  const publishingOpen = econ?.publicPublishingAllowed === true;
  const payoutsOpen = econ?.disbursementAllowed === true;

  // M1 — client-side filter over the props `feed` by subject name. Clearing
  // the box restores the full list. (Server-side / theme search is OUT OF
  // SCOPE — it pulls in the operator-gated shared-graph promotion boundary.)
  const trimmed = query.trim();
  const filtered = useMemo(() => {
    if (!trimmed) return feed;
    const q = trimmed.toLowerCase();
    return feed.filter((f) => f.name.toLowerCase().includes(q));
  }, [feed, trimmed]);

  return (
    <section className="space-y-4">
      {/* ── M1 · search/browse ──────────────────────────────────────────── */}
      <div>
        <LemonInput
          sizing="md"
          wrapperClassName="w-full"
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search public remembrances by name…"
          aria-label="Search public remembrances"
        />
      </div>

      {/* ── M1 · the feed (loading / empty / empty-search / list) ───────── */}
      {feedLoading ? (
        <p className="font-serif text-sm italic text-ink-mute dark:text-moonlight">
          Loading…
        </p>
      ) : feed.length === 0 ? (
        // Honest empty — copy unchanged from the shipped surface.
        <p className="font-serif text-sm italic text-ink-mute dark:text-moonlight">
          No public remembrances yet. When someone shares a story publicly,
          it'll appear here — and you'll be able to add what you remember.
        </p>
      ) : filtered.length === 0 ? (
        // NEW M1 state — a search that matches nothing, named honestly.
        <p className="font-serif text-sm italic text-ink-mute dark:text-moonlight">
          Nothing matches “{trimmed}”. Clear the search to see every public
          remembrance.
        </p>
      ) : (
        <ul className="space-y-2">
          {filtered.map((f) => (
            <li key={f.id} className={PANEL}>
              <div className="flex items-center justify-between gap-3">
                <Link
                  to={`/speak/${f.id}`}
                  className="font-serif text-[16px] text-ink hover:underline dark:text-bright"
                >
                  {f.name}
                </Link>
                <span className="shrink-0 font-mono text-[10px] text-ink-mute dark:text-moonlight">
                  {f.voiceCount === 0
                    ? "no voices yet"
                    : `${f.voiceCount} voice${f.voiceCount === 1 ? "" : "s"}`}
                </span>
              </div>

              {/* Lifecycle honesty: intent remains distinct from a servable
                  publication; only a concrete Read document earns "Read story". */}
              <p className="mt-0.5 font-serif text-[12px] text-ink-mute dark:text-moonlight">
                {f.readerDocumentId ? "Published as a readable story" : PUBLIC_LANE_LABELS.intendedPublic}
              </p>

              {/* M3 — the CTA. PublicLane lives behind RequireAuth, so the
                  viewer IS the operator: a real link to their own project
                  (/speak/:id) is the correct, WORKING action for them. The
                  label is reframed so it never implies a logged-out stranger
                  can contribute now (open public contribution is G7-gated,
                  framed below). No /login link, no 403 button, no dead end. */}
              <div className="mt-2">
                {f.readerDocumentId && (
                  <Link className="mr-2" to={`/read/${encodeURIComponent(f.readerDocumentId)}`}>
                    <LemonButton variant="primary" size="sm">Read story</LemonButton>
                  </Link>
                )}
                <Link to={`/speak/${f.id}`}>
                  <LemonButton variant="secondary" size="sm">
                    Add your memory
                  </LemonButton>
                </Link>
                <p className="mt-1 font-serif text-[11px] text-ink-mute dark:text-moonlight">
                  {PUBLIC_LANE_LABELS.ctaOperatorOnly}
                </p>
              </div>
            </li>
          ))}
        </ul>
      )}

      {/* ── M2 · the honest LOCKED state — the centerpiece ──────────────────
          STATIC, not a live read. There is no FE read of G7, so this renders
          the canonical future-tense G7 sentence VERBATIM. No close/enable
          affordance; future tense only. */}
      <div
        className={PANEL}
        role="note"
        aria-label={GATE_PHRASES.publicEcosystem.label}
      >
        <h3 className="font-serif text-[15px] font-semibold text-ink dark:text-bright">
          {GATE_PHRASES.publicEcosystem.label}
        </h3>
        <p className="mt-1 font-serif text-[13px] text-ink-mute dark:text-moonlight">
          {GATE_PHRASES.publicEcosystem.whenGated}
        </p>
      </div>

      {/* ── M4 · "how it will work" explainer — north-star, honest tense ────
          A calm, first-class description of the eventual flow. The G7 line is
          future-tense and points at the panel above (no duplicate sentence —
          FIX 4). The G2/G3 publishing + payout lines are read LIVE from
          `getEconomics` (FIX 2): gated copy when denied, an honest "now open"
          STATE sentence when the gate has cleared. The payout basis is §9.3
          Option-B — corroboration × source quality, NOT an airtime/ad-duration
          model (see the guard at speakApi.ts releasePayout). */}
      <div className={PANEL}>
        <h3 className="font-serif text-[15px] font-semibold text-ink dark:text-bright">
          {PUBLIC_LANE_LABELS.explainerHeading}
        </h3>
        <ol className="mt-2 space-y-2">
          <li className="font-serif text-[13px] text-ink dark:text-bright">
            {PUBLIC_LANE_LABELS.explainerStepFind}
          </li>
          {/* G7 — static, no FE read; distinct from the M2 panel above. */}
          <li className="font-serif text-[13px] text-ink dark:text-bright">
            {PUBLIC_LANE_LABELS.explainerStepOpenContribution}
          </li>
          {/* G2 — LIVE: gated future-tense copy vs honest open-state copy. */}
          <li className="font-serif text-[13px] text-ink dark:text-bright">
            {publishingOpen
              ? PUBLIC_LANE_LABELS.publishingOpen
              : GATE_PHRASES.publicSharing.whenGated}
          </li>
          {/* G3 — LIVE: gated future-tense copy vs honest open-state copy. */}
          <li className="font-serif text-[13px] text-ink dark:text-bright">
            {payoutsOpen
              ? PUBLIC_LANE_LABELS.payoutsOpen
              : GATE_PHRASES.disbursement.whenGated}
          </li>
        </ol>
        <p className="mt-2 font-serif text-[12px] italic text-ink-mute dark:text-moonlight">
          {PUBLIC_LANE_LABELS.explainerPayoutBasis}
        </p>
      </div>

      {/*
        OUT OF SCOPE (flagged, NOT built) — SPR-01 carry-forward open questions,
        backend/operator scope:
          · an UNAUTHENTICATED /speak browse route (a stranger reading the
            feed without an account);
          · a G7-gated token-mint endpoint that lets a stranger contribute.
        Neither is built here: PublicLane stays authed-only behind RequireAuth,
        and the lane is honest that open public contribution is not yet live.
      */}
    </section>
  );
}
