import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { LemonButton, LemonCard, LemonInput } from "../../../components/lemon";
import {
  getEconomics,
  makeContributionInvitePath,
  openContributePath,
  speakPublicHonesty,
  type EconomicsView,
  type FeedItem,
} from "../../../lib/speakApi";
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
  /** Logged-out browse: no invite mint, no operator console links. */
  visitorMode?: boolean;
}

/**
 * Static-chrome card recipe (D6): heavy edge in `rule`, no sun — the
 * sun-yellow edge stays on the ratified LemonCard primitive only. Used
 * where a panel needs its own element/role (gate notices) and LemonCard
 * can't carry the semantics.
 */
const STATIC_PANEL =
  "rounded-hog border-edge border-rule bg-ice-0 p-4 shadow-z1 " +
  "dark:border-charcoal-1 dark:bg-charcoal-2 dark:shadow-z1-night";


/**
 * Mint a link-only invite and navigate to SpeakInvite (`/speak/invite/:token`).
 * Presentational parent stays prop-driven; mint is on-click (no feed prefetch).
 */
function ContributionInviteCta({
  projectId,
  mode = "operator",
}: {
  projectId: string;
  /** operator = authed mint; open = G7 unauth self-serve. */
  mode?: "operator" | "open";
}) {
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const openDoor = async () => {
    setBusy(true);
    setErr(null);
    try {
      const path =
        mode === "open"
          ? await openContributePath(projectId)
          : await makeContributionInvitePath(projectId);
      navigate(path);
    } catch {
      setErr(PUBLIC_LANE_LABELS.ctaMintFailed);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <LemonButton
        variant="secondary"
        size="sm"
        disabledReason={busy ? "Getting a link" : null}
        onClick={() => void openDoor()}
        data-testid={`contribution-invite-cta-${projectId}`}
      >
        {busy ? PUBLIC_LANE_LABELS.ctaMintBusy : "Add your memory"}
      </LemonButton>
      {err && (
        <p className="mt-1 font-serif text-xs text-emperor" role="alert">
          {err}
        </p>
      )}
    </div>
  );
}

export default function PublicLane({ feedLoading, feed, visitorMode = false }: PublicLaneProps) {
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
  const [g7Live, setG7Live] = useState(false);
  const [publishingLive, setPublishingLive] = useState(false);
  const [disbursementLive, setDisbursementLive] = useState(false);
  const [synqueryLive, setSynqueryLive] = useState(false);
  const probeId = feed.length > 0 ? feed[0].id : null;
  useEffect(() => {
    let live = true;
    speakPublicHonesty()
      .then((h) => {
        if (!live) return;
        setG7Live(h.openContributionLive);
        setPublishingLive(h.publicPublishingLive);
        setDisbursementLive(h.disbursementLive);
        setSynqueryLive(h.synqueryLive);
      })
      .catch(() => {
        if (!live) return;
        setG7Live(false);
        setPublishingLive(false);
        setDisbursementLive(false);
        setSynqueryLive(false);
      });
    return () => {
      live = false;
    };
  }, []);
  useEffect(() => {
    if (!probeId || visitorMode) {
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

      {!visitorMode && (
        <aside
          className="rounded border border-rule bg-ice-0 p-3 dark:border-charcoal-1 dark:bg-charcoal-1"
          data-testid="share-browse-link"
        >
          <p className="font-serif text-xs text-ink-mute dark:text-moonlight">
            {PUBLIC_LANE_LABELS.shareBrowseHint}
          </p>
          <Link
            to="/speak/browse"
            className="mt-1 inline-block font-mono text-xs text-sun-deep underline dark:text-sun"
          >
            {PUBLIC_LANE_LABELS.shareBrowseLink}
          </Link>
        </aside>
      )}

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
            <li key={f.id}>
              <LemonCard elevation="z1">
              <div className="flex items-center justify-between gap-3">
                {visitorMode ? (
                  <span className="font-serif text-base text-ink dark:text-bright">
                    {f.name}
                  </span>
                ) : (
                  <Link
                    to={`/speak/${f.id}`}
                    className="font-serif text-base text-ink hover:underline dark:text-bright"
                  >
                    {f.name}
                  </Link>
                )}
                <span className="shrink-0 font-mono text-xxs text-ink-mute dark:text-moonlight">
                  {f.voiceCount === 0
                    ? "no voices yet"
                    : `${f.voiceCount} voice${f.voiceCount === 1 ? "" : "s"}`}
                </span>
              </div>

              {/* M5 — lifecycle honesty. The feed lists public-INTENT projects;
                  FeedItem carries NO "published" flag, so we NEVER claim a
                  project is published. We label it as intended-public only. */}
              <p className="mt-0.5 font-serif text-xs text-ink-mute dark:text-moonlight">
                {PUBLIC_LANE_LABELS.intendedPublic}
              </p>

              {/* M3 — the CTA. Spine SPR-03 dead-end fix: mint a link-only
                  invite and open /speak/invite/:token (SpeakInvite — unauth,
                  token is the credential). NEVER /speak/:id (operator console).
                  Open contribution WITHOUT an invite stays G7-honest below.
                  Title link above still reaches the operator console. */}
              <div className="mt-2">
                {visitorMode ? (
                  g7Live ? (
                    <>
                      <ContributionInviteCta projectId={f.id} mode="open" />
                      <p
                        className="mt-1 font-serif text-xs text-ink-mute dark:text-moonlight"
                        data-testid={`visitor-cta-note-${f.id}`}
                      >
                        {PUBLIC_LANE_LABELS.visitorCtaNoteLive}
                      </p>
                    </>
                  ) : (
                    <p
                      className="font-serif text-xs text-ink-mute dark:text-moonlight"
                      data-testid={`visitor-cta-note-${f.id}`}
                    >
                      {PUBLIC_LANE_LABELS.visitorCtaNote}
                    </p>
                  )
                ) : (
                  <>
                    <ContributionInviteCta projectId={f.id} />
                    <p className="mt-1 font-serif text-xs text-ink-mute dark:text-moonlight">
                      {PUBLIC_LANE_LABELS.ctaOperatorOnly}
                    </p>
                  </>
                )}
              </div>
              </LemonCard>
            </li>
          ))}
        </ul>
      )}

      {/* ── M2 · the honest LOCKED state — the centerpiece ──────────────────
          STATIC, not a live read. There is no FE read of G7, so this renders
          the canonical future-tense G7 sentence VERBATIM. No close/enable
          affordance; future tense only. */}
      <div
        className={STATIC_PANEL}
        role="note"
        aria-label={GATE_PHRASES.publicEcosystem.label}
      >
        <h3 className="font-serif text-base font-semibold text-ink dark:text-bright">
          {GATE_PHRASES.publicEcosystem.label}
        </h3>
        <p className="mt-1 font-serif text-sm text-ink-mute dark:text-moonlight">
          {g7Live
            ? PUBLIC_LANE_LABELS.openContributionLive
            : GATE_PHRASES.publicEcosystem.whenGated}
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
      <LemonCard elevation="z1">
        <h3 className="font-serif text-base font-semibold text-ink dark:text-bright">
          {PUBLIC_LANE_LABELS.explainerHeading}
        </h3>
        <ol className="mt-2 space-y-2">
          <li className="font-serif text-sm text-ink dark:text-bright">
            {PUBLIC_LANE_LABELS.explainerStepFind}
          </li>
          {/* G7 — static, no FE read; distinct from the M2 panel above. */}
          <li className="font-serif text-sm text-ink dark:text-bright">
            {g7Live
              ? PUBLIC_LANE_LABELS.explainerStepOpenContributionLive
              : PUBLIC_LANE_LABELS.explainerStepOpenContribution}
          </li>
          {/* G2 — LIVE: gated future-tense copy vs honest open-state copy. */}
          <li className="font-serif text-sm text-ink dark:text-bright">
            {publishingOpen || (visitorMode && publishingLive)
              ? PUBLIC_LANE_LABELS.publishingOpen
              : GATE_PHRASES.publicSharing.whenGated}
          </li>
          {/* G3 — LIVE: gated future-tense copy vs honest open-state copy. */}
          <li className="font-serif text-sm text-ink dark:text-bright">
            {payoutsOpen || (visitorMode && disbursementLive)
              ? PUBLIC_LANE_LABELS.payoutsOpen
              : GATE_PHRASES.disbursement.whenGated}
          </li>
          <li
            className="font-serif text-sm text-ink dark:text-bright"
            data-testid="public-lane-synquery-gate"
          >
            {synqueryLive
              ? "Expert-network booking (Synquery) is live for this operator."
              : GATE_PHRASES.synquery.whenGated}
          </li>
        </ol>
        <p className="mt-2 font-serif text-xs italic text-ink-mute dark:text-moonlight">
          {PUBLIC_LANE_LABELS.explainerPayoutBasis}
        </p>
      </LemonCard>

      {/*
        PARTIAL close of spine SPR-03: feed CTA now mints invite tokens →
        SpeakInvite. Still OUT OF SCOPE (operator/G7):
          · an UNAUTHENTICATED /speak browse route (stranger reading the feed
            without an account) — PublicLane stays behind RequireAuth;
          · G7 open contribution is live when opportunities honesty says so;
            private projects remain invite-only.
      */}
    </section>
  );
}
