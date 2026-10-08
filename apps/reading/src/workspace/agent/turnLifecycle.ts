/**
 * turnLifecycle.ts — one turn's lifecycle (SPR-07 M3/M8; repair C3).
 *
 * The sprint's M8 rule, by WALL CLOCK: "if no visible reply within 8 s show
 * 'Your agent couldn't get started' with retry". NO_REPLY_MS after send(),
 * with no reply token yet, the phase is `failed` with reason "no_reply" and
 * the failure copy + Retry show (the copy is interview-aware, statusRowFor).
 * The in-flight request is NOT aborted by the fallback: the route runs
 * retrieval and then a whole dispatch (app.py:7218-7256), so a reply that
 * lands later on the SAME request heals the fallback into `done` — a paid
 * call is never thrown away by a timer. retry() aborts the in-flight request
 * before sending again, so a paid call is never double-fired, and a reply
 * from an aborted request is dropped.
 */
import { awaitWorkspaceOwnerSession, isWorkspaceOwnerSession, subscribeWorkspaceOwnerAdmission, workspaceOwnerAdmission, workspaceOwnerSession, type WorkspaceOwnerSession } from "../../lib/accountWorkspaceOwner";

import type { AgentTransport, AgentTransportReply, AgentTransportRequest } from "./agentTransport";

/** refs pattern 18 (sprint M8): the no-reply fallback's wall-clock bound. */
export const NO_REPLY_MS = 8000;

export const WAITING_COPY = "waiting for the whole reply (no streaming yet)";
export const FAILURE_COPY = "Your agent couldn't answer";
export const FAILURE_COPY_INTERVIEW = "Your agent couldn't get started";

export type LifecyclePhase = "idle" | "sent" | "streaming" | "done" | "failed";

/** Why a turn failed: the 8 s wall clock, a transport rejection, or an empty text. */
export type FailureReason = "no_reply" | "transport" | "empty";

export interface LifecycleState {
  phase: LifecyclePhase;
  controller: AbortController | null;
  error: string | null;
  /** Set only while `phase === "failed"`. */
  reason: FailureReason | null;
}

export type LifecycleEvent =
  | { type: "send"; controller: AbortController }
  | { type: "stream" }
  | { type: "done" }
  | { type: "fail"; error: string | null; reason: FailureReason }
  | { type: "abort" };

export const IDLE: LifecycleState = { phase: "idle", controller: null, error: null, reason: null };

export function reduceLifecycle(s: LifecycleState, e: LifecycleEvent): LifecycleState {
  switch (e.type) {
    case "send":
      return { phase: "sent", controller: e.controller, error: null, reason: null };
    case "stream":
      return s.phase === "sent" ? { ...s, phase: "streaming" } : s;
    case "done":
      return { phase: "done", controller: null, error: null, reason: null };
    case "fail":
      return { phase: "failed", controller: null, error: e.error, reason: e.reason };
    case "abort":
      return IDLE;
  }
}

/** The status row's copy for a phase; null when the row shows the turn's
 *  own word instead. */
export function statusRowFor(phase: LifecyclePhase, i: { interview: boolean }): string | null {
  if (phase === "sent") return WAITING_COPY;
  if (phase === "failed") return i.interview ? FAILURE_COPY_INTERVIEW : FAILURE_COPY;
  return null;
}

export interface TurnRunner {
  send(): void;
  /** Aborts the in-flight request (if any) THEN sends once. */
  retry(): void;
  /** Aborts without failing (idle). */
  abort(): void;
  state(): LifecycleState;
  dispose(): void;
}

// A ready notification can still be refused by a later synchronous observer.
// Only the producer's independent confirmation admits resumed work.
let confirmedOwner: WorkspaceOwnerSession | null = null;
function confirmOwner(owner: WorkspaceOwnerSession): void {
  confirmedOwner = null;
  void awaitWorkspaceOwnerSession(owner).then((ok) => {
    if (ok && isWorkspaceOwnerSession(owner)) confirmedOwner = owner;
  });
}
confirmOwner(workspaceOwnerSession());
subscribeWorkspaceOwnerAdmission(({ session }) => confirmOwner(session));
export function isConfirmedAgentOwner(owner: WorkspaceOwnerSession): boolean {
  return owner.subject !== null && confirmedOwner === owner && isWorkspaceOwnerSession(owner);
}

export function createTurnRunner(i: {
  transport: AgentTransport;
  request: () => Omit<AgentTransportRequest, "signal">;
  onState: (s: LifecycleState, reply?: AgentTransportReply) => void;
  owner?: WorkspaceOwnerSession;
  /** Originating mounted pane/incarnation, independent of the owner gate. */
  current?: () => boolean;
}): TurnRunner {
  const owner = i.owner ?? workspaceOwnerSession();
  let state = IDLE;
  let live: AbortController | null = null;
  let noReplyTimer: ReturnType<typeof setTimeout> | null = null;
  let disposed = false;
  const current = () => {
    if (disposed || owner.subject === null) return false;
    const a = workspaceOwnerAdmission();
    if (a.session !== owner || a.state === "failed" || a.state === "retiring") return false;
    try { return i.current?.() ?? true; } catch { return false; }
  };
  const set = (e: LifecycleEvent, reply?: AgentTransportReply) => {
    if (!current() || !isConfirmedAgentOwner(owner)) return;
    state = reduceLifecycle(state, e);
    i.onState(state, reply);
  };
  const clearNoReply = () => {
    if (noReplyTimer !== null) clearTimeout(noReplyTimer);
    noReplyTimer = null;
  };
  const abortInFlight = () => {
    clearNoReply(); live?.abort(); live = null;
  };
  const off = subscribeWorkspaceOwnerAdmission(() => {
    if (!current()) { disposed = true; abortInFlight(); off(); }
  });
  const admitted = (controller: AbortController, run: () => void) => {
    const eligible = () => current() && live === controller && !controller.signal.aborted;
    if (!eligible()) return;
    if (isConfirmedAgentOwner(owner)) { run(); return; }
    void awaitWorkspaceOwnerSession(owner, controller.signal).then((ok) => {
      if (ok && eligible() && isConfirmedAgentOwner(owner)) run();
    });
  };
  const send = () => {
    if (!current()) return;
    abortInFlight();
    const controller = new AbortController();
    live = controller;
    admitted(controller, () => {
      set({ type: "send", controller });
      if (!current() || controller.signal.aborted || live !== controller) return;
      noReplyTimer = setTimeout(() => {
        noReplyTimer = null;
        admitted(controller, () => {
          if (state.phase === "sent") set({ type: "fail", error: null, reason: "no_reply" });
        });
      }, NO_REPLY_MS);
      let reply: Promise<AgentTransportReply>;
      try {
        const request = i.request();
        if (!current() || !isConfirmedAgentOwner(owner) || live !== controller) return;
        reply = i.transport.send({ ...request, signal: controller.signal });
      } catch (error) { reply = Promise.reject(error); }
      reply.then(
        (result) => {
          if (live !== controller || controller.signal.aborted) return;
          clearNoReply();
          admitted(controller, () => {
            set(result.text.trim() ? { type: "done" } : { type: "fail", error: null, reason: "empty" }, result);
            if (live === controller) live = null;
          });
        },
        (error: unknown) => {
          if (live !== controller || controller.signal.aborted) return;
          clearNoReply();
          admitted(controller, () => {
            set({ type: "fail", error: error instanceof Error ? error.message : String(error), reason: "transport" });
            if (live === controller) live = null;
          });
        },
      );
    });
  };
  return {
    send, retry: send,
    abort: () => { abortInFlight(); set({ type: "abort" }); },
    state: () => state,
    dispose: () => { disposed = true; off(); abortInFlight(); },
  };
}
