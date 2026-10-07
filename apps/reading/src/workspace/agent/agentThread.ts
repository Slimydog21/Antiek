/**
 * agentThread.ts — the pane's own thread store (SPR-07 M3).
 *
 * NOT useThoughtPartnerThread: that hook is keyed per reading document and
 * shared with the sidecar, and its failTurn writes error text into the
 * history that reaches the wire. Here a failed turn keeps `answer: null`
 * and `error`, so historyFor() never ships it. In memory for the session.
 */
import { create } from "zustand";

import type { AiAction } from "../../components/ai/aiActions";
import type { ThoughtPartnerShape } from "../../hooks/useThoughtPartnerThread";
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
}

export interface CompleteTurnInput {
  answer: string;
  shape: ThoughtPartnerShape;
  actions: AiAction[];
  libraryRetrievalStatus?: string | null;
}

interface AgentThreadState {
  threads: Record<string, AgentTurn[]>;
  startTurn: (key: string, question: string, opts?: { hidden?: boolean }) => string;
  streamTurn: (key: string, id: string, partial: string) => void;
  completeTurn: (key: string, id: string, input: CompleteTurnInput) => void;
  failTurn: (key: string, id: string, error: string | null) => void;
  clearThread: (key: string) => void;
  reset: () => void;
}

let serial = 0;
const now = () => (typeof performance !== "undefined" ? performance.now() : Date.now());

export const useAgentThreads = create<AgentThreadState>()((set, get) => ({
  threads: {},

  startTurn: (key, question, opts) => {
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

  streamTurn: (key, id, partial) =>
    set((s) => ({
      threads: { ...s.threads, [key]: (s.threads[key] ?? []).map((t) => (t.id === id ? { ...t, status: "streaming", answer: partial } : t)) },
    })),

  completeTurn: (key, id, input) =>
    set((s) => ({
      threads: {
        ...s.threads,
        [key]: (s.threads[key] ?? []).map((t) =>
          t.id === id
            ? { ...t, status: "done", answer: input.answer, shape: input.shape, actions: input.actions, endedAt: now(),
                ...(input.libraryRetrievalStatus !== undefined ? { libraryRetrievalStatus: input.libraryRetrievalStatus } : {}) }
            : t,
        ),
      },
    })),

  failTurn: (key, id, error) =>
    set((s) => ({
      threads: { ...s.threads, [key]: (s.threads[key] ?? []).map((t) => (t.id === id ? { ...t, status: "failed", answer: null, error, endedAt: now() } : t)) },
    })),

  clearThread: (key) => set((s) => { const { [key]: _drop, ...rest } = s.threads; return { threads: rest }; }),
  reset: () => set({ threads: {} }),
}));

/** The wire history: the last HISTORY_CAP DONE turns. Failed turns never reach it. */
export function historyFor(turns: readonly AgentTurn[] | undefined): Array<{ question: string; answer: string }> {
  return (turns ?? [])
    .filter((t): t is AgentTurn & { answer: string } => t.status === "done" && typeof t.answer === "string" && t.answer.trim().length > 0)
    .slice(-HISTORY_CAP)
    .map((t) => ({ question: t.question, answer: t.answer }));
}
