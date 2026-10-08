/**
 * agentThreadStore.ts — the pane's own thread store (SPR-07 M3).
 *
 * NOT useThoughtPartnerThread: that hook is keyed per reading document and
 * shared with the sidecar, and its failTurn writes error text into the
 * history that reaches the wire. Here a failed turn keeps `answer: null`
 * and `error`, so historyFor() never ships it. In memory for the session.
 */
import { create } from "zustand";
import { isWorkspaceOwnerSession, subscribeWorkspaceOwnerAdmission, workspaceOwnerSession, type WorkspaceOwnerSession } from "../../lib/accountWorkspaceOwner";

import type { AiAction } from "../../components/ai/aiActions";
import type { ThoughtPartnerShape } from "../../hooks/useThoughtPartnerThread";
import type { OptionCard } from "./interviewMode";
import { statusWordFor, type StatusWord, type TurnStatus } from "./statusWords";

/** The client's cap: the server builds history straight from req.history (app.py:7211-7214). */
export const HISTORY_CAP = 8;

export interface ToolRow {
  id: string;
  name: string;
  status: "running" | "done" | "failed";
  detail?: string;
}

export interface AgentTurn {
  id: string;
  question: string;
  answer: string | null;
  shape: ThoughtPartnerShape;
  status: TurnStatus;
  statusWord: StatusWord;
  startedAt: number;
  endedAt?: number;
  actions: AiAction[];
  tools: ToolRow[];
  /** The interview's first turn: in history once done, never rendered as a user turn. */
  hidden?: boolean;
  error?: string | null;
  libraryRetrievalStatus?: string | null;
  /** Interview mode: the @@options card the reply carried (parsed once, at completion). */
  optionCard?: OptionCard;
}

export interface CompleteTurnInput {
  answer: string;
  shape: ThoughtPartnerShape;
  actions: AiAction[];
  libraryRetrievalStatus?: string | null;
  optionCard?: OptionCard;
}

interface AgentThreadState {
  owner: WorkspaceOwnerSession | null;
  threads: Record<string, AgentTurn[]>;
  startTurn: (key: string, question: string, opts?: { hidden?: boolean }, owner?: WorkspaceOwnerSession) => string | null;
  streamTurn: (key: string, id: string | null, partial: string, owner?: WorkspaceOwnerSession) => void;
  completeTurn: (key: string, id: string | null, input: CompleteTurnInput, owner?: WorkspaceOwnerSession) => void;
  failTurn: (key: string, id: string | null, error: string | null, owner?: WorkspaceOwnerSession) => void;
  /** A retry re-opens the failed turn in place (pending, no answer, no error). */
  reopenTurn: (key: string, id: string | null, owner?: WorkspaceOwnerSession) => void;
  clearThread: (key: string) => void;
  reset: () => void;
}

let serial = 0;
const now = () => (typeof performance !== "undefined" ? performance.now() : Date.now());

function admitted(owner: WorkspaceOwnerSession, stored: WorkspaceOwnerSession | null): boolean {
  return owner.subject !== null && owner === stored && isWorkspaceOwnerSession(owner);
}

export const useAgentThreads = create<AgentThreadState>()((set, get) => ({
  owner: workspaceOwnerSession(),
  threads: {},

  startTurn: (key, question, opts, owner = workspaceOwnerSession()) => {
    if (!admitted(owner, get().owner)) return null;
    const turns = get().threads[key] ?? [];
    const id = `turn-${++serial}`;
    const turn: AgentTurn = {
      id, question, answer: null, shape: "SYNTHESIS", status: "pending",
      statusWord: statusWordFor(turns.length), startedAt: now(), actions: [], tools: [],
      ...(opts?.hidden ? { hidden: true } : {}),
    };
    set((s) => ({ threads: { ...s.threads, [key]: [...turns, turn] } }));
    return id;
  },

  /** A late reply healing the 8 s fallback streams into a FAILED turn: the
   *  turn runs again, so failTurn's endedAt and error are cleared here (the
   *  elapsed timer reads endedAt; completeTurn re-stamps it). */
  streamTurn: (key, id, partial, owner = workspaceOwnerSession()) => {
    if (id === null || !admitted(owner, get().owner)) return;
    set((s) => ({
      threads: { ...s.threads, [key]: (s.threads[key] ?? []).map((t) => (t.id === id ? { ...t, status: "streaming", answer: partial, error: null, endedAt: undefined } : t)) },
    }));
  },

  completeTurn: (key, id, input, owner = workspaceOwnerSession()) => {
    if (id === null || !admitted(owner, get().owner)) return;
    set((s) => ({
      threads: {
        ...s.threads,
        [key]: (s.threads[key] ?? []).map((t) =>
          t.id === id
            ? { ...t, status: "done", answer: input.answer, shape: input.shape, actions: input.actions, endedAt: now(),
                ...(input.libraryRetrievalStatus !== undefined ? { libraryRetrievalStatus: input.libraryRetrievalStatus } : {}),
                ...(input.optionCard ? { optionCard: input.optionCard } : {}) }
            : t,
        ),
      },
    }));
  },

  failTurn: (key, id, error, owner = workspaceOwnerSession()) => {
    if (id === null || !admitted(owner, get().owner)) return;
    set((s) => ({
      threads: { ...s.threads, [key]: (s.threads[key] ?? []).map((t) => (t.id === id ? { ...t, status: "failed", answer: null, error, endedAt: now() } : t)) },
    }));
  },

  reopenTurn: (key, id, owner = workspaceOwnerSession()) => {
    if (id === null || !admitted(owner, get().owner)) return;
    set((s) => ({
      threads: { ...s.threads, [key]: (s.threads[key] ?? []).map((t) => (t.id === id ? { ...t, status: "pending", answer: null, error: null, endedAt: undefined } : t)) },
    }));
  },

  clearThread: (key) => set((s) => { const { [key]: _drop, ...rest } = s.threads; return { threads: rest }; }),
  reset: () => set({ owner: workspaceOwnerSession(), threads: {} }),
}));

// Retire synchronously before another token can render or collect history.
// Suspension preserves the same token's body but never admits a mutation.
subscribeWorkspaceOwnerAdmission(({ session, state }) => {
  const current = useAgentThreads.getState();
  if (state === "retiring" || state === "failed" || session.subject === null) {
    useAgentThreads.setState({ owner: null, threads: {} });
  } else if (current.owner !== session) {
    useAgentThreads.setState({ owner: session, threads: {} });
  }
});

/** The wire history: the last HISTORY_CAP DONE turns. Failed turns never reach it. */
export function historyFor(turns: readonly AgentTurn[] | undefined): Array<{ question: string; answer: string }> {
  return (turns ?? [])
    .filter((t): t is AgentTurn & { answer: string } => t.status === "done" && typeof t.answer === "string" && t.answer.trim().length > 0)
    .slice(-HISTORY_CAP)
    .map((t) => ({ question: t.question, answer: t.answer }));
}
