import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import LemonButton from "../../components/lemon/LemonButton";
import LemonTextarea from "../../components/lemon/LemonTextarea";
import Thinking from "../../shared/Thinking";
import AIActionFailure from "../../shared/AIActionFailure";
import { CelebrateBurst, useCelebrate } from "../../shared/delight";
import { useStartInvestigation } from "../../hooks/useStartInvestigation";
import type { ResearchTier } from "../../lib/api";
import CascadeProposal from "./CascadeProposal";

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

/**
 * SPR-01 M3 — the curated research tiers. This is the WHOLE set the entry
 * offers: two values, no raw model dropdown, no BYO-model. The label +
 * one-line "what it's for" are the operator-facing framing; the tier→provider
 * map ("fast" → MiMo V2.5 Pro, "deep" → DeepSeek V4 Pro) lives server-side in
 * substrate/dispatch/research_tier.py and is never exposed to the client.
 * Default is "deep" (mirrors DEFAULT_RESEARCH_TIER): a cold research question
 * is the high-value case; the operator opts DOWN to fast for cheap asks.
 */
const RESEARCH_TIER_OPTIONS: ReadonlyArray<{
  value: ResearchTier;
  label: string;
  hint: string;
}> = [
  { value: "fast", label: "Fast", hint: "cheaper, lower-latency" },
  { value: "deep", label: "Deep", hint: "reasoning-heavier" },
];
const DEFAULT_TIER: ResearchTier = "deep";

/** Grace period before navigating even if no event has streamed yet, so a
 *  slow WS connection doesn't strand the operator on the start surface. */
const NAVIGATE_GRACE_MS = 1500;

export default function StartResearch() {
  const navigate = useNavigate();
  const start = useStartInvestigation();
  const [question, setQuestion] = useState("");
  // SPR-01 M3: the curated fast/deep tier. Closed set; defaults to deep.
  // Recorded on the investigation server-side so it's queryable after.
  const [tier, setTier] = useState<ResearchTier>(DEFAULT_TIER);
  // Two entry actions on one composer: Ask (one-shot, the shipped fast lane,
  // default) and Break-into-sub-questions (cascade). Cascade swaps the
  // composer for the proposal surface IN PLACE — no navigation away (M1). The
  // problem text the user typed seeds the proposal.
  const [cascadeProblem, setCascadeProblem] = useState<string | null>(null);
  const taRef = useRef<HTMLTextAreaElement>(null);
  // The research-starts signature beat (U-05 M2) — Werner's one-shot
  // celebrate the moment a research is genuinely under way. Non-blocking:
  // it only arms a timer; navigation + the live banner below are driven by
  // their own effects and don't wait on it.
  const { celebrating, celebrate } = useCelebrate();

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
    const id = await submit({ question, researchTier: tier });
    if (id) setQuestion("");
  }, [submit, question, tier]);

  const fillExample = useCallback((prompt: string) => {
    setQuestion(prompt);
    taRef.current?.focus();
  }, []);

  // Enter cascade mode with the typed problem space. Same >= 3-char floor as
  // Ask so an empty composer can't propose an empty plan.
  const onBreakDown = useCallback(() => {
    const q = question.trim();
    if (q.length < 3) return;
    setCascadeProblem(q);
  }, [question]);

  // Back out of cascade (the proposal couldn't split it, or the user chose
  // one question instead): keep the typed problem so Ask is one click away.
  const onCascadeFallBack = useCallback(() => {
    setCascadeProblem(null);
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

  // Fire the research-starts beat exactly once, at the transition into the
  // started-and-not-failed state (an id is back, the run is live). It's
  // independent of the navigate effect below: `celebrate()` returns
  // immediately, so the beat never sits between "research is under way" and
  // the operator seeing it. A failed run never celebrates.
  const startedAndLive = Boolean(startedId) && !failed;
  const celebratedRef = useRef(false);
  useEffect(() => {
    if (startedAndLive && !celebratedRef.current) {
      celebratedRef.current = true;
      celebrate();
    }
    if (!startedId) celebratedRef.current = false; // re-arm after reset
  }, [startedAndLive, startedId, celebrate]);

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
          {/* The beat sits above the working mark and retires on its own;
              the thinking penguin behind it carries the ongoing state.
              pointer-events-none + absolute so it can't gate the surface. */}
          <div className="relative flex items-center justify-center mb-4">
            {celebrating && (
              <CelebrateBurst
                active
                size={48}
                className="absolute inset-0 items-center justify-center"
              />
            )}
            {/* The shared <Thinking> (U-04 M3) — the same "AI is working"
                beat Research, Read, Write, and Speak draw from. Research's
                live status is the two centered lines below (richer than a
                single inline string), so we use Thinking for the penguin
                mark and pass the live label through; the same accessible
                name (via WernerThinking) is preserved. */}
            <Thinking
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

  // ── Cascade mode: the AI proposes sub-questions, the user trims, then
  //    launches N parallel researches. Stays on this surface (no navigation
  //    away) until launch hands a session to the monitor. ──
  if (cascadeProblem) {
    return (
      <div className="h-full flex items-center justify-center px-6">
        <div className="w-full max-w-xl">
          <h1 className="text-2xl font-serif text-ink dark:text-bright mb-1 text-center">
            Breaking this into sub-questions
          </h1>
          <p className="text-sm text-shadow-1 dark:text-moonlight font-serif text-center mb-4">
            {cascadeProblem}
          </p>
          <CascadeProposal
            problem={cascadeProblem}
            onLaunched={(sessionId) => navigate(`/deep-research/${sessionId}`)}
            onFallBackToAsk={onCascadeFallBack}
          />
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

          {/* SPR-01 M3 — the curated fast/deep tier selector. A closed
              two-value segmented control (NOT a model dropdown). Selecting
              a tier changes which provider Hermes routes to server-side
              ("fast" → MiMo V2.5 Pro, "deep" → DeepSeek V4 Pro); the chosen
              value rides on the start request and is recorded on the
              investigation. Lives ONLY here, at the research entry. */}
          <div
            className="flex items-center gap-2"
            role="radiogroup"
            aria-label="Research depth"
          >
            <span className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
              Depth
            </span>
            <div className="inline-flex rounded-hog border border-rule dark:border-charcoal-1 overflow-hidden">
              {RESEARCH_TIER_OPTIONS.map((opt) => {
                const active = tier === opt.value;
                return (
                  <button
                    key={opt.value}
                    type="button"
                    role="radio"
                    aria-checked={active}
                    onClick={() => setTier(opt.value)}
                    disabled={busy}
                    title={opt.hint}
                    className={
                      "px-3 py-1 text-[12px] font-mono transition-colors disabled:opacity-50 disabled:pointer-events-none " +
                      (active
                        ? "bg-sun text-ink"
                        : "bg-ice-0 dark:bg-charcoal-2 text-ink dark:text-bright hover:bg-sun/10")
                    }
                  >
                    {opt.label}
                  </button>
                );
              })}
            </div>
            <span className="text-[11px] font-serif text-ink-mute dark:text-moonlight">
              {RESEARCH_TIER_OPTIONS.find((o) => o.value === tier)?.hint}
            </span>
          </div>

          <div className="flex items-center justify-between gap-3">
            <div className="text-[11px] font-mono text-ink-mute dark:text-moonlight">
              <kbd className="border-2 border-ink dark:border-bright rounded px-1.5 text-[10px] font-mono bg-ice-0 dark:bg-charcoal-1 shadow-z1 dark:shadow-z1-night mr-1.5">
                ⌘ ↵
              </kbd>
              to ask · {COST_ESTIMATE}
            </div>
            <div className="flex items-center gap-2">
              {/* The second mode: break the problem space into focused
                  sub-questions and run them in parallel. Secondary to Ask so
                  the proven fast lane stays the default (rigor #2). */}
              <LemonButton
                variant="secondary"
                size="lg"
                onClick={onBreakDown}
                disabled={busy || question.trim().length < 3}
              >
                Break into sub-questions
              </LemonButton>
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
