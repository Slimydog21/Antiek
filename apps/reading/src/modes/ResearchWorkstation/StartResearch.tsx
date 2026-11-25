import { useCallback, useRef, useState } from "react";

import { cardLift } from "../../design/motion";
import GlassSurface from "../../shell/GlassSurface";
import LemonButton from "../../components/lemon/LemonButton";
import LemonTextarea from "../../components/lemon/LemonTextarea";
import LemonSelect from "../../components/lemon/LemonSelect";
import Thinking from "../../shared/Thinking";
import AIActionFailure from "../../shared/AIActionFailure";
import { ErrorState } from "../../components/states";
import { CelebrateBurst } from "../../shared/delight";
import type { ResearchSourcePolicy, ResearchTier } from "../../lib/api";
import { modelKey, URL_RE, useProjectIntake } from "../Home/useProjectIntake";
import CascadeProposal from "./CascadeProposal";
import MyResearch from "./MyResearch";
import VoiceChaseButton from "./VoiceChaseButton";

/**
 * StartResearch — the Research HOME (S5 redesign fix → Living-Roadmap SPR-05).
 *
 * Replaces the old static prose EmptyState, which described how to start
 * an investigation but gave the operator no way to actually do it (the
 * real composer only mounted once an `investigationId` existed, so a
 * fresh `/` was a dead end).
 *
 * This surface is the one-click entry: an autofocused composer, a visible
 * **Ask** button (click OR ⌘/Ctrl+Enter), three clickable example pills,
 * and — Living-Roadmap SPR-05 M1 — a VOICE button and an ATTACH affordance
 * (text + voice + attachments are the three home inputs the sprint asks for).
 *
 * SPR-05 M3 — log-as-home. Per the operator's "the research home IS the
 * research log" decision, when this surface is IDLE (nothing started yet,
 * not in cascade mode) it renders the composer at the TOP and the MyResearch
 * LOG below it, so "My Research" is folded INTO the workstation home rather
 * than living as a separate competing tab. Clicking a project row in the log
 * navigates to that project's workstation (/inv/{id}, via MyResearch's own
 * row links — unchanged). This is the consolidation: one home, composer +
 * log together. The active states (started / cascade / failed) take over the
 * whole surface as before — the log is an IDLE-only companion.
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
 *
 * § VOICE (SPR-05 M1, §5 voice discipline): the mic reuses the SHIPPED
 * VoiceChaseButton (apps/reading/src/modes/ResearchWorkstation/VoiceChaseButton.tsx),
 * which records via useVoiceRecorder + transcribes via the live
 * /voice/transcribe route — no new recorder is invented. On the home there
 * is no investigation yet, so the transcript only FILLS the prompt text; the
 * §9 user-sourcing is pinned downstream when the run starts (the start path
 * records the human-authored question). A transcription failure / mic-denied
 * surfaces VoiceChaseButton's own honest AIActionFailure — never a
 * hallucinated transcript silently dropped into the prompt.
 *
 * § ATTACH (SPR-05 M1): reuses PasteIngest's ingest API calls — ingestSource
 * for a URL, ingestVoiceNote for pasted text / a text file — WITHOUT an
 * investigation_id (none exists on the home; the document lands in the corpus
 * and is reachable by the run). Attachment-only with an empty prompt is
 * ACCEPTED (operator decision) with a DERIVED prompt ("Understand and distill
 * …"), not blocked. A failed/rejected ingest is surfaced, never silent.
 */

const EXAMPLE_PROMPTS: readonly string[] = [
  "What's the strongest case against this thesis, and what evidence would change my mind?",
  "Trace how this idea evolved across the sources in my substrate.",
  "Where do these authors disagree, and which side has the better-grounded claims?",
];

const RESEARCH_TIER_OPTIONS: ReadonlyArray<{ value: ResearchTier; label: string; hint: string }> = [
  { value: "fast", label: "Fast", hint: "lower-latency established route" },
  { value: "deep", label: "Deep", hint: "reasoning-heavier established route" },
];

const SOURCE_POLICY_OPTIONS: ReadonlyArray<{
  value: ResearchSourcePolicy;
  label: string;
  hint: string;
}> = [
  { value: "operator_corpus", label: "Corpus", hint: "your imported notes, books, and saved sources" },
  { value: "web", label: "Web", hint: "public web discovery when the runner supports it" },
  { value: "arxiv", label: "arXiv", hint: "papers and preprints" },
  { value: "substack", label: "Substack", hint: "newsletter feeds and essays" },
];

export default function StartResearch({ embedded = false }: { embedded?: boolean }) {
  // FFX-KPA SPR-03 M1: the intake machine (prompt, voice, URL / text-file
  // attach, derived prompt, tier / sources / owner model, submit, the
  // research-starts beat and the navigate grace) lives in useProjectIntake so
  // the zen home shares it. This component keeps the cascade toggle and the
  // markup.
  const intake = useProjectIntake();
  const {
    start,
    navigate,
    composerRef: taRef,
    question,
    setQuestion,
    promptDerived,
    setPromptDerived,
    tier,
    setTier,
    sourcePolicy,
    toggleSourcePolicy,
    models,
    modelsState,
    modelChoice,
    setModelChoice,
    selectedModel,
    selectModel,
    refreshModels,
    attach,
    setAttach,
    absorbUrl,
    handleFile,
    applyTranscript: onVoiceTranscript,
    fillExample,
    onSubmit,
    onTryAgain,
    celebrating,
  } = intake;
  // Two entry actions on one composer: Ask (one-shot, the shipped fast lane,
  // default) and Break-into-sub-questions (cascade). Cascade swaps the
  // composer for the proposal surface IN PLACE — no navigation away (M1). The
  // problem text the user typed seeds the proposal.
  const [cascadeProblem, setCascadeProblem] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const {
    startedId,
    phase,
    events,
    liveCost,
    failed,
    failureReason,
    error,
    busy,
  } = start;

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
  }, [taRef]);

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
              the thinking brain behind it carries the ongoing state.
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
                single inline string), so we use Thinking for the brain
                mark and pass the live label through; the same accessible
                name (via BrainThinking) is preserved. */}
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

  // ── Idle state: the start-a-research composer + (M3) the research LOG. ──
  //
  // SPR-05 M3 (log-as-home): the IDLE home is the composer ABOVE the MyResearch
  // log. `embedded` lets the consolidated home (ResearchWorkstation idle branch)
  // present the composer top-aligned in a scroll column with the log beneath it,
  // instead of the legacy vertically-centred empty composer. When the surface is
  // mounted standalone (embedded=false, e.g. a unit test or a route that wants
  // only the composer) it keeps the centred layout and shows no log.
  return (
    <div
      className={
        embedded
          ? "h-full overflow-y-auto px-6 py-8"
          : "h-full flex items-center justify-center px-6"
      }
    >
      {/* AMS2-SPR-03 (M2 for /): the idle home is a LANDING surface (occlusion
          audit §3 item 1). The root scroll/centering container above stays
          background-free so the z-0 <Scene/> shows through the MARGINS around
          this centred column (that content-free margin is what the headline
          gate samples). The column itself becomes a GlassSurface (glass
          variant) so the bare heading + intro — which previously sat DIRECTLY
          over the moving scene with no backing — ride on the primitive's scrim
          and clear WCAG-AA 4.5:1 (rigor #1: never translucent where text
          breaks). Under reduced-motion / no-scene the primitive degrades to its
          identical opaque solid fallback (M4). Tokens are consumed via the
          primitive's Tailwind classes only; nothing here redefines a colour.
          The composer/pills/log keep their own bg-ice-0 cards inside. */}
      <GlassSurface
        variant="glass"
        className={
          (embedded ? "mx-auto w-full max-w-3xl" : "w-full max-w-xl") +
          " rounded-hog-lg px-6 py-7"
        }
      >
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
            onChange={(e) => {
              setQuestion(e.target.value);
              // The operator edited the prompt by hand → it is no longer the
              // auto-derived one, so drop the "derived" label (honesty).
              if (promptDerived) setPromptDerived(false);
            }}
            onSubmit={() => void onSubmit()}
            placeholder="What do you want to research?"
            autoFocus
            disabled={busy}
            minRows={3}
            maxRows={10}
            className="font-serif text-base leading-relaxed"
            aria-label="Research question"
          />

          {/* Derived-prompt honesty (SPR-05 M1): when an attachment-only
              submission auto-filled the prompt, say so plainly. The text is
              editable above; this only labels its provenance. */}
          {promptDerived && (
            <p
              className="text-xs font-mono text-ink-mute dark:text-moonlight"
              role="status"
            >
              Prompt suggested from your attachment — edit it or ask as is.
            </p>
          )}

          {/* SPR-05 M1 — voice + attach affordances. Voice reuses the shipped
              VoiceChaseButton (record → /voice/transcribe → fills the prompt;
              its own honest no-key / mic-denied state). Attach reuses
              PasteIngest's ingest calls (URL → ingestSource, text →
              ingestVoiceNote). Both sit BELOW the composer so they don't
              re-lay-out the SPR-12 shell. */}
          <div className="flex flex-wrap items-center gap-3">
            <VoiceChaseButton onTranscript={onVoiceTranscript} disabled={busy} />
            <LemonButton
              type="button"
              variant="tertiary"
              size="sm"
              disabled={busy || attach.kind === "absorbing"}
              onClick={() => fileInputRef.current?.click()}
            >
              {attach.kind === "absorbing" ? "Absorbing…" : "＋ Attach a file or link"}
            </LemonButton>
            <input
              ref={fileInputRef}
              type="file"
              className="hidden"
              aria-label="Attach a file"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) void handleFile(f);
                e.target.value = "";
              }}
            />
            <input
              type="url"
              placeholder="…or paste a link"
              aria-label="Attach a link"
              disabled={busy || attach.kind === "absorbing"}
              className="min-w-0 flex-1 rounded-hog border border-rule dark:border-charcoal-1 bg-ice-0 dark:bg-charcoal-2 px-2 py-1 text-xs font-mono text-ink dark:text-bright disabled:opacity-50"
              onKeyDown={(e) => {
                if (e.key !== "Enter") return;
                const v = (e.target as HTMLInputElement).value.trim();
                if (!URL_RE.test(v)) return;
                e.preventDefault();
                void absorbUrl(v);
                (e.target as HTMLInputElement).value = "";
              }}
            />
          </div>

          {/* Attach result — absorbed / rejected / failed, surfaced not silent
              (rigor #3). A failed ingest reuses the shared AIActionFailure. */}
          {attach.kind === "absorbed" && (
            <p className="text-xs font-mono text-success" role="status">
              Added “{attach.title}” to your corpus.
            </p>
          )}
          {attach.kind === "rejected" && (
            <p
              className="text-xs font-mono text-shadow-1 dark:text-moonlight"
              role="status"
            >
              {attach.why}
            </p>
          )}
          {attach.kind === "failed" && (
            <AIActionFailure
              title="Couldn’t absorb that"
              reason={attach.reason}
              onRetry={() => setAttach({ kind: "idle" })}
              retryLabel="Dismiss"
            />
          )}

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

          {/* A failed POST says what failed and what is safe; the raw
              "Submit failed: POST … HTTP 500" goes to Copy error details. A
              validation or capacity message is already a sentence for the
              reader, set in the interface face. */}
          {error &&
            (error.startsWith("Submit failed") ? (
              <ErrorState
                variant="inline"
                title="Couldn’t start the research"
                body="Your question is still here, so you can send it again."
                detail={error}
                onRetry={() => void onSubmit()}
              />
            ) : (
              <p className="text-sm text-danger">{error}</p>
            ))}

          <div className="rounded-hog border border-rule dark:border-charcoal-1 bg-ice-1/80 dark:bg-charcoal-1/40 p-3 space-y-2">
            <div className="flex flex-col sm:flex-row sm:items-center gap-2">
              <label className="text-xs font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight" id="research-model-label">
                Model for Ask
              </label>
              <LemonSelect
                value={modelChoice ? modelKey(modelChoice.provider_id, modelChoice.model_id) : "established"}
                onChange={(value) => value === "established" ? setModelChoice(null) : selectModel(value)}
                options={[{
                  value: "established",
                  label: `Established ${tier} route`,
                }, ...models.map((model) => ({
                  value: modelKey(model.id, model.model_id),
                  label: `${model.display_name} · ${model.model_id}`,
                }))]}
                placeholder={
                  modelsState === "loading"
                    ? "Checking executable models…"
                    : models.length === 0
                      ? "No executable model available"
                      : "Choose an executable model"
                }
                aria-label="Model for Ask investigation"
                fullWidth
              />
            </div>
            {modelsState === "error" ? (
              <p className="text-sm text-danger" role="alert">
                Can’t load executable models. Check Settings, then retry inventory.
              </p>
            ) : selectedModel ? (
              <div className="space-y-1" aria-live="polite">
                <p className="text-xs font-serif text-ink dark:text-bright">
                  Ask uses this model for the root investigation’s paid Loop One roles. Later chases choose their own route.
                </p>
                <p className="text-xxs font-mono text-ink-mute dark:text-moonlight break-all">
                  Pricing authority: {selectedModel.rate_snapshot ?? "server-verified executable route"}
                </p>
              </div>
            ) : (
              <p className="text-xs font-serif text-ink-mute dark:text-moonlight">
                Only routes the server reports as eligible and executable appear here.
              </p>
            )}
            {!modelChoice && (
              <div className="flex items-center gap-2" role="radiogroup" aria-label="Established research depth">
                {RESEARCH_TIER_OPTIONS.map((option) => (
                  <button key={option.value} type="button" role="radio" aria-checked={tier === option.value}
                    title={option.hint} onClick={() => setTier(option.value)}
                    className={`px-3 py-1 rounded-hog text-xs font-mono border border-rule ${tier === option.value ? "bg-sun text-ink" : "bg-ice-0 dark:bg-charcoal-2 text-ink dark:text-bright"}`}>
                    {option.label}
                  </button>
                ))}
              </div>
            )}
            {modelsState !== "loading" && (
              <button type="button" onClick={() => void refreshModels()} className="text-xs font-mono underline text-ink dark:text-bright">
                Retry inventory
              </button>
            )}
          </div>

          <div
            className="flex flex-col gap-2"
            role="group"
            aria-label="Source policy"
          >
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                Sources
              </span>
              {SOURCE_POLICY_OPTIONS.map((opt) => {
                const active = sourcePolicy.includes(opt.value);
                return (
                  <button
                    key={opt.value}
                    type="button"
                    aria-pressed={active}
                    onClick={() => toggleSourcePolicy(opt.value)}
                    disabled={busy}
                    title={opt.hint}
                    className={
                      "rounded-hog border px-2.5 py-1 text-xs font-mono transition-colors disabled:opacity-50 disabled:pointer-events-none " +
                      (active
                        ? "border-sun-deep bg-sun/15 text-ink dark:text-bright"
                        : "border-rule dark:border-charcoal-1 bg-ice-0 dark:bg-charcoal-2 text-ink-mute dark:text-moonlight hover:bg-sun/10")
                    }
                  >
                    {opt.label}
                  </button>
                );
              })}
            </div>
            <p className="text-xs font-serif text-ink-mute dark:text-moonlight">
              Recorded as source-pack intent for this research; connector
              execution still happens only inside the approved runner path.
            </p>
          </div>

          <div className="flex items-center justify-between gap-3">
            <div className="text-xs font-mono text-ink-mute dark:text-moonlight">
              <kbd className="border-2 border-ink dark:border-bright rounded px-1.5 text-xxs font-mono bg-ice-0 dark:bg-charcoal-1 shadow-z1 dark:shadow-z1-night mr-1.5">
                ⌘ ↵
              </kbd>
              to ask · charges follow the selected model’s server pricing authority
            </div>
            <div className="flex items-center gap-2">
              {/* SPR-05 M2 — the OPTIONAL "plan it first" path (operator
                  decision: plan-mode is NOT forced on every Ask). This breaks
                  the problem into focused sub-questions the operator EDITS and
                  APPROVES before launch, via the shipped cascade planner +
                  approval gate (CascadeProposal). Ask stays the fast one-shot
                  default so the proven lane is never gated behind a plan
                  (rigor #2). */}
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
                disabled={busy || question.trim().length < 3 || Boolean(modelChoice && !selectedModel)}
              >
                {busy ? "Starting…" : "Ask"}
              </LemonButton>
            </div>
          </div>
        </div>

        <div className="mt-7">
          <p className="text-xs font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight mb-2 text-center">
            Try one of these
          </p>
          <div className="flex flex-col gap-2">
            {EXAMPLE_PROMPTS.map((prompt) => (
              <div key={prompt} className="group">
                <button
                  type="button"
                  onClick={() => fillExample(prompt)}
                  disabled={busy}
                  className={
                    "w-full text-left text-sm font-serif text-ink dark:text-bright px-3 py-2 rounded-hog " +
                    "border-edge border-sun bg-ice-0 dark:bg-charcoal-2 shadow-z1 dark:shadow-z1-night " +
                    "hover:border-sun dark:hover:border-sun hover:bg-sun/10 disabled:opacity-50 disabled:pointer-events-none " +
                    cardLift
                  }
                >
                  {prompt}
                </button>
              </div>
            ))}
          </div>
        </div>

        {/* SPR-05 M3 — the research LOG, folded into the home. Only in the
            consolidated home (`embedded`), so a fresh `/` is the composer AND
            the scannable list of past/running projects (operator's
            "log-as-home"). MyResearch keeps its own row links to /inv/{id}, so
            clicking a project navigates to its workstation — the consolidation
            is presentational, the row-nav contract is unchanged. We pass
            `embedded` so MyResearch drops its now-redundant launch bar (the
            composer above IS the entry) and reads as a log section. */}
        {embedded && (
          <div className="mt-12 border-t border-rule dark:border-charcoal-1 pt-2">
            <MyResearch embedded />
          </div>
        )}
      </GlassSurface>
    </div>
  );
}
