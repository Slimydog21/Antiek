import { useCallback, useState } from "react";
import { useNavigate } from "react-router-dom";

import Werner from "../../brand/Werner";
import { LemonButton } from "../../components/lemon";
import { startInvestigation } from "../../lib/api";
import {
  createBiography,
  makeShareLink,
  type BiographyComposition,
} from "../../lib/speakApi";
import AIActionFailure from "../../shared/AIActionFailure";

/**
 * Biography — the dedicated landing for the biography TEMPLATE (SPR-11).
 *
 * A biography is NOT a fifth product and NOT a fifth graph. It is a template
 * that composes the three surfaces you already have — research, writing, and
 * gathered voices — over the one shared workspace. "Start a biography"
 * provisions all three at once, each linked to the same place, so the research
 * you do, the draft you write, and the voices you collect feed each other.
 *
 * This page is reachable from the home (the "Start a biography" feature card),
 * NOT from the four-door rail — a fifth door would imply a fifth product, which
 * is exactly the template-not-silo decision this sprint is built to hold (see
 * docs/decisions/spr-11-biography-template-not-graph.md).
 *
 * Two phases on one route:
 *   M1 — the explainer + the start form (name someone → start their biography);
 *   M3 — once started, a guided first-run: the three places it set up, the
 *        next steps, and a one-tap "send to a friend" to gather a voice.
 *
 * §5 voice discipline: the copy is crafted prose in the product's own register
 * — no slop, no substrate jargon (the copy-lint scans this file). The landing
 * copy is asserted by a render test (Biography.test.tsx), not just by eye.
 */
export default function Biography() {
  const navigate = useNavigate();

  const [name, setName] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [failed, setFailed] = useState(false);
  const [composed, setComposed] = useState<BiographyComposition | null>(null);

  // Start a biography: provision the three surfaces over the ONE graph.
  //   1. the Research folder — startInvestigation → investigation_id (the
  //      shared identity everything threads on);
  //   2. createBiography wires the Write deliverable + the Speak project to
  //      that same Research folder and records the shared composition link.
  // The CTA creates the biography PROJECT (this composition), never a bare
  // Write document.
  const start = useCallback(async () => {
    const trimmed = name.trim();
    if (!trimmed) return;
    setSubmitting(true);
    setFailed(false);
    try {
      const research = await startInvestigation({
        question: `The life and story of ${trimmed}.`,
        context:
          "A biography: gather what is known, written, and remembered about this person.",
      });
      const comp = await createBiography({
        investigationId: research.investigation_id,
        subjectName: trimmed,
      });
      setComposed(comp);
    } catch {
      setFailed(true);
    } finally {
      setSubmitting(false);
    }
  }, [name]);

  if (composed) {
    return (
      <BiographyOnboarding
        subjectName={name.trim()}
        composition={composed}
        onOpenResearch={() => navigate(`/inv/${composed.investigationId}`)}
        onOpenWrite={() => navigate(`/write/${composed.deliverableId}`)}
        onOpenSpeak={() => navigate(`/speak/${composed.projectId}`)}
      />
    );
  }

  return (
    <div className="h-full overflow-y-auto bg-ice-2 dark:bg-space-2">
      <div className="mx-auto max-w-2xl px-6 py-12">
        <header className="mb-8 space-y-3">
          <div className="flex items-start gap-3">
            <span data-testid="biography-werner-brand">
              <Werner mood="thinking" size={52} label="Biography" />
            </span>
            <div>
              <h1 className="font-serif text-3xl font-semibold text-ink dark:text-bright">
                Write someone&rsquo;s biography
              </h1>
              <p className="mt-2 font-serif text-[15px] leading-relaxed text-shadow-1 dark:text-moonlight">
                A biography brings together everything you can find, write, and
                remember about a person — in one place, so each part feeds the
                others. Name someone to begin.
              </p>
            </div>
          </div>
        </header>

        {/* The steps — what "start a biography" actually sets up. Three
            surfaces over the one workspace, not three separate places. */}
        <ol
          data-testid="biography-steps"
          className="mb-8 space-y-3"
          aria-label="How a biography comes together"
        >
          <Step
            n={1}
            title="Gather what is known"
            body="We open a research folder for the person, so anything you find — records, articles, your own notes — gathers in one place."
          />
          <Step
            n={2}
            title="Invite the people who knew them"
            body="Send a link to friends and family. Each shares a memory in their own words, on their own time, and their voices come together into the story."
          />
          <Step
            n={3}
            title="Write it together"
            body="A draft starts from what everyone gathered and remembered, cited to who said what, so the story is theirs — not invented."
          />
        </ol>

        <form
          onSubmit={(e) => {
            e.preventDefault();
            void start();
          }}
          className="mb-6 flex flex-wrap items-center gap-2 rounded-md border-2 border-ink bg-ice-0 p-3 shadow-z1 dark:border-charcoal-1 dark:bg-charcoal-1 dark:shadow-z1-night"
        >
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="A name — e.g. my grandmother, Dad, Maria"
            aria-label="Whose biography do you want to write?"
            className="min-w-[220px] flex-1 rounded border border-rule bg-transparent px-3 py-2 font-serif text-[15px] text-ink focus:outline-none focus:ring-2 focus:ring-sun dark:border-charcoal-1 dark:text-bright"
          />
          <LemonButton
            type="submit"
            variant="primary"
            disabled={submitting || !name.trim()}
          >
            {submitting ? "Setting it up…" : "Start a biography"}
          </LemonButton>
        </form>

        {failed && (
          <AIActionFailure
            title="We couldn't start that biography"
            onRetry={() => void start()}
            retryLabel="Try again"
          />
        )}
      </div>
    </div>
  );
}

function Step({ n, title, body }: { n: number; title: string; body: string }) {
  return (
    <li className="flex items-start gap-3 rounded-md border border-rule bg-ice-0 p-3 dark:border-charcoal-1 dark:bg-charcoal-1">
      <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full border-2 border-ink bg-sun font-mono text-[12px] font-semibold text-ink">
        {n}
      </span>
      <div>
        <p className="font-serif text-[15px] font-semibold text-ink dark:text-bright">
          {title}
        </p>
        <p className="mt-0.5 font-serif text-[13.5px] leading-relaxed text-shadow-1 dark:text-moonlight">
          {body}
        </p>
      </div>
    </li>
  );
}

/**
 * The guided first-run (M3). Once a biography is started, walk the creator
 * through what was set up and the next steps, and offer a one-tap "send to a
 * friend" invite. The share link drops the RECIPIENT (no account needed) into
 * the Speak talk flow for THIS biography's project (modes/SpeakInvite, reused
 * from SPR-10) — so a captured memory feeds the biography's shared graph, not a
 * side store. (Distinct surface from the creator's own "Open it" Speak button
 * below, which opens the project console at /speak/:projectId.)
 */
function BiographyOnboarding({
  subjectName,
  composition,
  onOpenResearch,
  onOpenWrite,
  onOpenSpeak,
}: {
  subjectName: string;
  composition: BiographyComposition;
  onOpenResearch: () => void;
  onOpenWrite: () => void;
  onOpenSpeak: () => void;
}) {
  const [inviteLink, setInviteLink] = useState<string | null>(null);
  const [inviting, setInviting] = useState(false);
  const [inviteFailed, setInviteFailed] = useState(false);
  const [copied, setCopied] = useState(false);

  const who = subjectName || "this person";

  const sendToAFriend = useCallback(async () => {
    setInviting(true);
    setInviteFailed(false);
    try {
      const link = await makeShareLink(composition.projectId);
      setInviteLink(link);
    } catch {
      setInviteFailed(true);
    } finally {
      setInviting(false);
    }
  }, [composition.projectId]);

  const copyLink = useCallback(async () => {
    if (!inviteLink) return;
    try {
      await navigator.clipboard?.writeText(inviteLink);
      setCopied(true);
    } catch {
      /* the link is shown inline regardless — copy is a convenience */
    }
  }, [inviteLink]);

  return (
    <div className="h-full overflow-y-auto bg-ice-2 dark:bg-space-2">
      <div className="mx-auto max-w-2xl px-6 py-12">
        <header className="mb-7 flex items-start gap-3">
          <Werner mood="celebrate" size={52} label="" />
          <div>
            <h1 className="font-serif text-3xl font-semibold text-ink dark:text-bright">
              {who}&rsquo;s biography is started
            </h1>
            <p className="mt-2 font-serif text-[15px] leading-relaxed text-shadow-1 dark:text-moonlight">
              Everything for {who} now lives in one place. Here&rsquo;s what was
              set up, and where to go next.
            </p>
          </div>
        </header>

        {/* The three surfaces this biography composes — each one click away,
            all over the same workspace. */}
        <section
          aria-label="What was set up"
          data-testid="biography-surfaces"
          className="mb-8 space-y-3"
        >
          <SurfaceCard
            testid="biography-open-research"
            title="A place to gather what is known"
            body="Your research folder. Empty for now — add records, articles, or notes whenever you like."
            cta="Open it"
            onClick={onOpenResearch}
          />
          <SurfaceCard
            testid="biography-open-write"
            title="A draft of the story"
            body="It fills in from what you gather and what people share. Nothing is invented; every line is traceable to who said it."
            cta="Open it"
            onClick={onOpenWrite}
          />
          <SurfaceCard
            testid="biography-open-speak"
            title="The voices of the people who knew them"
            body="No voices yet. Invite friends and family below — each shares a memory in their own words."
            cta="Open it"
            onClick={onOpenSpeak}
          />
        </section>

        {/* "Send to a friend" — the one-tap invite (M3). Generates a link
            that drops the recipient into the Speak talk flow for THIS
            biography, so a captured memory feeds its shared graph. */}
        <section
          aria-label="Invite someone to share a memory"
          data-testid="biography-invite"
          className="rounded-md border-2 border-ink bg-sun/10 p-5 shadow-z1 dark:border-charcoal-1 dark:bg-sun/5 dark:shadow-z1-night"
        >
          <h2 className="font-serif text-lg font-semibold text-ink dark:text-bright">
            Invite someone to share a memory
          </h2>
          <p className="mt-1 font-serif text-[13.5px] leading-relaxed text-shadow-1 dark:text-moonlight">
            Get a link to send a friend or family member. They tap it, record a
            memory of {who} in their own words, and it joins the story. They
            don&rsquo;t need an account.
          </p>

          {inviteLink ? (
            <div className="mt-4">
              <p className="font-serif text-[13px] text-ink dark:text-bright">
                Share this link with someone who knew {who}:
              </p>
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <code className="min-w-0 flex-1 truncate rounded border border-rule bg-ice-0 px-2 py-1 text-[12px] text-ink dark:border-charcoal-1 dark:bg-charcoal-2 dark:text-bright">
                  {inviteLink}
                </code>
                <LemonButton variant="secondary" size="sm" onClick={() => void copyLink()}>
                  {copied ? "Copied" : "Copy link"}
                </LemonButton>
              </div>
            </div>
          ) : (
            <div className="mt-4">
              <LemonButton
                variant="primary"
                onClick={() => void sendToAFriend()}
                disabled={inviting}
              >
                {inviting ? "Getting a link…" : "Send to a friend"}
              </LemonButton>
            </div>
          )}

          {inviteFailed && (
            <div className="mt-4">
              <AIActionFailure
                title="We couldn't make an invite link"
                onRetry={() => void sendToAFriend()}
                retryLabel="Try again"
              />
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

function SurfaceCard({
  testid,
  title,
  body,
  cta,
  onClick,
}: {
  testid: string;
  title: string;
  body: string;
  cta: string;
  onClick: () => void;
}) {
  return (
    <div className="flex items-start justify-between gap-3 rounded-md border border-rule bg-ice-0 p-4 dark:border-charcoal-1 dark:bg-charcoal-1">
      <div className="min-w-0">
        <p className="font-serif text-[15px] font-semibold text-ink dark:text-bright">
          {title}
        </p>
        <p className="mt-0.5 font-serif text-[13.5px] leading-relaxed text-shadow-1 dark:text-moonlight">
          {body}
        </p>
      </div>
      <button
        type="button"
        data-testid={testid}
        onClick={onClick}
        className="mt-0.5 shrink-0 rounded border-2 border-ink bg-ice-0 px-3 py-1.5 font-mono text-[12px] font-semibold text-ink shadow-z1 hover:-translate-y-0.5 dark:bg-charcoal-2 dark:text-bright dark:shadow-z1-night"
      >
        {cta}
      </button>
    </div>
  );
}
