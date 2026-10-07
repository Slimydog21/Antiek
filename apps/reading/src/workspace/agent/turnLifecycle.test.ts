/** turnLifecycle.test.ts — SPR-07 invariant 10 (fix 1): no wall-clock failure while a fetch is pending; retry aborts first. */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { AgentTransport, AgentTransportReply, AgentTransportRequest } from "./agentTransport";
import { FAILURE_COPY, FAILURE_COPY_INTERVIEW, SLOW_COPY, SLOW_NOTICE_MS, WAITING_COPY, createTurnRunner, statusRowFor, type LifecycleState } from "./turnLifecycle";

function transportResolvingAt(ms: number, reply: Partial<AgentTransportReply> = {}): AgentTransport & { sends: AgentTransportRequest[] } {
  const sends: AgentTransportRequest[] = [];
  return {
    kind: "whole",
    sends,
    send: (req) => {
      sends.push(req);
      return new Promise((resolve, reject) => {
        const t = setTimeout(() => resolve({ text: "a reply", shape: "SYNTHESIS", ...reply }), ms);
        req.signal.addEventListener("abort", () => { clearTimeout(t); reject(new DOMException("aborted", "AbortError")); });
      });
    },
  };
}

const request = () => ({ prompt: "q", history: [], system_context: "" });

beforeEach(() => { vi.useFakeTimers(); });
afterEach(() => { vi.useRealTimers(); });

describe("createTurnRunner", () => {
  it("a transport resolving at 9 000 ms shows the slow notice at 8 000 and never the failure copy", async () => {
    const transport = transportResolvingAt(9000);
    const states: LifecycleState[] = [];
    const runner = createTurnRunner({ transport, request, onState: (s) => states.push(s) });
    runner.send();
    expect(states.at(-1)!.phase).toBe("sent");
    expect(statusRowFor(states.at(-1)!.phase, { interview: false })).toBe(WAITING_COPY);
    await vi.advanceTimersByTimeAsync(SLOW_NOTICE_MS - 1);
    expect(states.at(-1)!.phase).toBe("sent");
    await vi.advanceTimersByTimeAsync(1);
    expect(states.at(-1)!.phase).toBe("slow");
    expect(statusRowFor("slow", { interview: false })).toBe(SLOW_COPY);
    await vi.advanceTimersByTimeAsync(1000);
    expect(states.at(-1)!.phase).toBe("done");
    expect(states.map((s) => s.phase)).not.toContain("failed");
    expect(SLOW_NOTICE_MS).toBe(8000);
  });

  it("retry aborts the in-flight signal and sends exactly one more request", async () => {
    const transport = transportResolvingAt(9000);
    const states: LifecycleState[] = [];
    const runner = createTurnRunner({ transport, request, onState: (s) => states.push(s) });
    runner.send();
    await vi.advanceTimersByTimeAsync(100);
    runner.retry();
    await vi.advanceTimersByTimeAsync(0);
    expect(transport.sends).toHaveLength(2);
    expect(transport.sends[0].signal.aborted).toBe(true);
    expect(transport.sends[1].signal.aborted).toBe(false);
    // The aborted first request never reports failure over the live second.
    expect(states.at(-1)!.phase).toBe("sent");
    await vi.advanceTimersByTimeAsync(9000);
    expect(states.at(-1)!.phase).toBe("done");
  });

  it("a rejected transport and an empty text each fail with Retry copy", async () => {
    const rejecting: AgentTransport = { kind: "whole", send: () => Promise.reject(new Error("HTTP 500")) };
    const states: LifecycleState[] = [];
    const runner = createTurnRunner({ transport: rejecting, request, onState: (s) => states.push(s) });
    runner.send();
    await vi.advanceTimersByTimeAsync(0);
    expect(states.at(-1)).toMatchObject({ phase: "failed", error: "HTTP 500" });
    expect(statusRowFor("failed", { interview: false })).toBe(FAILURE_COPY);
    expect(statusRowFor("failed", { interview: true })).toBe(FAILURE_COPY_INTERVIEW);

    const empty = transportResolvingAt(10, { text: "" });
    const states2: LifecycleState[] = [];
    createTurnRunner({ transport: empty, request, onState: (s) => states2.push(s) }).send();
    await vi.advanceTimersByTimeAsync(10);
    expect(states2.at(-1)!.phase).toBe("failed");
  });

  it("abort is not a failure and dispose cancels the slow timer", async () => {
    const transport = transportResolvingAt(9000);
    const states: LifecycleState[] = [];
    const runner = createTurnRunner({ transport, request, onState: (s) => states.push(s) });
    runner.send();
    runner.abort();
    await vi.advanceTimersByTimeAsync(0);
    expect(states.at(-1)!.phase).toBe("idle");
    runner.send();
    runner.dispose();
    await vi.advanceTimersByTimeAsync(SLOW_NOTICE_MS + 1);
    expect(states.map((s) => s.phase)).not.toContain("slow");
  });
});
