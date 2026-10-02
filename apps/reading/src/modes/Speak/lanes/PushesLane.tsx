import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { LemonButton } from "../../../components/lemon";
import {
  listPushes,
  makeContributionInvitePath,
  repingInvitee,
  type PrivateReping,
  type PublicOpportunity,
  type PushesView,
} from "../../../lib/speakApi";
import { PUSHES_COPY } from "../../../lib/speakVocab";

/**
 * Dual-push inbox (Anti-Ek Speak remap §PUSHES).
 *
 * (a) Public opportunities — multi-signal heuristic ranking (not ML).
 * (b) Private re-pings — prepare followups + SpeakInvite door.
 * No second notification stack; no ML. Optional AgentMail/Resend when env gate on.
 */
const STATIC_PANEL =
  "rounded-hog border-edge border-rule bg-ice-0 p-4 shadow-z1 " +
  "dark:border-charcoal-1 dark:bg-charcoal-2 dark:shadow-z1-night";

export default function PushesLane() {
  const navigate = useNavigate();
  const [view, setView] = useState<PushesView | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setView(await listPushes());
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  const onContribute = async (projectId: string) => {
    setBusyId(projectId);
    setNote(null);
    try {
      const path = await makeContributionInvitePath(projectId);
      navigate(path);
    } catch {
      setNote("Couldn't open the invite door — try again.");
    } finally {
      setBusyId(null);
    }
  };

  const onReping = async (row: PrivateReping) => {
    setBusyId(row.interviewId);
    setNote(null);
    try {
      const result = await repingInvitee(row.interviewId, { sendEmail: true });
      if (result.skippedReason) {
        setNote(result.skippedReason);
      } else {
        const emailNote =
          result.emailStatus === "sent"
            ? PUSHES_COPY.emailSent
            : result.emailStatus === "skipped_env_gate"
              ? PUSHES_COPY.emailSkippedEnv
              : result.emailStatus && result.emailStatus.startsWith("degraded")
                ? PUSHES_COPY.emailDegraded
                : PUSHES_COPY.repingDone;
        setNote(
          `${emailNote} (+${result.followupsAdded} follow-up` +
            `${result.followupsAdded === 1 ? "" : "s"}; ` +
            `${result.pendingQuestionCount} pending).`,
        );
        navigate(result.invitePath);
      }
      await reload();
    } catch {
      setNote("Couldn't prepare a re-ping — try again.");
    } finally {
      setBusyId(null);
    }
  };

  if (loading && !view) {
    return (
      <p className="font-serif text-sm text-ink-mute dark:text-moonlight">
        Loading pushes…
      </p>
    );
  }

  const pubs: PublicOpportunity[] = view?.publicOpportunities ?? [];
  const privs: PrivateReping[] = view?.privateRepings ?? [];

  return (
    <section className="space-y-4" data-testid="pushes-lane">
      <header>
        <h2 className="font-serif text-lg font-semibold text-ink dark:text-bright">
          {PUSHES_COPY.heading}
        </h2>
        <aside
          role="note"
          className="mt-2 rounded-hog border border-rule bg-ice-0 p-3 dark:border-charcoal-1 dark:bg-charcoal-2"
          data-testid="pushes-honesty-banner"
        >
          <p className="font-serif text-xs text-ink dark:text-bright">
            {PUSHES_COPY.honestyBanner}
          </p>
        </aside>
      </header>

      {error && (
        <p className="font-mono text-xs text-emperor" role="alert">
          {error}
        </p>
      )}
      {note && (
        <p className="font-serif text-xs text-ink-mute dark:text-moonlight" role="status">
          {note}
        </p>
      )}

      <div className={STATIC_PANEL} data-testid="pushes-public-panel">
        <h3 className="font-mono text-xs font-semibold uppercase tracking-wider text-ink-mute dark:text-moonlight">
          {PUSHES_COPY.publicHeading}
        </h3>
          <p className="mt-1 font-serif text-xs text-ink-mute dark:text-moonlight">
            {PUSHES_COPY.rankingSignals}
          </p>
        {pubs.length === 0 ? (
          <p className="mt-2 font-serif text-sm text-ink-mute dark:text-moonlight">
            {PUSHES_COPY.publicEmpty}
          </p>
        ) : (
          <ul className="mt-2 space-y-3">
            {pubs.map((o) => (
              <li
                key={o.projectId}
                className="flex flex-wrap items-start justify-between gap-2 border-b border-rule pb-2 dark:border-charcoal-1"
              >
                <div className="min-w-0">
                  <Link
                    to={`/speak/${o.projectId}`}
                    className="font-serif text-base text-ink hover:underline dark:text-bright"
                  >
                    {o.subjectRef ?? o.title}
                  </Link>
                  <p className="font-serif text-xs text-ink-mute dark:text-moonlight">
                    {o.rankReason}
                  </p>
                </div>
                <LemonButton
                  variant="secondary"
                  size="sm"
                  disabled={busyId === o.projectId}
                  onClick={() => void onContribute(o.projectId)}
                >
                  {PUSHES_COPY.contribute}
                </LemonButton>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className={STATIC_PANEL} data-testid="pushes-private-panel">
        <h3 className="font-mono text-xs font-semibold uppercase tracking-wider text-ink-mute dark:text-moonlight">
          {PUSHES_COPY.privateHeading}
        </h3>
        {privs.length === 0 ? (
          <p className="mt-2 font-serif text-sm text-ink-mute dark:text-moonlight">
            {PUSHES_COPY.privateEmpty}
          </p>
        ) : (
          <ul className="mt-2 space-y-3">
            {privs.map((r) => (
              <li
                key={r.interviewId}
                className="flex flex-wrap items-start justify-between gap-2 border-b border-rule pb-2 dark:border-charcoal-1"
              >
                <div className="min-w-0">
                  <p className="font-serif text-base text-ink dark:text-bright">
                    {r.who}
                    <span className="ml-2 font-mono text-xxs uppercase text-ink-mute dark:text-moonlight">
                      {r.status}
                    </span>
                  </p>
                  <p className="font-serif text-xs text-ink-mute dark:text-moonlight">
                    {r.projectTitle}
                    {r.pendingQuestionCount > 0
                      ? ` · ${r.pendingQuestionCount} pending question` +
                        `${r.pendingQuestionCount === 1 ? "" : "s"}`
                      : " · ready for a follow-up"}
                  </p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <LemonButton
                    variant="secondary"
                    size="sm"
                    disabled={busyId === r.interviewId}
                    onClick={() => void onReping(r)}
                    data-testid={`reping-${r.interviewId}`}
                  >
                    {busyId === r.interviewId
                      ? PUSHES_COPY.repingBusy
                      : PUSHES_COPY.prepareReping}
                  </LemonButton>
                  <Link
                    to={r.invitePath}
                    className="inline-flex items-center font-mono text-xs text-sun-deep underline dark:text-sun"
                  >
                    {PUSHES_COPY.openInvite}
                  </Link>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
