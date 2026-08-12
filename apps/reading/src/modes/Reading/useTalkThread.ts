import { useCallback, useEffect, useState } from "react";

import type {
  BookCitation,
  BookModelOperationState,
  BookModelReceipt,
  DeepBookOperationStatus,
  PrimeReceipt,
  TalkTurn,
  UserModelChoice,
} from "../../api/books";

/**
 * useTalkThread — the MULTI-TURN talk-to-book conversation, persisted per book
 * in SESSION state (Read SPR-08 M2).
 *
 * WHY SESSION STATE, NOT A SUBSTRATE EVENT (operator decision): the running
 * conversation is EPHEMERAL reader view-state — the same class as the reading
 * position (`usePosition`'s `antiek.read.pos.${documentId}`). It is the floating
 * bookmark's pivot: it follows the reader across page navigation so a thread
 * survives turning pages, but it is NOT substrate truth. So it rides
 * sessionStorage (the usePosition precedent), NOT a new typed event. The
 * single-writer DuckDB invariant is untouched — nothing here writes the graph.
 * (Contrast: the SPR-04 selection FloatMenu Dialogue stays ONE-SHOT and does
 * not persist; the multi-turn thread is THIS new book-level surface.)
 *
 * BRANCHING ("what about that?"): a turn can be a TANGENT off an earlier turn.
 * A branch forks a new thread seeded from the conversation UP TO the branch
 * point, so a "what about that?" follow-up explores without losing the trunk.
 * The active branch is what the bookmark carries; the trunk is preserved so the
 * reader can return to it.
 */

export interface TalkMessage {
  /** A stable id for React keys + branch anchoring. */
  id: string;
  /** The reader's question — user-sourced. */
  question: string;
  /** The model's reply — model-sourced. Null while the turn is in flight. */
  answer: string | null;
  /** Durable event id returned by the server. Missing only on legacy sessions. */
  answer_id?: string;
  capture_unavailable?: boolean;
  judgment?: "good" | "bad";
  /** Page-level citations for the answer (empty until the reply lands). */
  citations: BookCitation[];
  /** False when the answer was ungrounded (no extractable text / withheld) —
   * surfaced honestly, never dressed up as a grounded reply. */
  grounded: boolean;
  /** Stable idempotency identity for a selected-model dispatch. */
  operation_id?: string;
  /** Safe dispatch provenance returned by the server. Absent on old sessions. */
  model_receipt?: BookModelReceipt | null;
  model_choice?: UserModelChoice;
  model_operation_state?: BookModelOperationState | "requesting";
  mode?: "ask" | "deep";
  prime_receipt?: PrimeReceipt | null;
  /** Exact safe request inputs required to resume the same paid operation. */
  deep_request?: {
    history: TalkTurn[];
    max_cost_micro_usd?: number;
    prime_operation_id?: string;
    prime_model_choice?: UserModelChoice;
  };
  deep_operation_status?: DeepBookOperationStatus;
  operation_not_found_checks?: number;
  operation_first_not_found_at?: number;
}

export interface TalkBranch {
  branch_id: string;
  /** The message id this branch forked from (null for the trunk). */
  forked_from: string | null;
  messages: TalkMessage[];
}

export interface TalkThreadState {
  branches: TalkBranch[];
  active_branch_id: string;
}

const KEY = (documentId: string) => `antiek.read.talk.${documentId}`;
const TRUNK = "trunk";

function emptyState(): TalkThreadState {
  return { branches: [{ branch_id: TRUNK, forked_from: null, messages: [] }], active_branch_id: TRUNK };
}

function readStored(documentId: string): TalkThreadState {
  try {
    const raw = window.sessionStorage.getItem(KEY(documentId));
    if (!raw) return emptyState();
    const parsed = JSON.parse(raw) as TalkThreadState;
    if (!parsed.branches?.length || !parsed.active_branch_id) return emptyState();
    return parsed;
  } catch {
    return emptyState();
  }
}

function writeStored(documentId: string, state: TalkThreadState): void {
  try {
    window.sessionStorage.setItem(KEY(documentId), JSON.stringify(state));
  } catch {
    /* private mode — the thread still works in-memory, just won't persist */
  }
}

function genId(prefix: string): string {
  const rand =
    typeof crypto !== "undefined" && crypto.randomUUID
      ? crypto.randomUUID().slice(0, 8)
      : Math.random().toString(36).slice(2, 10);
  return `${prefix}-${rand}`;
}

export interface UseTalkThread {
  /** The messages of the ACTIVE branch (what the bookmark shows). */
  messages: TalkMessage[];
  /** The full thread state (all branches) — for the bookmark's branch picker. */
  state: TalkThreadState;
  activeBranchId: string;
  /** Append a user question (answer pending) to the active branch; returns the
   * new message id so the caller can fill in the reply. */
  startTurn: (question: string, operationId?: string, modelChoice?: UserModelChoice, mode?: "ask" | "deep", deepRequest?: TalkMessage["deep_request"]) => string;
  /** Fill in a turn's model reply + citations once the answer lands. */
  completeTurn: (
    messageId: string,
    answer: string,
    citations: BookCitation[],
    grounded: boolean,
    answerId: string | null,
    captureStatus: "captured" | "unavailable",
    modelReceipt?: BookModelReceipt | null,
    primeReceipt?: PrimeReceipt | null,
  ) => void;
  setModelOperationState: (messageId: string, state: BookModelOperationState) => void;
  setPrimeOperationReceipt: (messageId: string, receipt: PrimeReceipt) => void;
  setDeepOperationStatus: (messageId: string, status: DeepBookOperationStatus) => void;
  markModelOperationNotFound: (messageId: string) => void;
  abandonMissingModelOperation: (messageId: string) => void;
  setJudgment: (messageId: string, verdict: "good" | "bad") => void;
  /** Mark a turn failed (drops the pending message so the thread isn't stuck). */
  failTurn: (messageId: string) => void;
  /** Fork a tangential branch from a message ("what about that?"). The new
   * branch is seeded with the active branch's messages UP TO and INCLUDING the
   * fork point, and becomes active. The trunk is preserved. */
  branchFrom: (messageId: string) => void;
  /** Switch the active branch (return to the trunk / another tangent). */
  setActiveBranch: (branchId: string) => void;
  /** Clear the whole conversation (drops session state). */
  reset: () => void;
}

export function useTalkThread(documentId: string): UseTalkThread {
  const [state, setState] = useState<TalkThreadState>(() => readStored(documentId));

  // Restore the document's saved thread when the book changes.
  useEffect(() => {
    setState(readStored(documentId));
  }, [documentId]);

  // Persist on every change (the bookmark carries it across navigation).
  useEffect(() => {
    writeStored(documentId, state);
  }, [documentId, state]);

  const activeBranch =
    state.branches.find((b) => b.branch_id === state.active_branch_id) ?? state.branches[0];

  const mutateActive = useCallback(
    (fn: (msgs: TalkMessage[]) => TalkMessage[]) => {
      setState((prev) => ({
        ...prev,
        branches: prev.branches.map((b) =>
          b.branch_id === prev.active_branch_id ? { ...b, messages: fn(b.messages) } : b,
        ),
      }));
    },
    [],
  );

  const startTurn = useCallback(
    (question: string, operationId?: string, modelChoice?: UserModelChoice, mode: "ask" | "deep" = "ask", deepRequest?: TalkMessage["deep_request"]): string => {
      const id = genId("turn");
      const message: TalkMessage = {
        id,
        question,
        answer: null,
        citations: [],
        grounded: false,
        mode,
        ...(deepRequest ? { deep_request: {
          history: deepRequest.history.map((turn) => ({ ...turn })),
          ...(deepRequest.max_cost_micro_usd !== undefined
            ? { max_cost_micro_usd: deepRequest.max_cost_micro_usd } : {}),
          ...(deepRequest.prime_operation_id
            ? { prime_operation_id: deepRequest.prime_operation_id } : {}),
          ...(deepRequest.prime_model_choice
            ? { prime_model_choice: { ...deepRequest.prime_model_choice } } : {}),
        } } : {}),
        ...(operationId ? { operation_id: operationId } : {}),
        ...(modelChoice ? {
          model_choice: { ...modelChoice },
          model_operation_state: "requesting" as const,
        } : {}),
      };
      const next = {
        ...state,
        branches: state.branches.map((branch) =>
          branch.branch_id === state.active_branch_id
            ? { ...branch, messages: [...branch.messages, message] }
            : branch,
        ),
      };
      // Selected-model operation identity must be durable before dispatch so
      // a reload/retry cannot accidentally create a second billable action.
      writeStored(documentId, next);
      setState(next);
      return id;
    },
    [documentId, state],
  );

  const completeTurn = useCallback(
    (
      messageId: string,
      answer: string,
      citations: BookCitation[],
      grounded: boolean,
      answerId: string | null,
      captureStatus: "captured" | "unavailable",
      modelReceipt?: BookModelReceipt | null,
      primeReceipt?: PrimeReceipt | null,
    ) => {
      mutateActive((msgs) =>
        msgs.map((m) => (m.id === messageId ? {
          ...m,
          answer,
          citations,
          grounded,
          answer_id: answerId ?? undefined,
          capture_unavailable: captureStatus === "unavailable",
          model_operation_state: undefined,
          model_receipt: modelReceipt ? {
            authority: modelReceipt.authority,
            requested_provider_id: modelReceipt.requested_provider_id,
            requested_model_id: modelReceipt.requested_model_id,
            actual_provider_id: modelReceipt.actual_provider_id,
            actual_model_id: modelReceipt.actual_model_id,
            authority_digest: null,
          } : null,
          prime_receipt: primeReceipt ? { ...primeReceipt } : null,
        } : m)),
      );
    },
    [mutateActive],
  );

  const setModelOperationState = useCallback(
    (messageId: string, operationState: BookModelOperationState) => {
      setState((prev) => {
        const current = prev.branches.flatMap((branch) => branch.messages)
          .find((message) => message.id === messageId);
        if (!current || current.answer !== null || current.model_operation_state === operationState) {
          return prev;
        }
        return {
          ...prev,
          branches: prev.branches.map((branch) => ({
          ...branch,
          messages: branch.messages.map((message) =>
            message.id === messageId && message.answer === null
              ? { ...message, model_operation_state: operationState }
              : message,
          ),
          })),
        };
      });
    },
    [],
  );

  const setPrimeOperationReceipt = useCallback((messageId: string, receipt: PrimeReceipt) => {
    const mapped: BookModelOperationState = receipt.state === "authorized" ? "prepared"
      : receipt.state === "cancelled" ? "cancelled"
        : receipt.state === "unknown" ? "unknown" : "settlement_pending";
    setState((prev) => {
      const current = prev.branches.flatMap((branch) => branch.messages)
        .find((message) => message.id === messageId);
      if (!current || current.answer !== null) return prev;
      const prior = current?.prime_receipt;
      if (current?.model_operation_state === mapped && prior &&
        prior.state === receipt.state && prior.updated_at_ms === receipt.updated_at_ms &&
        prior.held_micro_usd === receipt.held_micro_usd &&
        prior.charged_micro_usd === receipt.charged_micro_usd) return prev;
      return {
        ...prev,
        branches: prev.branches.map((branch) => ({
        ...branch,
        messages: branch.messages.map((message) => {
          if (message.id !== messageId) return message;
          return { ...message, prime_receipt: { ...receipt }, model_operation_state: mapped };
        }),
        })),
      };
    });
  }, []);

  const setDeepOperationStatus = useCallback((messageId: string, status: DeepBookOperationStatus) => {
    setState((prev) => {
      const current = prev.branches.flatMap((branch) => branch.messages)
        .find((message) => message.id === messageId);
      if (!current || current.answer !== null ||
        (current.deep_operation_status?.state === status.state &&
          current.deep_operation_status.updated_at_ms === status.updated_at_ms &&
          current.deep_operation_status.lease_expires_at_ms === status.lease_expires_at_ms &&
          current.deep_operation_status.resumable === status.resumable)) return prev;
      return {
        ...prev,
        branches: prev.branches.map((branch) => ({
          ...branch,
          messages: branch.messages.map((message) => message.id === messageId
            ? { ...message, deep_operation_status: { ...status } }
            : message),
        })),
      };
    });
  }, []);

  const markModelOperationNotFound = useCallback((messageId: string) => {
    setState((prev) => ({
      ...prev,
      branches: prev.branches.map((branch) => ({
        ...branch,
        messages: branch.messages.map((message) => message.id === messageId &&
          (message.model_operation_state === "unknown" || message.model_operation_state === "requesting")
          ? (() => {
              const first = message.operation_first_not_found_at ?? Date.now();
              const priorChecks = message.operation_not_found_checks ?? 0;
              const separatedCheck = priorChecks === 0 || Date.now() - first >= 3_000;
              return {
                ...message,
                operation_not_found_checks: priorChecks + (separatedCheck ? 1 : 0),
                operation_first_not_found_at: first,
              };
            })()
          : message),
      })),
    }));
  }, []);

  const abandonMissingModelOperation = useCallback((messageId: string) => {
    setState((prev) => ({
      ...prev,
      branches: prev.branches.map((branch) => ({
        ...branch,
        messages: branch.messages.filter((message) => message.id !== messageId ||
          !(
            (message.model_operation_state === "unknown" || message.model_operation_state === "requesting") &&
            (message.operation_not_found_checks ?? 0) >= 2
          )),
      })),
    }));
  }, []);

  const setJudgment = useCallback(
    (messageId: string, verdict: "good" | "bad") => {
      mutateActive((msgs) =>
        msgs.map((m) => (m.id === messageId ? { ...m, judgment: verdict } : m)),
      );
    },
    [mutateActive],
  );

  const failTurn = useCallback(
    (messageId: string) => {
      mutateActive((msgs) => msgs.filter((m) => m.id !== messageId));
    },
    [mutateActive],
  );

  const branchFrom = useCallback(
    (messageId: string) => {
      setState((prev) => {
        const active =
          prev.branches.find((b) => b.branch_id === prev.active_branch_id) ?? prev.branches[0];
        const idx = active.messages.findIndex((m) => m.id === messageId);
        if (idx < 0) return prev;
        const seed = active.messages.slice(0, idx + 1).map((m) => ({ ...m }));
        const branchId = genId("branch");
        return {
          branches: [
            ...prev.branches,
            { branch_id: branchId, forked_from: messageId, messages: seed },
          ],
          active_branch_id: branchId,
        };
      });
    },
    [],
  );

  const setActiveBranch = useCallback((branchId: string) => {
    setState((prev) =>
      prev.branches.some((b) => b.branch_id === branchId)
        ? { ...prev, active_branch_id: branchId }
        : prev,
    );
  }, []);

  const reset = useCallback(() => {
    setState(emptyState());
  }, []);

  return {
    messages: activeBranch.messages,
    state,
    activeBranchId: state.active_branch_id,
    startTurn,
    completeTurn,
    setModelOperationState,
    setPrimeOperationReceipt,
    setDeepOperationStatus,
    markModelOperationNotFound,
    abandonMissingModelOperation,
    setJudgment,
    failTurn,
    branchFrom,
    setActiveBranch,
    reset,
  };
}
