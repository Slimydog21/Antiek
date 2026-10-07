/**
 * turnLifecycle.ts — one turn's lifecycle (SPR-07 M3/M8, fix 1).
 *
 * The route runs retrieval and then a whole dispatch (app.py:7218-7256), so
 * a slow reply is the normal case, not a failure. The failure copy is
 * entered ONLY on transport rejection, abort-by-dispose, or an empty text;
 * NEVER by wall clock while the fetch is pending. At SLOW_NOTICE_MS the
 * status row says it is still waiting. retry() aborts the in-flight
 * request before sending again, so a paid call is never double-fired.
 */
import type { AgentTransport, AgentTransportReply, AgentTransportRequest } from "./agentTransport";

export const SLOW_NOTICE_MS = 8000;

export const WAITING_COPY = "waiting for the whole reply (no streaming yet)";
export const SLOW_COPY = "still waiting for the whole reply (no streaming yet)";
export const FAILURE_COPY = "Your agent couldn't answer";
export const FAILURE_COPY_INTERVIEW = "Your agent couldn't get started";

export type LifecyclePhase = "idle" | "sent" | "slow" | "streaming" | "done" | "failed";

export interface LifecycleState {
  phase: LifecyclePhase;
  controller: AbortController | null;
  error: string | null;
}

export type LifecycleEvent =
  | { type: "send"; controller: AbortController }
  | { type: "slow" }
  | { type: "stream" }
  | { type: "done" }
  | { type: "fail"; error: string | null }
  | { type: "abort" };

export const IDLE: LifecycleState = { phase: "idle", controller: null, error: null };

export function reduceLifecycle(s: LifecycleState, e: LifecycleEvent): LifecycleState {
  switch (e.type) {
    case "send":
      return { phase: "sent", controller: e.controller, error: null };
    case "slow":
      return s.phase === "sent" ? { ...s, phase: "slow" } : s;
    case "stream":
      return s.phase === "sent" || s.phase === "slow" ? { ...s, phase: "streaming" } : s;
    case "done":
      return { phase: "done", controller: null, error: null };
    case "fail":
      return { phase: "failed", controller: null, error: e.error };
    case "abort":
      return IDLE;
  }
}

/** The status row's copy for a phase; null when the row shows the turn's
 *  own word instead. */
export function statusRowFor(phase: LifecyclePhase, i: { interview: boolean }): string | null {
  if (phase === "sent") return WAITING_COPY;
  if (phase === "slow") return SLOW_COPY;
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

export function createTurnRunner(i: {
  transport: AgentTransport;
  request: () => Omit<AgentTransportRequest, "signal">;
  onState: (s: LifecycleState, reply?: AgentTransportReply) => void;
}): TurnRunner {
  let state = IDLE;
  let slowTimer: ReturnType<typeof setTimeout> | null = null;
  let disposed = false;
  const set = (e: LifecycleEvent, reply?: AgentTransportReply) => {
    state = reduceLifecycle(state, e);
    i.onState(state, reply);
  };
  const clearSlow = () => {
    if (slowTimer !== null) clearTimeout(slowTimer);
    slowTimer = null;
  };
  const abortInFlight = () => {
    clearSlow();
    state.controller?.abort();
  };
  const send = () => {
    if (disposed) return;
    abortInFlight();
    const controller = new AbortController();
    set({ type: "send", controller });
    slowTimer = setTimeout(() => {
      slowTimer = null;
      if (state.controller === controller) set({ type: "slow" });
    }, SLOW_NOTICE_MS);
    i.transport.send({ ...i.request(), signal: controller.signal }).then(
      (reply) => {
        if (controller.signal.aborted || state.controller !== controller) return;
        clearSlow();
        if (!reply.text.trim()) set({ type: "fail", error: null });
        else set({ type: "done" }, reply);
      },
      (err: unknown) => {
        // An aborted request belongs to retry()/abort(): never a failure.
        if (controller.signal.aborted || state.controller !== controller) return;
        clearSlow();
        set({ type: "fail", error: err instanceof Error ? err.message : String(err) });
      },
    );
  };
  return {
    send,
    retry: send,
    abort: () => {
      abortInFlight();
      set({ type: "abort" });
    },
    state: () => state,
    dispose: () => {
      disposed = true;
      abortInFlight();
    },
  };
}
