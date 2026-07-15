import { useCallback, useEffect, useState } from "react";

import type { BookCitation } from "../../api/books";

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
  startTurn: (question: string) => string;
  /** Fill in a turn's model reply + citations once the answer lands. */
  completeTurn: (
    messageId: string,
    answer: string,
    citations: BookCitation[],
    grounded: boolean,
    answerId: string | null,
    captureStatus: "captured" | "unavailable",
  ) => void;
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
    try {
      window.sessionStorage.setItem(KEY(documentId), JSON.stringify(state));
    } catch {
      /* private mode — the thread still works in-memory, just won't persist */
    }
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
    (question: string): string => {
      const id = genId("turn");
      mutateActive((msgs) => [
        ...msgs,
        { id, question, answer: null, citations: [], grounded: false },
      ]);
      return id;
    },
    [mutateActive],
  );

  const completeTurn = useCallback(
    (
      messageId: string,
      answer: string,
      citations: BookCitation[],
      grounded: boolean,
      answerId: string | null,
      captureStatus: "captured" | "unavailable",
    ) => {
      mutateActive((msgs) =>
        msgs.map((m) => (m.id === messageId ? {
          ...m,
          answer,
          citations,
          grounded,
          answer_id: answerId ?? undefined,
          capture_unavailable: captureStatus === "unavailable",
        } : m)),
      );
    },
    [mutateActive],
  );

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
    setJudgment,
    failTurn,
    branchFrom,
    setActiveBranch,
    reset,
  };
}
