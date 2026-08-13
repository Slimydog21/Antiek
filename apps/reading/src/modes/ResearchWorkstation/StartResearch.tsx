import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { cardLift } from "../../design/motion";
import GlassSurface from "../../shell/GlassSurface";
import LemonButton from "../../components/lemon/LemonButton";
import LemonTextarea from "../../components/lemon/LemonTextarea";
import LemonSelect from "../../components/lemon/LemonSelect";
import Thinking from "../../shared/Thinking";
import AIActionFailure from "../../shared/AIActionFailure";
import { CelebrateBurst, useCelebrate } from "../../shared/delight";
import { useStartInvestigation } from "../../hooks/useStartInvestigation";
import { ApiError, ingestSource, ingestVoiceNote } from "../../lib/api";
import type { ResearchTier, UserModelChoice } from "../../lib/api";
import { fetchUserModels, type UserModelRow } from "../../api/settingsModels";
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

const OWNER_LAUNCH_KEY = "antiek.research.pending-owner-launch.session.v1";
const modelKey = (providerId: string, modelId: string) => `${providerId}\u0000${modelId}`;
const isExecutable = (model: UserModelRow) =>
  model.enabled && model.key_present && model.registered && model.route_eligible &&
  model.pricing_status === "known" && model.hard_ceiling_eligible &&
  model.execution_status === "executable";

const RESEARCH_TIER_OPTIONS: ReadonlyArray<{ value: ResearchTier; label: string; hint: string }> = [
  { value: "fast", label: "Fast", hint: "lower-latency established route" },
  { value: "deep", label: "Deep", hint: "reasoning-heavier established route" },
];

interface PendingOwnerLaunch {
  question: string;
  modelChoice: UserModelChoice;
  operationId: string;
}

function readPendingOwnerLaunch(): PendingOwnerLaunch | null {
  try {
    const raw = window.sessionStorage.getItem(OWNER_LAUNCH_KEY);
    if (!raw) return null;
    const value = JSON.parse(raw) as Partial<PendingOwnerLaunch>;
    if (
      typeof value.question !== "string" ||
      typeof value.operationId !== "string" ||
      value.operationId.length === 0 ||
      value.modelChoice?.authority !== "user_model" ||
      typeof value.modelChoice.provider_id !== "string" ||
      typeof value.modelChoice.model_id !== "string"
    ) return null;
    return value as PendingOwnerLaunch;
  } catch {
    return null;
  }
}

/** Grace period before navigating even if no event has streamed yet, so a
 *  slow WS connection doesn't strand the operator on the start surface. */
const NAVIGATE_GRACE_MS = 1500;

/** SPR-05 M1 — match PasteIngest's URL test so the home routes a pasted/typed
 *  link to ingestSource and any other text to ingestVoiceNote, the same split
 *  PasteIngest uses. Kept identical on purpose (PasteIngest.tsx:120). */
const URL_RE = /^https?:\/\/\S+$/i;
/** Text-file extensions the browser can read as text (mirror of
 *  PasteIngest.TEXT_EXTENSIONS). A binary blob is rejected honestly. */
const TEXT_EXTENSIONS = /\.(txt|md|markdown|csv|json|log|rtf)$/i;

/** SPR-05 M1 (operator decision) — attachment-only with an EMPTY prompt is
 *  accepted with a sensible DERIVED prompt rather than blocked. The derived
 *  prompt is shown in the composer (editable) so it is never silently chosen
 *  behind the operator's back, and labelled in the UI as derived. */
function derivePromptFor(title: string): string {
  const t = title.trim();
  return t
    ? `Understand and distill “${t}”, and surface its key claims and open questions.`
    : "Understand and distill the attached material, and surface its key claims and open questions.";
}

/** What an attach attempt produced. Mirrors PasteIngest's Outcome shape but
 *  scoped to the home (no investigation yet). */
type AttachState =
  | { kind: "idle" }
  | { kind: "absorbing" }
  | { kind: "absorbed"; title: string }
  | { kind: "rejected"; why: string }
  | { kind: "failed"; reason: string | null };

export default function StartResearch({ embedded = false }: { embedded?: boolean }) {
  const navigate = useNavigate();
  const start = useStartInvestigation();
  const restoredLaunch = useMemo(readPendingOwnerLaunch, []);
  const [question, setQuestion] = useState(restoredLaunch?.question ?? "");
  const [tier, setTier] = useState<ResearchTier>("deep");
  const [models, setModels] = useState<UserModelRow[]>([]);
  const [modelsState, setModelsState] = useState<"loading" | "ready" | "error">("loading");
  const [modelChoice, setModelChoice] = useState<UserModelChoice | null>(
    restoredLaunch?.modelChoice ?? null,
  );
  const [operationId, setOperationId] = useState(
    restoredLaunch?.operationId ?? `research-${crypto.randomUUID()}`,
  );
  // Two entry actions on one composer: Ask (one-shot, the shipped fast lane,
  // default) and Break-into-sub-questions (cascade). Cascade swaps the
  // composer for the proposal surface IN PLACE — no navigation away (M1). The
  // problem text the user typed seeds the proposal.
  const [cascadeProblem, setCascadeProblem] = useState<string | null>(null);
  // SPR-05 M1 — attach state (a file / URL / passage absorbed into the corpus
  // before the run). Whether the prompt was auto-derived from an attachment is
  // tracked so we can label it honestly in the UI.
  const [attach, setAttach] = useState<AttachState>({ kind: "idle" });
  const [promptDerived, setPromptDerived] = useState(false);
  const taRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
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

  const refreshModels = useCallback(async () => {
    setModelsState("loading");
    try {
      const inventory = await fetchUserModels();
      setModels(inventory.models.filter(isExecutable));
      setModelsState("ready");
    } catch {
      setModels([]);
      setModelsState("error");
    }
  }, []);

  useEffect(() => { void refreshModels(); }, [refreshModels]);

  const selectedModel = modelChoice
    ? models.find((model) => model.id === modelChoice.provider_id && model.model_id === modelChoice.model_id)
    : null;

  useEffect(() => {
    if (modelsState === "ready" && modelChoice && !selectedModel) setModelChoice(null);
  }, [modelsState, modelChoice, selectedModel]);

  const onSubmit = useCallback(async () => {
    const pending = modelChoice && selectedModel
      ? { question, modelChoice, operationId } satisfies PendingOwnerLaunch
      : null;
    if (pending) window.sessionStorage.setItem(OWNER_LAUNCH_KEY, JSON.stringify(pending));
    const id = await submit(modelChoice && selectedModel
      ? { question, modelChoice, operationId }
      : { question, researchTier: tier });
    if (id) {
      window.sessionStorage.removeItem(OWNER_LAUNCH_KEY);
      setQuestion("");
    }
  }, [submit, question, modelChoice, operationId, selectedModel, tier]);

  const selectModel = useCallback((value: string) => {
    const model = models.find((row) => modelKey(row.id, row.model_id) === value);
    if (!model) return;
    setModelChoice({ authority: "user_model", provider_id: model.id, model_id: model.model_id });
    setOperationId(`research-${crypto.randomUUID()}`);
  }, [models]);

  const fillExample = useCallback((prompt: string) => {
    setQuestion(prompt);
    setPromptDerived(false);
    taRef.current?.focus();
  }, []);

  // SPR-05 M1 — voice fills the prompt. VoiceChaseButton owns the record +
  // transcribe + honest-failure path; here a successful transcript just
  // becomes the prompt text (a user-authored question), exactly like typing.
  // We never assert the words on the user's behalf — the transcript lands in
  // the editable composer so it is confirmed/corrected before Ask, the same
  // correct-before-commit guard VoiceChaseButton documents.
  const onVoiceTranscript = useCallback((transcript: string) => {
    const t = transcript.trim();
    if (!t) return; // empty/silent transcript → leave the prompt untouched
    setQuestion(t);
    setPromptDerived(false);
    taRef.current?.focus();
  }, []);

  // SPR-05 M1 — attach a URL / passage / text file. Reuses PasteIngest's
  // ingest calls (ingestSource for a URL, ingestVoiceNote for text) with NO
  // investigation_id: on the home there is no investigation yet, so the backend
  // bins the doc to the `__operator__` corpus sentinel — it is ADDED TO THE
  // CORPUS, NOT auto-retrieved by the run launched next (the UI copy says exactly
  // that; wiring the doc into the launched investigation is the documented SPR-05
  // follow-up). On success, if the prompt is still empty we DERIVE one (operator
  // decision) and mark it derived; the operator sees + can edit it before Ask.
  const onAbsorbed = useCallback(
    (title: string) => {
      setAttach({ kind: "absorbed", title });
      setQuestion((q) => {
        if (q.trim().length > 0) return q; // keep an explicit prompt
        setPromptDerived(true);
        return derivePromptFor(title);
      });
    },
    [],
  );

  const absorbUrl = useCallback(
    async (url: string) => {
      setAttach({ kind: "absorbing" });
      try {
        const r = await ingestSource({ url }); // no investigation_id on the home
        if (r.status === "error") {
          setAttach({ kind: "failed", reason: r.error_message });
          return;
        }
        onAbsorbed(r.title ?? url);
      } catch (e) {
        setAttach({ kind: "failed", reason: e instanceof ApiError ? e.body || null : null });
      }
    },
    [onAbsorbed],
  );

  const absorbText = useCallback(
    async (text: string, title: string) => {
      setAttach({ kind: "absorbing" });
      try {
        const r = await ingestVoiceNote({ transcript: text, title });
        onAbsorbed(r.title ?? title);
      } catch (e) {
        setAttach({ kind: "failed", reason: e instanceof ApiError ? e.body || null : null });
      }
    },
    [onAbsorbed],
  );

  const handleFile = useCallback(
    async (file: File) => {
      // A binary blob the browser can't read as text has no shipped multipart
      // endpoint here — reject it plainly (rigor #1), don't pretend to absorb.
      if (!TEXT_EXTENSIONS.test(file.name) && !file.type.startsWith("text/")) {
        setAttach({
          kind: "rejected",
          why:
            `“${file.name}” isn’t a kind I can absorb directly yet. ` +
            "Paste a link to it, or paste its text.",
        });
        return;
      }
      const text = await file.text();
      await absorbText(text, file.name);
    },
    [absorbText],
  );

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
            className="font-serif text-[15px] leading-relaxed"
            aria-label="Research question"
          />

          {/* Derived-prompt honesty (SPR-05 M1): when an attachment-only
              submission auto-filled the prompt, say so plainly. The text is
              editable above; this only labels its provenance. */}
          {promptDerived && (
            <p
              className="text-[11px] font-mono text-ink-mute dark:text-moonlight"
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
              className="min-w-0 flex-1 rounded-hog border border-rule dark:border-charcoal-1 bg-ice-0 dark:bg-charcoal-2 px-2 py-1 text-[12px] font-mono text-ink dark:text-bright disabled:opacity-50"
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
            <p className="text-[11px] font-mono text-aurora" role="status">
              Added “{attach.title}” to your corpus.
            </p>
          )}
          {attach.kind === "rejected" && (
            <p
              className="text-[11px] font-mono text-shadow-1 dark:text-moonlight"
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

          {error && (
            <div className="text-xs font-mono text-emperor">{error}</div>
          )}

          <div className="rounded-hog border border-rule dark:border-charcoal-1 bg-ice-1/80 dark:bg-charcoal-1/40 p-3 space-y-2">
            <div className="flex flex-col sm:flex-row sm:items-center gap-2">
              <label className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight" id="research-model-label">
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
              <p className="text-[11px] font-mono text-emperor" role="alert">
                Can’t load executable models. Check Settings, then retry inventory.
              </p>
            ) : selectedModel ? (
              <div className="space-y-1" aria-live="polite">
                <p className="text-[11px] font-serif text-ink dark:text-bright">
                  Ask uses this model for the root investigation’s paid Loop One roles. Later chases choose their own route.
                </p>
                <p className="text-[10px] font-mono text-ink-mute dark:text-moonlight break-all">
                  Pricing authority: {selectedModel.rate_snapshot ?? "server-verified executable route"}
                </p>
              </div>
            ) : (
              <p className="text-[11px] font-serif text-ink-mute dark:text-moonlight">
                Only routes the server reports as eligible and executable appear here.
              </p>
            )}
            {!modelChoice && (
              <div className="flex items-center gap-2" role="radiogroup" aria-label="Established research depth">
                {RESEARCH_TIER_OPTIONS.map((option) => (
                  <button key={option.value} type="button" role="radio" aria-checked={tier === option.value}
                    title={option.hint} onClick={() => setTier(option.value)}
                    className={`px-3 py-1 rounded-hog text-[11px] font-mono border border-rule ${tier === option.value ? "bg-sun text-ink" : "bg-ice-0 dark:bg-charcoal-2 text-ink dark:text-bright"}`}>
                    {option.label}
                  </button>
                ))}
              </div>
            )}
            {modelsState !== "loading" && (
              <button type="button" onClick={() => void refreshModels()} className="text-[11px] font-mono underline text-ink dark:text-bright">
                Retry inventory
              </button>
            )}
          </div>

          <div className="flex items-center justify-between gap-3">
            <div className="text-[11px] font-mono text-ink-mute dark:text-moonlight">
              <kbd className="border-2 border-ink dark:border-bright rounded px-1.5 text-[10px] font-mono bg-ice-0 dark:bg-charcoal-1 shadow-z1 dark:shadow-z1-night mr-1.5">
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
          <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight mb-2 text-center">
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
                    "w-full text-left text-[13px] font-serif text-ink dark:text-bright px-3 py-2 rounded-hog " +
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
