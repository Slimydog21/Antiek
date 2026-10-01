import {
  useCallback,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";
import { useModeNavigate } from "../../workspace/useModeNavigate";
import {
  type OwnerModelController,
  type PreparedModelLaunch,
} from "../../hooks/useOwnerModelController";
import { useAuth } from "../../lib/auth";
import type {
  ModelExecutionScope,
  ReadyModelScope,
} from "../../lib/modelExecutionScope";
import { track, trackException } from "../../lib/analytics";
import {
  startInvestigation,
  type StartInvestigationRequest,
} from "../../lib/api";
import {
  rootResearchLaunchArchive,
  type RootResearchLaunchHandle,
  type RootResearchIntent,
} from "./rootResearchLaunch";
export interface ResearchComposerProps {
  parentInvestigationId?: string;
  spawnContext?: string;
  placeholder?: string;
  autoFocus?: boolean;
  onSubmitted?: (investigationId: string) => void;
}

type DraftBinding = Readonly<{ scope: ModelExecutionScope; props: object }>;
const UNCERTAIN_START_MESSAGE =
  "Could not confirm the start. The request may have been accepted or charged.";
function reportLaunchTelemetry(report: () => void): void {
  try {
    report();
  } catch {
    // Telemetry cannot change a research start outcome.
  }
}
/** Project private lifecycle observations into visible draft and launch controls. */
function projectComposerState({
  controller,
  question,
  error,
  questionBinding,
  errorBinding,
  scope,
  props,
  busy,
  pending,
  intent,
  editingAllowed,
}: {
  controller: OwnerModelController | undefined;
  question: string;
  error: string | null;
  questionBinding: DraftBinding;
  errorBinding: DraftBinding;
  scope: ModelExecutionScope;
  props: object;
  busy: boolean;
  pending: boolean;
  intent: RootResearchIntent | null;
  editingAllowed: boolean;
}) {
  const rootReady =
    !controller ||
    (controller.inventory.kind === "ready" &&
      controller.isInventoryCurrent(controller.inventory) &&
      (controller.selection.kind === "saved" ||
        controller.selection.kind === "house"));
  const uncertainBlocked =
    !!intent && !rootResearchLaunchArchive.canBegin(intent);
  return {
    question:
      questionBinding.scope === scope && questionBinding.props === props
        ? question
        : "",
    error:
      errorBinding.scope === scope && errorBinding.props === props
        ? error
        : null,
    busy,
    editingDisabled: busy || !editingAllowed,
    showUncertainty: rootResearchLaunchArchive.hasUnresolved() || uncertainBlocked,
    submitDisabled:
      busy ||
      pending ||
      question.trim().length < 3 ||
      !rootReady ||
      uncertainBlocked ||
      !editingAllowed,
  };
}

export function useResearchComposer({
  parentInvestigationId,
  spawnContext,
  onSubmitted,
  controller,
}: ResearchComposerProps & { controller?: OwnerModelController }) {
  useSyncExternalStore(
    rootResearchLaunchArchive.subscribe,
    rootResearchLaunchArchive.getVersion,
    rootResearchLaunchArchive.getVersion,
  );
  const [question, setQuestion] = useState(spawnContext ?? "");
  const questionRef = useRef(question);
  const [error, setErrorState] = useState<string | null>(null);
  const [, renderAction] = useState(0);
  const navigate = useModeNavigate();
  const { modelExecution } = useAuth();
  const renderedScope = modelExecution.current;
  const propsToken = useMemo(
    () =>
      Object.freeze({
        parentInvestigationId,
        spawnContext,
        onSubmitted,
        navigate,
      }),
    [parentInvestigationId, spawnContext, onSubmitted, navigate],
  );
  const committedPropsRef = useRef<typeof propsToken | null>(null);
  const questionBindingRef = useRef({
    scope: modelExecution.readCurrent(),
    props: propsToken,
  });
  const errorBindingRef = useRef({
    scope: modelExecution.readCurrent(),
    props: propsToken,
  });
  const setError = useCallback(
    (message: string | null) => {
      errorBindingRef.current = {
        scope: modelExecution.readCurrent(),
        props: propsToken,
      };
      setErrorState(message);
    },
    [modelExecution, propsToken],
  );
  const initialDraftCommittedRef = useRef(false);
  useLayoutEffect(() => {
    const scope = modelExecution.current;
    if (!initialDraftCommittedRef.current && scope.kind === "ready") {
      initialDraftCommittedRef.current = true;
      questionBindingRef.current = { scope, props: propsToken };
      if (!controller) {
        questionRef.current = spawnContext ?? "";
        setQuestion(spawnContext ?? "");
      }
      renderAction((value) => value + 1);
      return;
    }
    if (
      questionBindingRef.current.scope !== scope ||
      questionBindingRef.current.props !== propsToken
    ) {
      questionBindingRef.current = { scope, props: propsToken };
      questionRef.current = "";
      setQuestion("");
    }
  }, [controller, modelExecution, propsToken, spawnContext]);
  const mountedRef = useRef(false);
  const intentRef = useRef<ReturnType<
    typeof rootResearchLaunchArchive.createIntent
  > | null>(null);
  useLayoutEffect(() => {
    if (!intentRef.current)
      intentRef.current = rootResearchLaunchArchive.createIntent();
  }, []);
  type Action = {
    scope: ReadyModelScope;
    props: typeof propsToken;
    question: string;
    phase: "pending" | "unknown" | "accepted";
    prepared?: Exclude<PreparedModelLaunch, { kind: "blocked" }>;
    handle: RootResearchLaunchHandle;
  };
  const actionRef = useRef<Action | null>(null);
  useLayoutEffect(() => {
    mountedRef.current = true;
    committedPropsRef.current = propsToken;
    return () => {
      mountedRef.current = false;
      if (committedPropsRef.current === propsToken)
        committedPropsRef.current = null;
    };
  }, [propsToken]);
  const admitsCurrentRender = useCallback(
    () =>
      mountedRef.current &&
      committedPropsRef.current === propsToken &&
      renderedScope.kind === "ready" &&
      modelExecution.readCurrent() === renderedScope,
    [modelExecution, propsToken, renderedScope],
  );
  const currentAction = useCallback(
    (action: Action) =>
      actionRef.current === action &&
      mountedRef.current &&
      committedPropsRef.current === action.props &&
      questionRef.current === action.question &&
      modelExecution.readCurrent() === action.scope &&
      (!action.prepared || !!controller?.isCurrent(action.prepared)),
    [controller, modelExecution],
  );
  const submit = useCallback(async () => {
    if (
      !admitsCurrentRender() ||
      questionRef.current !== question ||
      actionRef.current?.phase === "pending" ||
      questionBindingRef.current.scope !== modelExecution.readCurrent()
    )
      return;
    const scope = modelExecution.readCurrent();
    if (scope.kind !== "ready") return;
    const q = question.trim();
    if (q.length < 3) {
      setError("Question is too short. At least 3 characters.");
      return;
    }
    const intent = intentRef.current;
    if (!intent || !rootResearchLaunchArchive.canBegin(intent)) {
      setError("A previous research request may have been accepted or charged.");
      return;
    }
    const request: Readonly<StartInvestigationRequest> = Object.freeze({
      question: q,
      parent_investigation_id: parentInvestigationId ?? undefined,
      spawn_context: spawnContext ?? undefined,
    });
    let prepared: Exclude<PreparedModelLaunch, { kind: "blocked" }> | undefined;
    let handle: RootResearchLaunchHandle | null = null;
    let fields: Readonly<StartInvestigationRequest> = request;
    if (controller) {
      const result = controller.prepareLaunch({
        semanticKey: JSON.stringify({ turn: intent.nonce, request }),
      });
      if (result.kind === "blocked") {
        setError("Choose an available model or the house route before asking.");
        return;
      }
      if (!controller.isCurrent(result) || result.scope !== scope) return;
      prepared = result;
      fields = Object.freeze({
        ...request,
        ...(result.kind === "saved" ? result.fields : {}),
      });
      handle = rootResearchLaunchArchive.begin(intent, fields, result);
    } else {
      handle = rootResearchLaunchArchive.beginChild(intent, request, scope);
    }
    if (!handle) return;
    const action: Action = {
      scope,
      props: propsToken,
      question,
      phase: "pending",
      prepared,
      handle,
    };
    actionRef.current = action;
    setError(null);
    renderAction((value) => value + 1);
    try {
      const response = await startInvestigation(fields);
      const accepted = rootResearchLaunchArchive.accepted(handle, response);
      if (!accepted) {
        rootResearchLaunchArchive.uncertain(handle);
        action.phase = "unknown";
        if (currentAction(action))
          setError(UNCERTAIN_START_MESSAGE);
        return;
      }
      action.phase = "accepted";
      if (!currentAction(action)) return;
      intentRef.current = rootResearchLaunchArchive.createIntent();
      reportLaunchTelemetry(() =>
        track("investigation_started", {
          question_length: q.length,
          has_parent: parentInvestigationId != null,
          has_spawn_context: spawnContext != null,
        }),
      );
      questionRef.current = "";
      setQuestion("");
      if (onSubmitted) onSubmitted(response.investigation_id);
      else navigate(`/inv/${response.investigation_id}`);
    } catch {
      if (action.phase === "accepted") {
        if (
          actionRef.current === action &&
          admitsCurrentRender() &&
          (!action.prepared || controller?.isCurrent(action.prepared))
        ) {
          reportLaunchTelemetry(() =>
            trackException(new Error("Research start completion callback failed.")),
          );
          setError("Research started, but the composer could not open it.");
        }
        return;
      }
      rootResearchLaunchArchive.uncertain(handle);
      action.phase = "unknown";
      if (currentAction(action)) {
        reportLaunchTelemetry(() =>
          trackException(new Error("Research start could not be confirmed.")),
        );
        setError(UNCERTAIN_START_MESSAGE);
      }
    } finally {
      if (currentAction(action)) renderAction((value) => value + 1);
    }
  }, [
    question,
    parentInvestigationId,
    spawnContext,
    controller,
    modelExecution,
    propsToken,
    currentAction,
    navigate,
    onSubmitted,
    setError,
    admitsCurrentRender,
  ]);
  const active = actionRef.current;
  const busy = !!(active?.phase === "pending" && currentAction(active));
  const observedScope = modelExecution.readCurrent();
  const presentation = projectComposerState({
    controller,
    question,
    error,
    questionBinding: questionBindingRef.current,
    errorBinding: errorBindingRef.current,
    scope: observedScope,
    props: propsToken,
    busy,
    pending: active?.phase === "pending",
    intent: intentRef.current,
    editingAllowed:
      renderedScope.kind === "ready" && observedScope === renderedScope,
  });
  const changeQuestion = useCallback(
    (value: string) => {
      if (!admitsCurrentRender()) return;
      questionBindingRef.current = {
        scope: modelExecution.readCurrent(),
        props: propsToken,
      };
      questionRef.current = value;
      setQuestion(value);
      setError(null);
    },
    [modelExecution, propsToken, setError, admitsCurrentRender],
  );
  const startSeparate = useCallback(() => {
    if (!admitsCurrentRender()) return;
    intentRef.current = rootResearchLaunchArchive.createIntent(true);
    actionRef.current = null;
    setError(null);
    renderAction((value) => value + 1);
  }, [setError, admitsCurrentRender]);
  return {
    ...presentation,
    submit,
    changeQuestion,
    startSeparate,
  };
}
