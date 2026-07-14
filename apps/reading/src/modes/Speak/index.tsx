import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";

import WernerThinking from "../../brand/werner/animated/WernerThinking";
import { LemonButton } from "../../components/lemon";
import { track } from "../../lib/analytics";
import { apiFetch } from "../../lib/api";
import {
  assembleDraft,
  getEconomics,
  getProject,
  inviteByEmail,
  listVoices,
  makeShareLink,
  releasePayout,
  whatEveryoneAgreesOn,
  type AgreementPoint,
  type ArrivingVoice,
  type AssembledDraft,
  type EconomicsView,
  type ProjectDetail,
} from "../../lib/speakApi";
import { VOICE_STATE_LABELS } from "../../lib/speakVocab";
import GlassSurface from "../../shell/GlassSurface";
import AIActionFailure from "../../shared/AIActionFailure";
import { notifySpeakInviteCommitted } from "../../werner/shellExperienceSignals";
import Invites from "./Invites";
import SpeakSettings from "./SpeakSettings";

/**
 * Speak project page (Product Depth SPR-08 M2 + M4).
 *
 * The operator's verdict on the old console: "no focus and looks ugly." It
 * was a flat wall of action verbs (corroborate · generate draft · publish ·
 * quote paperback) over raw enums. This is a warm, focused page that does the
 * one thing Speak is for: gather voices for someone and watch their story
 * come together.
 *
 *   1. one shareable link to invite the people who knew them;
 *   2. the voices as they arrive (light polling while the page is open);
 *   3. what everyone agrees on — corroboration, framed honestly as
 *      "corroborated", NEVER "proven";
 *   4. the assembling story (creator-only), with Werner present while it
 *      assembles and an honest no-result state without model keys;
 *   5. everything else — economics, the contributor split, publishing,
 *      physical books — behind ONE calm Settings tap (SPR-08 M4).
 *
 * The substrate enums never reach this component: they're translated at the
 * UI edge in lib/speakApi.ts.
 */
type DraftState =
  | { phase: "idle" }
  | { phase: "assembling" }
  | { phase: "ready"; draft: AssembledDraft }
  | { phase: "failed" };

type AgreeState =
  | { phase: "idle" }
  | { phase: "working" }
  | { phase: "ready"; points: AgreementPoint[] }
  | { phase: "failed" };

const POLL_MS = 8000;

async function readDetail(resp: Response): Promise<string> {
  try {
    const body = await resp.json();
    return typeof body.detail === "string" ? body.detail : `HTTP ${resp.status}`;
  } catch {
    return `HTTP ${resp.status}`;
  }
}

export default function Speak() {
  const { projectId } = useParams<{ projectId: string }>();
  const [project, setProject] = useState<ProjectDetail | null>(null);
  const [economics, setEconomics] = useState<EconomicsView | null>(null);
  const [voices, setVoices] = useState<ArrivingVoice[]>([]);
  const [shareLink, setShareLink] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const [showSettings, setShowSettings] = useState(false);
  const [draft, setDraft] = useState<DraftState>({ phase: "idle" });
  const [agree, setAgree] = useState<AgreeState>({ phase: "idle" });

  // Gated-action note (publish / book quote) — shown verbatim, never faked.
  const [actionNote, setActionNote] = useState<string | null>(null);
  const [actionBusy, setActionBusy] = useState(false);

  const reload = useCallback(async () => {
    if (!projectId) return;
    setError(null);
    try {
      const [p, ec, vs] = await Promise.all([
        getProject(projectId),
        getEconomics(projectId).catch(() => null),
        listVoices(projectId).catch(() => [] as ArrivingVoice[]),
      ]);
      setProject(p);
      setEconomics(ec);
      setVoices(vs);
      // Seed the shareable link from the first existing invite, if any.
      setShareLink((cur) => cur || vs.find((v) => v.link)?.link || "");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [projectId]);

  useEffect(() => {
    void reload();
  }, [reload]);

  // Light polling for arriving voices while the page is open. Refreshes just
  // the voices (not the whole page) so an open Settings panel / draft stays
  // put. Calm: no spinner, no churn when nothing changes.
  useEffect(() => {
    if (!projectId) return;
    const t = window.setInterval(() => {
      void listVoices(projectId)
        .then(setVoices)
        .catch(() => {/* keep the last good list; polling is best-effort */});
    }, POLL_MS);
    return () => window.clearInterval(t);
  }, [projectId]);

  const ensureShareLink = useCallback(async () => {
    if (!projectId || shareLink) return;
    try {
      const link = await makeShareLink(projectId);
      track("speak_share_link_created", { project_id: projectId });
      setShareLink(link);
      await reload();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [projectId, shareLink, reload]);

  const copyTimer = useRef<number | null>(null);
  const copyLink = useCallback(() => {
    if (!shareLink) return;
    void navigator.clipboard?.writeText(shareLink);
    setCopied(true);
    if (copyTimer.current) window.clearTimeout(copyTimer.current);
    copyTimer.current = window.setTimeout(() => setCopied(false), 1800);
  }, [shareLink]);

  const invite = useCallback(async (email: string) => {
    if (!projectId) return;
    try {
      await inviteByEmail(projectId, email);
      notifySpeakInviteCommitted();
      track("speak_invite_sent", { project_id: projectId });
      await reload();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [projectId, reload]);

  const seeAgreement = useCallback(async () => {
    if (!projectId) return;
    setAgree({ phase: "working" });
    try {
      const points = await whatEveryoneAgreesOn(projectId);
      setAgree({ phase: "ready", points });
    } catch {
      setAgree({ phase: "failed" });
    }
  }, [projectId]);

  const assemble = useCallback(async () => {
    if (!projectId) return;
    setDraft({ phase: "assembling" });
    try {
      const d = await assembleDraft(projectId, project?.willBePublic ?? false);
      track("speak_draft_assembled", {
        project_id: projectId,
        will_be_public: project?.willBePublic ?? false,
      });
      setDraft({ phase: "ready", draft: d });
    } catch {
      setDraft({ phase: "failed" });
    }
  }, [projectId, project?.willBePublic]);

  // The gated, money-adjacent actions (publish / book quote). They surface the
  // backend's verbatim refusal (G2/G3) — never a pretend success.
  const runGated = useCallback(
    async (label: string, path: string, body: unknown) => {
      if (!projectId) return;
      setActionBusy(true);
      setActionNote(`${label}…`);
      try {
        const resp = await apiFetch(`/speak/projects/${projectId}${path}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        const detail = resp.ok ? null : await readDetail(resp);
        if (!resp.ok) {
          setActionNote(`Not yet — ${detail}`);
          return;
        }
        const data = await resp.json().catch(() => ({}));
        if (label === "Publishing") {
          setActionNote(
            data.served
              ? "Published."
              : "Saved privately — not shared publicly (publishing is still gated).",
          );
        } else {
          setActionNote(
            `Paperback quote: $${data.cost_usd ?? "—"} (not ordered — fulfilment is gated).`,
          );
        }
        await reload();
      } catch (e: unknown) {
        setActionNote(e instanceof Error ? e.message : String(e));
      } finally {
        setActionBusy(false);
      }
    },
    [projectId, reload],
  );

  if (!projectId) {
    return (
      <div className="p-6 font-serif text-[14px] text-ink dark:text-bright">
        No one selected.{" "}
        <Link to="/speak" className="text-sun-deep underline dark:text-sun">
          ← everyone you're remembering
        </Link>
      </div>
    );
  }

  const arrived = voices.filter((v) => v.state === "shared" || v.state === "recording");

  return (
    // Landing-glass (SPR-03 M2): the Speak project page is a LANDING surface —
    // its full-bleed root renders through GlassSurface so the <Scene/> (z-0)
    // shows through, with the scrim guaranteeing the body text stays ≥4.5:1.
    // Was an opaque bg-ice-0 dark:bg-charcoal-2 wall over the scene. The inner
    // cards keep their own chrome; only the occluding outer sheet is glassed.
    <GlassSurface className="h-full overflow-y-auto">
      <div className="mx-auto max-w-2xl px-6 py-8">
        <Link
          to="/speak"
          className="font-mono text-[10px] text-sun-deep hover:underline dark:text-sun"
        >
          ← everyone you're remembering
        </Link>

        <header className="mb-5 mt-2 flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h1 className="font-serif text-2xl font-semibold text-ink dark:text-bright">
              {project?.name ?? "Their story"}
            </h1>
            <p className="mt-0.5 font-serif text-[13px] text-ink-mute dark:text-moonlight">
              {project?.willBePublic ? "Will be shared publicly" : "Kept private"}
            </p>
          </div>
          <LemonButton
            variant="tertiary"
            size="sm"
            onClick={() => setShowSettings((v) => !v)}
            aria-expanded={showSettings}
          >
            {showSettings ? "Done" : "Settings"}
          </LemonButton>
        </header>

        {error && <p className="mb-3 font-mono text-[12px] text-emperor">{error}</p>}

        {showSettings ? (
          <SpeakSettings
            willBePublic={project?.willBePublic ?? false}
            subjectStatusWord={project?.subjectStatusWord ?? null}
            economics={economics}
            actionNote={actionNote}
            busy={actionBusy}
            onPublish={() => void runGated("Publishing", "/publish", {})}
            onQuoteBook={() =>
              void runGated("Quote", "/book-orders", { book_format: "paperback", page_count: 200 })
            }
            onReleasePayout={(args) =>
              releasePayout(projectId, { ...args, adRevenueUsd: "0" })
            }
          />
        ) : (
          <>
            {/* 1 · Invite by link */}
            <section className="mb-5 rounded-md border-2 border-ink bg-ice-0 p-4 shadow-z1 dark:border-charcoal-1 dark:bg-charcoal-1 dark:shadow-z1-night">
              <h2 className="font-serif text-[16px] text-ink dark:text-bright">
                Invite the people who knew them
              </h2>
              <p className="mt-0.5 font-serif text-[13px] text-ink-mute dark:text-moonlight">
                Share one link. Anyone who has it can record their memories —
                in their own voice, on their own time. No account needed.
              </p>
              {shareLink ? (
                <div className="mt-3 flex items-center gap-2">
                  <code className="min-w-0 flex-1 truncate rounded border border-rule bg-ice-1 px-2 py-1.5 text-[12px] text-ink dark:border-charcoal-1 dark:bg-charcoal-2 dark:text-bright">
                    {shareLink}
                  </code>
                  <LemonButton variant="primary" size="sm" onClick={copyLink}>
                    {copied ? "Copied" : "Copy link"}
                  </LemonButton>
                </div>
              ) : (
                <div className="mt-3">
                  <LemonButton variant="primary" size="sm" onClick={() => void ensureShareLink()}>
                    Get a shareable link
                  </LemonButton>
                </div>
              )}
              <details className="mt-3">
                <summary className="cursor-pointer font-mono text-[11px] text-ink-mute hover:text-ink dark:text-moonlight dark:hover:text-bright">
                  or invite someone by email
                </summary>
                <div className="mt-2">
                  <Invites
                    projectTitle={project?.name ?? "this story"}
                    publishIntent={
                      project?.willBePublic ? "will_be_public" : "private_never_published"
                    }
                    invites={voices.map((v) => ({
                      interviewId: v.interviewId,
                      email: v.who,
                      handle: null,
                      status:
                        v.state === "recording"
                          ? "in_progress"
                          : v.state === "shared"
                          ? "completed"
                          : v.state === "declined"
                          ? "declined"
                          : v.state === "unfinished"
                          ? "incomplete"
                          : "invited",
                      link: v.link,
                      requiredScopes: ["record"],
                    }))}
                    onInvite={invite}
                  />
                </div>
              </details>
            </section>

            {/* 2 · Arriving voices */}
            <section className="mb-5">
              <h2 className="mb-2 font-mono text-[11px] font-semibold uppercase tracking-wider text-ink-mute dark:text-moonlight">
                Voices ({arrived.length})
              </h2>
              {voices.length === 0 ? (
                <p className="font-serif text-[13px] italic text-ink-mute dark:text-moonlight">
                  No voices yet. Share the link above — they'll appear here as
                  people record.
                </p>
              ) : (
                <ul className="space-y-1.5">
                  {voices.map((v) => (
                    <li
                      key={v.interviewId}
                      className="flex items-center justify-between gap-3 rounded border border-rule px-3 py-2 dark:border-charcoal-1"
                    >
                      <span className="min-w-0 truncate font-serif text-[14px] text-ink dark:text-bright">
                        {v.who}
                      </span>
                      <span className="shrink-0 font-mono text-[10px] uppercase tracking-wider text-ink-mute dark:text-moonlight">
                        {VOICE_STATE_LABELS[v.state]}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </section>

            {/* 3 · What everyone agrees on (corroboration — honest) */}
            <section className="mb-5">
              <div className="mb-2 flex items-center justify-between gap-2">
                <h2 className="font-mono text-[11px] font-semibold uppercase tracking-wider text-ink-mute dark:text-moonlight">
                  What everyone agrees on
                </h2>
                <LemonButton variant="tertiary" size="sm" onClick={() => void seeAgreement()}>
                  {agree.phase === "working" ? "Looking…" : "Refresh"}
                </LemonButton>
              </div>
              {agree.phase === "idle" && (
                <p className="font-serif text-[13px] italic text-ink-mute dark:text-moonlight">
                  Once a few people have shared, see where their memories line
                  up — and where they remember things differently.
                </p>
              )}
              {agree.phase === "working" && (
                <div className="py-1">
                  <WernerThinking size={28} label="Comparing the voices" />
                </div>
              )}
              {agree.phase === "failed" && (
                <AIActionFailure
                  title="We couldn't compare the voices"
                  onRetry={() => void seeAgreement()}
                />
              )}
              {agree.phase === "ready" &&
                (agree.points.length === 0 ? (
                  <p className="font-serif text-[13px] italic text-ink-mute dark:text-moonlight">
                    Nothing to compare yet — when two people mention the same
                    thing, it'll show up here.
                  </p>
                ) : (
                  <ul className="space-y-1.5">
                    {agree.points.map((pt, i) => (
                      <li
                        key={i}
                        className="rounded border border-rule px-3 py-2 dark:border-charcoal-1"
                      >
                        <p className="font-serif text-[14px] text-ink dark:text-bright">
                          {pt.text}
                        </p>
                        <p className="mt-0.5 font-mono text-[10px] uppercase tracking-wider text-ink-mute dark:text-moonlight">
                          {pt.kind === "corroborated"
                            ? `Corroborated · ${pt.voices} people independently remember this`
                            : pt.kind === "disagreement"
                            ? "People remember this differently — both kept"
                            : "One person so far"}
                        </p>
                      </li>
                    ))}
                  </ul>
                ))}
            </section>

            {/* 4 · The assembling story (creator-only) */}
            <section className="mb-2">
              <div className="mb-2 flex items-center justify-between gap-2">
                <h2 className="font-mono text-[11px] font-semibold uppercase tracking-wider text-ink-mute dark:text-moonlight">
                  Their story, so far
                </h2>
                <LemonButton
                  variant="secondary"
                  size="sm"
                  disabled={draft.phase === "assembling"}
                  onClick={() => void assemble()}
                >
                  {draft.phase === "ready" ? "Reassemble" : "Assemble the story"}
                </LemonButton>
              </div>
              <p className="mb-2 font-serif text-[12px] text-ink-mute dark:text-moonlight">
                Only you see this draft — each contributor only sees what they
                shared.
              </p>
              {draft.phase === "assembling" && (
                <div className="rounded-md border border-rule p-4 dark:border-charcoal-1">
                  <WernerThinking size={32} label="Assembling their story" />
                  <p className="mt-2 font-serif text-[13px] text-ink-mute dark:text-moonlight">
                    Drawing the story together from what everyone shared…
                  </p>
                </div>
              )}
              {draft.phase === "failed" && (
                <AIActionFailure
                  title="The story couldn't be assembled"
                  onRetry={() => void assemble()}
                  retryLabel="Try again"
                />
              )}
              {draft.phase === "ready" && (
                <div className="rounded-md border border-rule p-4 dark:border-charcoal-1">
                  <p className="whitespace-pre-wrap font-serif text-[14px] leading-relaxed text-ink dark:text-bright">
                    {draft.draft.prose || "It's still thin — invite a few more voices and try again."}
                  </p>
                  {draft.draft.excludedCount > 0 && (
                    <p className="mt-2 font-serif text-[12px] text-ink-mute dark:text-moonlight">
                      {draft.draft.excludedCount} memory
                      {draft.draft.excludedCount === 1 ? " was" : "ies were"} left
                      out — only one person mentioned them, or people disagreed,
                      so they aren't in the story yet.
                    </p>
                  )}
                </div>
              )}
            </section>
          </>
        )}
      </div>
    </GlassSurface>
  );
}
