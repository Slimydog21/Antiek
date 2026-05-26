import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import LemonButton from "../../components/lemon/LemonButton";
import LemonTextarea from "../../components/lemon/LemonTextarea";
import WernerThinking from "../../brand/werner/animated/WernerThinking";
import AIActionFailure from "../../shared/AIActionFailure";
import { useStartInvestigation } from "../../hooks/useStartInvestigation";

/**
 * StartResearch — the Research home's empty state (S5 redesign fix).
 *
 * Replaces the old static prose EmptyState, which described how to start
 * an investigation but gave the operator no way to actually do it (the
 * real composer only mounted once an `investigationId` existed, so a
 * fresh `/` was a dead end).
 *
 * This surface is the one-click entry: a centered, autofocused composer,
 * a visible **Ask** button (click OR ⌘/Ctrl+Enter), and three clickable
 * example pills that populate the input.
 *
 * Make the AI *felt*: the moment the POST returns an id, we attach the
 * REAL event stream (via useStartInvestigation → useEventStream) and show
 * a genuine connecting → streaming "thinking…" state with the live event
 * count and accumulated cost — never a silent `…`. Once the first real
 * events arrive (or a short grace elapses so a slow socket can't strand
 * the operator), we navigate to /inv/:id where InvestigationCenter's
 * TrajectoryView takes over the same live feed.
 *
 * The actual POST lives in `startInvestigation` (via the hook); nothing
 * here reimplements it. The submit semantics match ChatInputArea (>= 3
 * chars, ⌘/Ctrl+Enter).
 */

const EXAMPLE_PROMPTS: readonly string[] = [
  "What's the strongest case against this thesis, and what evidence would change my mind?",
  "Trace how this idea evolved across the sources in my substrate.",
  "Where do these authors disagree, and which side has the better-grounded claims?",
];

/** Cost line shared with ChatInputArea — kept in sync intentionally. */
const COST_ESTIMATE = "~$0.08-$0.16 / investigation";

/** Grace period before navigating even if no event has streamed yet, so a
 *  slow WS connection doesn't strand the operator on the start surface. */
const NAVIGATE_GRACE_MS = 1500;

export default function StartResearch() {
  const navigate = useNavigate();
  const start = useStartInvestigation();
  const [question, setQuestion] = useState("");
  const taRef = useRef<HTMLTextAreaElement>(null);

  const {
    startedId,
    phase,
    events,
    liveCost,
    failed,
    failureReason,
    error,
    busy,
    submit,
    reset,
  } = start;

  const onSubmit = useCallback(async () => {
    const id = await submit({ question });
    if (id) setQuestion("");
  }, [submit, question]);

  const fillExample = useCallback((prompt: string) => {
    setQuestion(prompt);
    taRef.current?.focus();
  }, []);

  // Try again after a failed run: tear the started id / stream down (which
  // clears the failure) and put the operator back on the composer. The
  // question was deliberately not cleared on failure, so it's still there to
  // re-submit; we just refocus it.
  const onTryAgain = useCallback(() => {
    reset();
    taRef.current?.focus();
  }, [reset]);

  // On failure, restore the question the operator typed so the run is
  // recoverable. (onSubmit clears it only on a successful POST; but the run
  // can fail *after* the POST returned an id, so we re-seed it here.)
  const lastQuestionRef = useRef("");
  useEffect(() => {
    if (question) lastQuestionRef.current = question;
  }, [question]);
  useEffect(() => {
    if (failed && !question && lastQuestionRef.current) {
      setQuestion(lastQuestionRef.current);
    }
  }, [failed, question]);

  // Once we have an id, route to the full investigation surface as soon as
  // real activity begins — or after a grace window if the socket is slow.
  // Either way the navigation is to the SAME live feed (TrajectoryView via
  // useInvestigation), so nothing is faked and no progress is lost.
  //
  // Failure-aware: if the run hit a terminal investigation.failed, we must
  // NOT navigate — /inv/:id would be a dead/empty surface. We suppress both
  // the event-driven navigate and the grace-timer navigate so the operator
  // stays on the start surface and sees the honest error below.
  useEffect(() => {
    if (!startedId) return;
    if (failed) return;
    if (events.length > 0) {
      navigate(`/inv/${startedId}`);
      return;
    }
    const t = window.setTimeout(() => {
      // Re-check at fire time: a failure event may have arrived during the
      // grace window. The effect re-runs on `failed` so this guard is belt-
      // and-suspenders, but it keeps the timer path honest regardless.
      if (!failed) navigate(`/inv/${startedId}`);
    }, NAVIGATE_GRACE_MS);
    return () => window.clearTimeout(t);
  }, [startedId, failed, events.length, navigate]);

  // ── Starting state: id returned, stream attached, run still progressing.
  //    A terminal failure falls through to the composer surface below, where
  //    we show an honest error and a Try-again action (never the dead
  //    /inv/:id route). ──
  if (startedId && !failed) {
    return (
      <div className="h-full flex items-center justify-center px-6">
        <div
          className="max-w-md w-full text-center"
          role="status"
          aria-live="polite"
        >
          <div className="flex items-center justify-center mb-4">
            <WernerThinking
              size={48}
              label={
                phase === "connecting"
                  ? "Connecting to the investigation"
                  : "The investigation is working"
              }
            />
          </div>
          <p className="text-base font-serif text-ink dark:text-bright mb-1">
            {phase === "connecting"
              ? "Starting your research…"
              : "Working on it…"}
          </p>
          <p className="text-xs font-mono text-ink-mute dark:text-moonlight">
            {phase === "connecting"
              ? "connecting to the live trajectory"
              : `${events.length} event${events.length === 1 ? "" : "s"} so far`}
            {" · "}${liveCost.toFixed(4)}
          </p>
        </div>
      </div>
    );
  }

  // ── Idle state: the start-a-research composer. ─────────────────────────
  return (
    <div className="h-full flex items-center justify-center px-6">
      <div className="w-full max-w-xl">
        <h1 className="text-2xl font-serif text-ink dark:text-bright mb-2 text-center">
          What do you want to research?
        </h1>
        <p className="text-sm text-shadow-1 dark:text-moonlight leading-relaxed font-serif text-center mb-6">
          Ask a question. The substrate runs a recursive note-taking chain
          across your corpus, distills insights and open questions, and
          renders a cited thesis. Highlight anything in the result to chase
          it further.
        </p>

        <div className="flex flex-col gap-3">
          <LemonTextarea
            ref={taRef}
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onSubmit={() => void onSubmit()}
            placeholder="What do you want to research?"
            autoFocus
            disabled={busy}
            minRows={3}
            maxRows={10}
            className="font-serif text-[15px] leading-relaxed"
            aria-label="Research question"
          />

          {failed && (
            // The presentational failure shell is now the shared
            // <AIActionFailure> (U-04) — same sentence across all four doors.
            // Start-flow specifics (re-seeding the question, refocusing, never
            // routing to the dead /inv/:id) stay in onTryAgain / the navigate
            // guard above; this component only renders + offers the retry.
            <AIActionFailure
              title="The research didn’t complete"
              reason={failureReason}
              onRetry={onTryAgain}
            />
          )}

          {error && (
            <div className="text-xs font-mono text-emperor">{error}</div>
          )}

          <div className="flex items-center justify-between gap-3">
            <div className="text-[11px] font-mono text-ink-mute dark:text-moonlight">
              <kbd className="border-2 border-ink dark:border-bright rounded px-1.5 text-[10px] font-mono bg-ice-0 dark:bg-charcoal-1 shadow-z1 dark:shadow-z1-night mr-1.5">
                ⌘ ↵
              </kbd>
              to submit · {COST_ESTIMATE}
            </div>
            <LemonButton
              variant="primary"
              size="lg"
              onClick={() => void onSubmit()}
              disabled={busy || question.trim().length < 3}
            >
              {busy ? "Starting…" : "Ask"}
            </LemonButton>
          </div>
        </div>

        <div className="mt-7">
          <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight mb-2 text-center">
            Try one of these
          </p>
          <div className="flex flex-col gap-2">
            {EXAMPLE_PROMPTS.map((prompt) => (
              <button
                key={prompt}
                type="button"
                onClick={() => fillExample(prompt)}
                disabled={busy}
                className="text-left text-[13px] font-serif text-ink dark:text-bright px-3 py-2 rounded-hog border border-rule dark:border-charcoal-1 bg-ice-0 dark:bg-charcoal-2 hover:border-sun dark:hover:border-sun hover:bg-sun/10 transition-colors disabled:opacity-50 disabled:pointer-events-none"
              >
                {prompt}
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
