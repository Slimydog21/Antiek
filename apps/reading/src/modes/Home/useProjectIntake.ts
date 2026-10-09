import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { accountStorageKey, isWorkspaceOwnerSession, workspaceOwnerSession } from "../../lib/accountWorkspaceOwner";
import { useModeNavigate } from "../../workspace/useModeNavigate";
import { useCelebrate } from "../../shared/delight";
import { useStartInvestigation } from "../../hooks/useStartInvestigation";
import { ApiError, ingestSource, ingestVoiceNote } from "../../lib/api";
import type { ResearchSourcePolicy, ResearchTier, UserModelChoice } from "../../lib/api";
import { fetchUserModels, type UserModelRow } from "../../api/settingsModels";
import { addProjectMember, createProject, PROJECT_SEED_CONTRACT_LIVE } from "../../lib/api/projects";

/**
 * useProjectIntake — the intake machine behind every "start something" box
 * (FFX-KPA SPR-03 M1). Extracted verbatim from StartResearch.tsx so the
 * Research door and the zen home share one implementation of: the prompt,
 * voice-fills-the-prompt, URL → POST /sources/ingest, text file →
 * POST /voice-notes/ingest, the attachment-only derived prompt, tier /
 * source policy / owner model, submit through useStartInvestigation, the
 * research-starts beat, and the navigate-on-first-event-or-1.5 s rule.
 *
 * Nothing here changes a request shape: the POST /investigations body is
 * built by useStartInvestigation exactly as before (useProjectIntake.test.ts
 * pins the bytes). StartResearch renders over this hook; ZenHome renders a
 * calmer surface over the same state.
 *
 * Owner-model rule (useOwnerModelChoice.ts:19-33): `model_choice` and
 * `operation_id` travel together or not at all. onSubmit sends both only when
 * the chosen row is still in the executable inventory, otherwise the tier.
 *
 * The pending owner launch is stashed in sessionStorage before the POST and
 * cleared once an id returns, so a reload mid-launch restores the question,
 * the model and the same idempotency id (useStartInvestigation.ts:103-172).
 */

const OWNER_LAUNCH_KEY = "antiek.research.pending-owner-launch.session.v1";
export const modelKey = (providerId: string, modelId: string) => `${providerId}\u0000${modelId}`;
const isExecutable = (model: UserModelRow) =>
  model.enabled && model.key_present && model.registered && model.route_eligible &&
  model.pricing_status === "known" && model.hard_ceiling_eligible &&
  model.execution_status === "executable";

interface PendingOwnerLaunch {
  question: string;
  modelChoice: UserModelChoice;
  operationId: string;
}

function readPendingOwnerLaunch(): PendingOwnerLaunch | null {
  const key = accountStorageKey(OWNER_LAUNCH_KEY);
  if (key === null) return null;
  try {
    const raw = window.sessionStorage.getItem(key);
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

export const DEFAULT_SOURCE_POLICY: ResearchSourcePolicy[] = ["operator_corpus", "web"];

/** Grace period before navigating even if no event has streamed yet, so a
 *  slow WS connection doesn't strand the operator on the start surface. */
export const NAVIGATE_GRACE_MS = 1500;

/** Match PasteIngest's URL test so a pasted/typed link goes to ingestSource
 *  and any other text to ingestVoiceNote (PasteIngest.tsx:120). */
export const URL_RE = /^https?:\/\/\S+$/i;
/** Text-file extensions the browser can read as text (mirror of
 *  PasteIngest.TEXT_EXTENSIONS). A binary blob is rejected honestly. */
export const TEXT_EXTENSIONS = /\.(txt|md|markdown|csv|json|log|rtf)$/i;

/** Attachment-only with an EMPTY prompt is accepted with a DERIVED prompt
 *  rather than blocked (operator decision, SPR-05 M1). It is shown in the
 *  composer (editable) and labelled as derived, never chosen silently. */
export function derivePromptFor(title: string): string {
  const t = title.trim();
  return t
    ? `Understand and distill “${t}”, and surface its key claims and open questions.`
    : "Understand and distill the attached material, and surface its key claims and open questions.";
}

/** What an attach attempt produced (no investigation exists yet). */
export type AttachState =
  | { kind: "idle" }
  | { kind: "absorbing" }
  | { kind: "absorbed"; title: string }
  | { kind: "rejected"; why: string }
  | { kind: "failed"; reason: string | null };

/** What submitProject() created. Before the SPR-B intake contract
 *  (ffx-nav-backend-intake) there is no registry call and the investigation id
 *  doubles as the project id. */
export interface CreatedProject {
  projectId: string;
  investigationId: string;
  registry: "created" | "skipped-pre-contract";
}

export interface ProjectIntakeOptions {
  /** Whether the "create project from seed" registry contract is live.
   *  Defaults to PROJECT_SEED_CONTRACT_LIVE (false until SPR-B). */
  projectSeedContract?: boolean;
}

export function useProjectIntake(options: ProjectIntakeOptions = {}) {
  const projectSeedContract = options.projectSeedContract ?? PROJECT_SEED_CONTRACT_LIVE;
  const [owner] = useState(workspaceOwnerSession);
  const navigate = useModeNavigate();
  const start = useStartInvestigation();
  const restoredLaunch = useMemo(readPendingOwnerLaunch, []);
  const [question, setQuestion] = useState(restoredLaunch?.question ?? "");
  // The curated fast/deep tier. Closed set; defaults to deep.
  const [tier, setTier] = useState<ResearchTier>("deep");
  const [sourcePolicy, setSourcePolicy] = useState<ResearchSourcePolicy[]>(DEFAULT_SOURCE_POLICY);
  const [models, setModels] = useState<UserModelRow[]>([]);
  const [modelsState, setModelsState] = useState<"loading" | "ready" | "error">("loading");
  const [modelChoice, setModelChoice] = useState<UserModelChoice | null>(
    restoredLaunch?.modelChoice ?? null,
  );
  const [operationId, setOperationId] = useState(
    restoredLaunch?.operationId ?? `research-${crypto.randomUUID()}`,
  );
  const [attach, setAttach] = useState<AttachState>({ kind: "idle" });
  const [promptDerived, setPromptDerived] = useState(false);
  const [projectError, setProjectError] = useState<string | null>(null);
  const composerRef = useRef<HTMLTextAreaElement>(null);
  const { celebrating, celebrate } = useCelebrate();

  const { startedId, events, failed, submit, reset } = start;

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
    if (!isWorkspaceOwnerSession(owner)) return null;
    const key = accountStorageKey(OWNER_LAUNCH_KEY, owner);
    if (key === null) return null;
    const pending = modelChoice && selectedModel
      ? { question, modelChoice, operationId } satisfies PendingOwnerLaunch
      : null;
    if (pending) window.sessionStorage.setItem(key, JSON.stringify(pending));
    const id = await submit(modelChoice && selectedModel
      ? { question, modelChoice, operationId, sourcePolicy }
      : { question, researchTier: tier, sourcePolicy });
    if (id && isWorkspaceOwnerSession(owner)) {
      window.sessionStorage.removeItem(key);
      setQuestion("");
    }
    return id;
  }, [submit, question, modelChoice, operationId, selectedModel, tier, sourcePolicy, owner]);

  // SPR-03 M6 — submit as a project. Pre-contract (PROJECT_SEED_CONTRACT_LIVE
  // false) this is onSubmit and the investigation id is the project seed.
  // TODO(ffx-nav-backend-intake, SPR-B): once the intake contract publishes
  // the project-seed response, flip PROJECT_SEED_CONTRACT_LIVE and drop the
  // pre-contract branch. POST /investigations carries no project field
  // (lib/api.ts:311-332), so the live branch links the run with the existing
  // member edge rather than inventing a request shape.
  const submitProject = useCallback(async (): Promise<CreatedProject | null> => {
    setProjectError(null);
    if (!projectSeedContract) {
      const id = await onSubmit();
      return id ? { projectId: id, investigationId: id, registry: "skipped-pre-contract" } : null;
    }
    const title = question.trim();
    if (title.length < 3) return null;
    let projectId: string;
    try {
      projectId = (await createProject({ title, kind: "project" })).project_id;
    } catch {
      setProjectError("Couldn’t create the project. Your words are still here; try again.");
      return null;
    }
    const id = await onSubmit();
    if (!id) {
      // The project exists but the run did not start; say so rather than
      // let a retry mint a second project silently.
      setProjectError("The project was created, but the research didn’t start. Your words are still here.");
      return null;
    }
    try {
      await addProjectMember(projectId, { member_kind: "investigation", member_id: id });
    } catch {
      // The run started; only the membership edge failed. Say so, keep going.
      setProjectError("The research started, but it couldn’t be filed under the new project.");
    }
    return { projectId, investigationId: id, registry: "created" };
  }, [projectSeedContract, onSubmit, question]);

  const toggleSourcePolicy = useCallback((value: ResearchSourcePolicy) => {
    setSourcePolicy((current) => {
      const next = current.includes(value)
        ? current.filter((item) => item !== value)
        : [...current, value];
      return next.length > 0 ? next : current;
    });
  }, []);

  const selectModel = useCallback((value: string) => {
    const model = models.find((row) => modelKey(row.id, row.model_id) === value);
    if (!model) return;
    setModelChoice({ authority: "user_model", provider_id: model.id, model_id: model.model_id });
    setOperationId(`research-${crypto.randomUUID()}`);
  }, [models]);

  /** A hand edit: the prompt is no longer the derived one. */
  const editQuestion = useCallback((text: string) => {
    setQuestion(text);
    setPromptDerived(false);
  }, []);

  const fillExample = useCallback((prompt: string) => {
    setQuestion(prompt);
    setPromptDerived(false);
    composerRef.current?.focus();
  }, []);

  // Voice fills the prompt: a successful transcript becomes the prompt text,
  // exactly like typing, and stays editable before Ask.
  const applyTranscript = useCallback((transcript: string) => {
    const t = transcript.trim();
    if (!t) return; // empty/silent transcript → leave the prompt untouched
    setQuestion(t);
    setPromptDerived(false);
    composerRef.current?.focus();
  }, []);

  // No investigation_id on the home: the backend bins the doc to the
  // `__operator__` corpus sentinel — added to the corpus, not auto-retrieved
  // by the run launched next. If the prompt is still empty, derive one.
  const onAbsorbed = useCallback((title: string) => {
    setAttach({ kind: "absorbed", title });
    setQuestion((q) => {
      if (q.trim().length > 0) return q;
      setPromptDerived(true);
      return derivePromptFor(title);
    });
  }, []);

  const absorbUrl = useCallback(async (url: string) => {
    setAttach({ kind: "absorbing" });
    try {
      const r = await ingestSource({ url });
      if (r.status === "error") {
        setAttach({ kind: "failed", reason: r.error_message });
        return false;
      }
      onAbsorbed(r.title ?? url);
      return true;
    } catch (e) {
      setAttach({ kind: "failed", reason: e instanceof ApiError ? e.body || null : null });
      return false;
    }
  }, [onAbsorbed]);

  const absorbText = useCallback(async (text: string, title: string) => {
    setAttach({ kind: "absorbing" });
    try {
      const r = await ingestVoiceNote({ transcript: text, title });
      onAbsorbed(r.title ?? title);
      return true;
    } catch (e) {
      setAttach({ kind: "failed", reason: e instanceof ApiError ? e.body || null : null });
      return false;
    }
  }, [onAbsorbed]);

  const handleFile = useCallback(async (file: File) => {
    // A binary blob has no shipped multipart endpoint here — reject plainly.
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
  }, [absorbText]);

  // Try again after a failed run: tear the started id down and refocus.
  const onTryAgain = useCallback(() => {
    reset();
    composerRef.current?.focus();
  }, [reset]);

  // On failure, restore the question so the run is recoverable (onSubmit
  // clears it on a successful POST; the run can fail after that).
  const lastQuestionRef = useRef("");
  useEffect(() => {
    if (question) lastQuestionRef.current = question;
  }, [question]);
  useEffect(() => {
    if (failed && !question && lastQuestionRef.current) {
      setQuestion(lastQuestionRef.current);
    }
  }, [failed, question]);

  // The research-starts beat, exactly once per started-and-live run.
  const startedAndLive = Boolean(startedId) && !failed;
  const celebratedRef = useRef(false);
  useEffect(() => {
    if (startedAndLive && !celebratedRef.current) {
      celebratedRef.current = true;
      celebrate();
    }
    if (!startedId) celebratedRef.current = false; // re-arm after reset
  }, [startedAndLive, startedId, celebrate]);

  // Navigate to /inv/:id on the first real event or after the grace window;
  // never after a terminal investigation.failed (that route would be empty).
  useEffect(() => {
    if (!startedId) return;
    if (failed) return;
    if (events.length > 0) {
      navigate(`/inv/${startedId}`);
      return;
    }
    const t = window.setTimeout(() => {
      if (!failed) navigate(`/inv/${startedId}`);
    }, NAVIGATE_GRACE_MS);
    return () => window.clearTimeout(t);
  }, [startedId, failed, events.length, navigate]);

  return {
    start,
    navigate,
    composerRef,
    question,
    setQuestion,
    editQuestion,
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
    operationId,
    refreshModels,
    attach,
    setAttach,
    absorbUrl,
    absorbText,
    handleFile,
    applyTranscript,
    fillExample,
    onSubmit,
    submitProject,
    projectError,
    onTryAgain,
    celebrating,
  };
}

export type ProjectIntake = ReturnType<typeof useProjectIntake>;
