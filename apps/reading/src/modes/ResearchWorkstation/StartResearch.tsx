import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import { Link, useLocation } from "react-router-dom";
import { useModeNavigate } from "../../workspace/useModeNavigate";
import { readNavigationEpoch, subscribeNavigationLifetime } from "../../workspace/navigationLifetime";
import { locationStamp, useTabTrees } from "../../workspace/tabTreeStore";
import { getHydrationGeneration, useWorkspace } from "../../workspace/WorkspaceStore";
import type { ReadyModelScope } from "../../lib/modelExecutionScope";

import { cardLift } from "../../design/motion";
import GlassSurface from "../../shell/GlassSurface";
import LemonButton from "../../components/lemon/LemonButton";
import LemonTextarea from "../../components/lemon/LemonTextarea";
import OwnerModelUsagePicker from "../../components/ai/OwnerModelUsagePicker";
import { useOwnerModelController, type OwnerModelController } from "../../hooks/useOwnerModelController";
import { useAuth } from "../../lib/auth";
import Thinking from "../../shared/Thinking";
import AIActionFailure from "../../shared/AIActionFailure";
import { ErrorState } from "../../components/states";
import { CelebrateBurst, useCelebrate } from "../../shared/delight";
import { useStartInvestigation } from "../../hooks/useStartInvestigation";
import { ApiError, ingestSource, ingestVoiceNote } from "../../lib/api";
import type {
  ResearchSourcePolicy,
  ResearchTier,
} from "../../lib/api";
import CascadeProposal from "./CascadeProposal";
import MyResearch from "./MyResearch";
import QuickAsk from "./QuickAsk";
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

const RESEARCH_TIER_OPTIONS: ReadonlyArray<{ value: ResearchTier; label: string }> = [
  { value: "fast", label: "Fast" },
  { value: "deep", label: "Deep" },
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
const DEFAULT_SOURCE_POLICY: ResearchSourcePolicy[] = ["operator_corpus", "web"];

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

type ResearchHome = Readonly<{
  scope: ReadyModelScope;
  navigationEpoch: number;
  contextEpoch: number;
  hydrationGeneration: number;
  stamp: string;
}>;
const readContextEpoch = () => useTabTrees.getState().contextEpoch;

/** The root research route's observed lifetime, never project authority. */
export function useResearchHomeBinding() {
  const location = useLocation();
  const { modelExecution } = useAuth();
  const scope = modelExecution.current;
  useSyncExternalStore(subscribeNavigationLifetime, readNavigationEpoch, readNavigationEpoch);
  useSyncExternalStore(useTabTrees.subscribe, readContextEpoch, readContextEpoch);
  useSyncExternalStore(useWorkspace.subscribe, getHydrationGeneration, getHydrationGeneration);
  const current = useRef<ResearchHome | null>(null);
  const mounted = useRef(false);
  useLayoutEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; current.current = null; };
  }, []);
  const [, notify] = useState(0);
  const readHome = useCallback((): ResearchHome | null => {
    const home = current.current;
    return mounted.current && home && modelExecution.readCurrent() === home.scope &&
      readNavigationEpoch() === home.navigationEpoch && readContextEpoch() === home.contextEpoch &&
      getHydrationGeneration() === home.hydrationGeneration && locationStamp() === home.stamp
      ? home : null;
  }, [modelExecution.readCurrent]);
  const isHomeCurrent = useCallback((home: object) => readHome() === home, [readHome]);
  useEffect(() => {
    if (readHome()) return;
    // Every shell layout effect, including route hydration, has already run.
    // Never use this new baseline to update an earlier issued operation.
    const actualEpoch = readNavigationEpoch();
    if (scope.kind !== "ready" || modelExecution.readCurrent() !== scope || actualEpoch === null ||
        location.pathname !== "/" || window.location.pathname !== "/") {
      current.current = null;
      return;
    }
    // Hydration may have removed ?ws through the observed raw replacement,
    // which intentionally does not publish a new Router query/key.
    const home: ResearchHome = Object.freeze({
      scope, navigationEpoch: actualEpoch, contextEpoch: readContextEpoch(),
      hydrationGeneration: getHydrationGeneration(), stamp: locationStamp(),
    });
    current.current = home;
    notify((value) => value + 1);
  });
  return { readHome, isHomeCurrent };
}

export default function StartResearch({ embedded = false }: { embedded?: boolean }) {
  const navigate = useModeNavigate();
  const { modelExecution } = useAuth();
  const controller = useOwnerModelController({
    operationPrefix: "research", policy: "strict-owner", allowHouse: false,
  });
  const homeBinding = useResearchHomeBinding();
  const renderedHome = homeBinding.readHome();
  const [modeBinding, setModeBinding] = useState<{ mode: "quick" | "deep" }>(() => ({ mode: "quick" }));
  const askMode = modeBinding.mode;
  const [quickAskSending, setQuickAskSending] = useState(false);
  const quickAskSendingRef = useRef(false);
  const askModeRef = useRef(modeBinding);
  const renderedScope = modelExecution.current;
  const draftScopeRef = useRef(renderedScope);
  const draftHomeRef = useRef(renderedHome);
  const onQuickPaidChange = useCallback((pending: boolean) => {
    quickAskSendingRef.current = pending;
    setQuickAskSending(pending);
  }, []);
  const changeMode = (mode: "quick" | "deep") => {
    if (mode === askModeRef.current.mode) return;
    if (!renderedHome || !homeBinding.isHomeCurrent(renderedHome) ||
        renderedScope.kind !== "ready" || modelExecution.readCurrent() !== renderedScope ||
        askModeRef.current !== modeBinding || quickAskSendingRef.current || start.isIssued()) return;
    const next = { mode };
    askModeRef.current = next;
    setModeBinding(next);
  };
  const [tier, setTier] = useState<ResearchTier>("deep");
  const [questionState, setQuestion] = useState("");
  const question = draftScopeRef.current === renderedScope && draftHomeRef.current === renderedHome ? questionState : "";
  const [sourcePolicy, setSourcePolicy] = useState<ResearchSourcePolicy[]>(
    DEFAULT_SOURCE_POLICY,
  );
  const [draftRevision, setDraftRevision] = useState<object>(() => ({}));
  const draftRevisionRef = useRef(draftRevision);
  const readDraftRevision = useCallback(() => draftRevisionRef.current, []);
  const readAdmission = useCallback((): object | null => {
    if (!renderedHome || !homeBinding.isHomeCurrent(renderedHome) ||
        renderedScope.kind !== "ready" || modelExecution.readCurrent() !== renderedScope ||
        askModeRef.current !== modeBinding || modeBinding.mode !== "deep" || quickAskSendingRef.current) return null;
    return modeBinding;
  }, [renderedHome, homeBinding.isHomeCurrent, renderedScope, modelExecution, modeBinding]);
  const isAdmitted = useCallback(() => readAdmission() !== null, [readAdmission]);
  const start = useStartInvestigation({
    controller, readHome: homeBinding.readHome, isHomeCurrent: homeBinding.isHomeCurrent,
    readAdmission, isAdmitted, readDraftRevision,
  });
  const isDraftCurrent = useCallback(() =>
    draftRevisionRef.current === draftRevision &&
    draftScopeRef.current === renderedScope && draftHomeRef.current === renderedHome &&
    readAdmission() === modeBinding && !start.isIssued(),
  [draftRevision, renderedScope, renderedHome, modeBinding, readAdmission, start.isIssued]);
  const advanceDraft = useCallback(() => {
    const next = {};
    draftRevisionRef.current = next;
    setDraftRevision(next);
  }, []);
  const isPickerCurrent = useCallback(() => isAdmitted() && !start.isIssued(), [isAdmitted, start.isIssued]);
  const inventoryReady = controller.inventory.kind === "ready" && controller.isInventoryCurrent(controller.inventory);
  const modelSelection = controller.selection;
  const selectedModel = inventoryReady && controller.inventory.kind === "ready" && modelSelection.kind === "saved"
    ? controller.inventory.rows.find((row) => row.id === modelSelection.recordId) : null;
  const pickerController = useMemo<OwnerModelController>(() => ({
    ...controller,
    select(choice) {
      if (!isDraftCurrent()) return;
      advanceDraft();
      controller.select(choice);
    },
  }), [controller, isDraftCurrent, advanceDraft]);
  // Two entry actions on one composer: Ask (one-shot, the shipped fast lane,
  // default) and Break-into-sub-questions (cascade). Cascade swaps the
  // composer for the proposal surface IN PLACE — no navigation away (M1). The
  // problem text the user typed seeds the proposal.
  const [cascadeProblem, setCascadeProblem] = useState<string | null>(null);
  // SPR-05 M1 — attach state (a file / URL / passage absorbed into the corpus
  // before the run). Whether the prompt was auto-derived from an attachment is
  // tracked so we can label it honestly in the UI.
  const [attachState, setAttach] = useState<AttachState>({ kind: "idle" });
  const attach: AttachState = draftScopeRef.current === renderedScope && draftHomeRef.current === renderedHome ? attachState : { kind: "idle" };
  const [promptDerived, setPromptDerived] = useState(false);
  const taRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  // The research-starts signature beat (U-05 M2) — Brain's one-shot
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
  } = start;

  const onSubmit = useCallback(async () => {
    if (!isDraftCurrent()) return;
    const id = await submit({ question, sourcePolicy: [...sourcePolicy], researchTier: tier, revision: draftRevision });
    if (id && start.isDeliveryCurrent(id) && draftRevisionRef.current === draftRevision) {
      setQuestion("");
    }
  }, [submit, question, sourcePolicy, tier, draftRevision, isDraftCurrent, start.isDeliveryCurrent]);

  const toggleSourcePolicy = useCallback((value: ResearchSourcePolicy) => {
    if (!isDraftCurrent()) return;
    const next = sourcePolicy.includes(value)
      ? sourcePolicy.filter((item) => item !== value)
      : [...sourcePolicy, value];
    if (!next.length) return;
    advanceDraft();
    setSourcePolicy(next);
  }, [sourcePolicy, isDraftCurrent, advanceDraft]);

  const changeTier = (value: ResearchTier) => {
    if (!isDraftCurrent()) return;
    advanceDraft();
    setTier(value);
  };

  const fillExample = useCallback((prompt: string) => {
    if (!isDraftCurrent()) return;
    advanceDraft();
    setQuestion(prompt);
    setPromptDerived(false);
    taRef.current?.focus();
  }, [isDraftCurrent, advanceDraft]);

  // SPR-05 M1 — voice fills the prompt. VoiceChaseButton owns the record +
  // transcribe + honest-failure path; here a successful transcript just
  // becomes the prompt text (a user-authored question), exactly like typing.
  // We never assert the words on the user's behalf — the transcript lands in
  // the editable composer so it is confirmed/corrected before Ask, the same
  // correct-before-commit guard VoiceChaseButton documents.
  const onVoiceTranscript = useCallback((transcript: string) => {
    const t = transcript.trim();
    if (!t || !isDraftCurrent()) return;
    advanceDraft();
    setQuestion(t);
    setPromptDerived(false);
    taRef.current?.focus();
  }, [isDraftCurrent, advanceDraft]);

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
      if (!isDraftCurrent()) return;
      setAttach({ kind: "absorbed", title });
      if (question.trim()) return;
      advanceDraft();
      setPromptDerived(true);
      setQuestion(derivePromptFor(title));
    },
    [question, isDraftCurrent, advanceDraft],
  );

  const absorbUrl = useCallback(
    async (url: string) => {
      if (!isDraftCurrent()) return;
      setAttach({ kind: "absorbing" });
      try {
        const r = await ingestSource({ url }); // no investigation_id on the home
        if (!isDraftCurrent()) return;
        if (r.status === "error") {
          setAttach({ kind: "failed", reason: r.error_message });
          return;
        }
        onAbsorbed(r.title ?? url);
      } catch (e) {
        if (!isDraftCurrent()) return;
        setAttach({ kind: "failed", reason: e instanceof ApiError ? e.body || null : null });
      }
    },
    [onAbsorbed, isDraftCurrent],
  );

  const absorbText = useCallback(
    async (text: string, title: string) => {
      if (!isDraftCurrent()) return;
      setAttach({ kind: "absorbing" });
      try {
        const r = await ingestVoiceNote({ transcript: text, title });
        onAbsorbed(r.title ?? title);
      } catch (e) {
        if (!isDraftCurrent()) return;
        setAttach({ kind: "failed", reason: e instanceof ApiError ? e.body || null : null });
      }
    },
    [onAbsorbed, isDraftCurrent],
  );

  const handleFile = useCallback(
    async (file: File) => {
      if (!isDraftCurrent()) return;
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
      if (!isDraftCurrent()) return;
      await absorbText(text, file.name);
    },
    [absorbText, isDraftCurrent],
  );

  // Enter cascade mode with the typed problem space. Same >= 3-char floor as
  // Ask so an empty composer can't propose an empty plan.
  const onBreakDown = useCallback(() => {
    if (!isDraftCurrent()) return;
    const q = question.trim();
    if (q.length < 3) return;
    setCascadeProblem(q);
  }, [question, isDraftCurrent]);

  // Back out of cascade (the proposal couldn't split it, or the user chose
  // one question instead): keep the typed problem so Ask is one click away.
  const onCascadeFallBack = useCallback(() => {
    if (!isDraftCurrent()) return;
    setCascadeProblem(null);
    taRef.current?.focus();
  }, [isDraftCurrent]);

  const onStartSeparate = useCallback(() => {
    if (!isDraftCurrent() || !start.startSeparate()) return;
    advanceDraft();
    taRef.current?.focus();
  }, [isDraftCurrent, start.startSeparate, advanceDraft]);

  // On failure, restore the question the operator typed so the run is
  // recoverable. (onSubmit clears it only on a successful POST; but the run
  // can fail *after* the POST returned an id, so we re-seed it here.)
  const lastQuestionRef = useRef("");
  useLayoutEffect(() => {
    if (draftScopeRef.current === renderedScope && draftHomeRef.current === renderedHome) return;
    draftScopeRef.current = renderedScope;
    draftHomeRef.current = renderedHome;
    advanceDraft();
    setQuestion("");
    lastQuestionRef.current = "";
    setAttach({ kind: "idle" });
    setPromptDerived(false);
    setSourcePolicy(DEFAULT_SOURCE_POLICY);
    setTier("deep");
    setCascadeProblem(null);
  }, [renderedScope, renderedHome, advanceDraft]);
  useEffect(() => {
    if (question) lastQuestionRef.current = question;
  }, [question]);
  useEffect(() => {
    if (failed && start.isDeliveryCurrent(startedId ?? undefined) && !question && lastQuestionRef.current) {
      setQuestion(lastQuestionRef.current);
    }
  }, [failed, question, startedId, start.isDeliveryCurrent]);

  // Fire the research-starts beat exactly once, at the transition into the
  // started-and-not-failed state (an id is back, the run is live). It's
  // independent of the navigate effect below: `celebrate()` returns
  // immediately, so the beat never sits between "research is under way" and
  // the operator seeing it. A failed run never celebrates.
  const startedAndLive = Boolean(startedId) && !failed;
  const celebratedRef = useRef(false);
  useEffect(() => {
    if (startedAndLive && startedId && start.isDeliveryCurrent(startedId) && !celebratedRef.current) {
      celebratedRef.current = true;
      try { celebrate(); }
      catch { start.reportDeliveryFailure(startedId, "Research started, but its start animation could not be displayed."); }
    }
    if (!startedId) celebratedRef.current = false; // re-arm after reset
  }, [startedAndLive, startedId, celebrate, start.isDeliveryCurrent, start.reportDeliveryFailure]);

  const navigationProgress = useRef({ startedId, failed, error });
  useLayoutEffect(() => {
    navigationProgress.current = { startedId, failed, error };
  }, [startedId, failed, error]);
  const openReceived = useCallback((id: string) => {
    const current = navigationProgress.current;
    if (current.startedId !== id || current.failed || !start.isDeliveryCurrent(id)) return;
    try { navigate(`/inv/${id}`); }
    catch { start.reportDeliveryFailure(id, "Research started, but this view could not open it. You can open the received investigation again."); }
  }, [navigate, start.isDeliveryCurrent, start.reportDeliveryFailure]);

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
    if (!startedId || !start.isDeliveryCurrent(startedId)) return;
    if (failed || error) return;
    if (events.length > 0) {
      openReceived(startedId);
      return;
    }
    const t = window.setTimeout(() => {
      // This is the latest committed stream observation, not an unexposed
      // synchronous socket state. Action/home/mode admission is read live.
      const current = navigationProgress.current;
      if (current.startedId === startedId && !current.failed && !current.error && start.isDeliveryCurrent(startedId)) {
        openReceived(startedId);
      }
    }, NAVIGATE_GRACE_MS);
    return () => window.clearTimeout(t);
  }, [startedId, failed, error, events.length, openReceived, start.isDeliveryCurrent]);

  // ── Starting state: id returned, stream attached, run still progressing.
  //    A terminal failure falls through to the composer surface below, where
  //    we show an honest error and a Try-again action (never the dead
  //    /inv/:id route). ──
  const startingPanel = startedId && !failed ? (
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
          {error && <p role="alert" className="text-sm text-danger">{error}</p>}
          {error && <LemonButton onClick={() => openReceived(startedId)}>Open received investigation</LemonButton>}
        </div>
      </div>
    ) : null;

  // ── Cascade mode: the AI proposes sub-questions, the user trims, then
  //    launches N parallel researches. Stays on this surface (no navigation
  //    away) until launch hands a session to the monitor. ──
  const cascadePanel = cascadeProblem ? (
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
    ) : null;
  const idle = !startingPanel && !cascadePanel;

  // ── Idle state: the start-a-research composer + (M3) the research LOG. ──
  //
  // SPR-05 M3 (log-as-home): the IDLE home is the composer ABOVE the MyResearch
  // log. `embedded` lets the consolidated home (ResearchWorkstation idle branch)
  // present the composer top-aligned in a scroll column with the log beneath it,
  // instead of the legacy vertically-centred empty composer. When the surface is
  // mounted standalone (embedded=false, e.g. a unit test or a route that wants
  // only the composer) it keeps the centred layout and shows no log.
  return (
    <>
    {startingPanel}
    {cascadePanel}
    <div
      hidden={!idle}
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
        {idle && <>
        <h1 className="text-2xl font-serif text-ink dark:text-bright mb-2 text-center">
          What do you want to research?
        </h1>
        <div className="flex flex-wrap items-center justify-center gap-2 mb-5" role="group" aria-label="Research mode">
          <button type="button" aria-pressed={askMode === "quick"} disabled={quickAskSending || start.isIssued()}
            onClick={() => changeMode("quick")}
            className={`px-3 py-2 rounded-hog border-edge border-sun text-xs font-mono ${askMode === "quick" ? "bg-sun text-ink" : "bg-ice-0 dark:bg-charcoal-2 text-ink dark:text-bright"}`}>
            Quick Ask · one model request
          </button>
          <button type="button" aria-pressed={askMode === "deep"} disabled={quickAskSending || start.isIssued()}
            onClick={() => changeMode("deep")}
            className={`px-3 py-2 rounded-hog border-edge border-sun text-xs font-mono ${askMode === "deep" ? "bg-sun text-ink" : "bg-ice-0 dark:bg-charcoal-2 text-ink dark:text-bright"}`}>
            Deep research · multiple model calls
          </button>
        </div>
        </>}
        <div hidden={!idle || askMode !== "quick"}>
          <QuickAsk onPaidRequestInFlight={onQuickPaidChange} />
        </div>
        {idle && askMode === "deep" && <>
        <p className="text-sm text-shadow-1 dark:text-moonlight leading-relaxed font-serif text-center mb-6">
          Ask a question. The substrate runs a recursive note-taking chain
          across your corpus, distills insights and open questions, and
          renders a cited thesis. Highlight anything in the result to chase
          it further.
          It can make multiple model requests before the result is ready.
        </p>

        <div className="flex flex-col gap-3">
          <LemonTextarea
            ref={taRef}
            value={question}
            onChange={(e) => {
              if (!isDraftCurrent()) return;
              advanceDraft();
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
              onRetry={() => { if (isDraftCurrent()) setAttach({ kind: "idle" }); }}
              retryLabel="Dismiss"
            />
          )}

          {failed && (
            // The presentational failure shell is now the shared
            // <AIActionFailure> (U-04) — same sentence across all four doors.
            // A failed run remains a received paid operation; this diagnostic
            // does not grant another POST.
            <AIActionFailure
              title="The research didn’t complete"
              reason={failureReason}
              code="unknown"
              retryable={false}
              onRetry={start.reset}
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
                body="The request may have been accepted or charged. No automatic retry was made."
                detail={error}
              />
            ) : (
              <p role="alert" className="text-sm text-danger">{error}</p>
            ))}

          {(start.requiresNewIntent || start.showUncertainty || failed) && (
            <div role="status" className="text-sm font-serif text-ink dark:text-bright">
              <p>{start.showUncertainty
                ? "A previous research request may have been accepted or charged. Starting separately does not cancel or replay it."
                : "Start a separate paid research before sending another question."}</p>
              <LemonButton onClick={onStartSeparate} disabled={busy || start.continuityUnavailable}>
                Start a separate paid research
              </LemonButton>
            </div>
          )}
          {start.continuityUnavailable && <p role="alert" className="text-sm text-danger">Research request continuity could not be checked. No new request was sent.</p>}

          <div className="rounded-hog border border-rule dark:border-charcoal-1 bg-ice-1/80 dark:bg-charcoal-1/40 p-3 space-y-2">
            <div className="flex flex-col sm:flex-row sm:items-center gap-2">
              <label className="text-xs font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight" id="research-model-label">
                Model for Ask
              </label>
              <OwnerModelUsagePicker
                controller={pickerController}
                allowHouse={false}
                triggerAriaLabel="Model for Ask investigation"
                isResourceCurrent={isPickerCurrent}
              />
            </div>
            {controller.inventory.kind === "failed" ? (
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
                Choose an executable saved model before starting deep research.
                If none appears, <Link to="/settings" className="underline text-ink dark:text-bright">connect one in Settings</Link> and retry inventory.
              </p>
            )}
            <div className="flex items-center gap-2" role="radiogroup" aria-label="Research depth">
              {RESEARCH_TIER_OPTIONS.map((option) => (
                <button key={option.value} type="button" role="radio" aria-checked={tier === option.value}
                  onClick={() => changeTier(option.value)} disabled={busy}
                  className={`px-3 py-1 rounded-hog text-xs font-mono border border-rule ${tier === option.value ? "bg-sun text-ink" : "bg-ice-0 dark:bg-charcoal-2 text-ink dark:text-bright"}`}>
                  {option.label}
                </button>
              ))}
            </div>
            {controller.inventory.kind !== "loading" && (
              <button type="button" onClick={() => { if (isDraftCurrent()) void controller.refresh(); }} className="text-xs font-mono underline text-ink dark:text-bright">
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
                disabled
                aria-describedby="sub-question-unavailable"
              >
                Break into sub-questions
              </LemonButton>
              <LemonButton
                variant="primary"
                size="lg"
                onClick={() => void onSubmit()}
                disabled={busy || !isDraftCurrent() || !inventoryReady || start.submitDisabled || question.trim().length < 3 || controller.selection.kind !== "saved"}
              >
                {busy ? "Starting…" : "Ask"}
              </LemonButton>
            </div>
          </div>
          <p id="sub-question-unavailable" className="text-xs font-serif text-ink-mute dark:text-moonlight">
            Sub-question planning is unavailable until its proposal and launch can use your saved model.
          </p>
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
        </>}

        {/* SPR-05 M3 — the research LOG, folded into the home. Only in the
            consolidated home (`embedded`), so a fresh `/` is the composer AND
            the scannable list of past/running projects (operator's
            "log-as-home"). MyResearch keeps its own row links to /inv/{id}, so
            clicking a project navigates to its workstation — the consolidation
            is presentational, the row-nav contract is unchanged. We pass
            `embedded` so MyResearch drops its now-redundant launch bar (the
            composer above IS the entry) and reads as a log section. */}
        {idle && embedded && (
          <div className="mt-12 border-t border-rule dark:border-charcoal-1 pt-2">
            <MyResearch embedded />
          </div>
        )}
      </GlassSurface>
    </div>
    </>
  );
}
