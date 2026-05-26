/**
 * useEventStream.test.ts — the live socket's reconnect/resume behaviour
 * (SPR-02 M2 reconnect-idempotency gate).
 *
 * jsdom has no WebSocket, so we install a controllable fake on globalThis and
 * drive the hook through a drop → reconnect cycle. The properties pinned:
 *   - a dropped socket reconnects (status goes connecting → open) and the
 *     reconnect counter advances;
 *   - events accumulated before the drop are NOT lost on reconnect (the hook
 *     accumulates, it does not reset on a transient close);
 *   - ping keepalive frames are dropped (never enter the event list);
 *   - the dedupe by event_id that protects the narration (useInvestigation +
 *     ThinkingStream) means a replayed event after reconnect narrates once —
 *     proven here at the data layer by asserting the event identity is stable
 *     across the reconnect so the downstream Set<event_id> dedupe is correct.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";

import { useEventStream } from "./useEventStream";

// ── Controllable fake WebSocket ────────────────────────────────────────────

class FakeWebSocket {
  static OPEN = 1;
  static instances: FakeWebSocket[] = [];

  readyState = 0;
  onopen: (() => void) | null = null;
  onmessage: ((e: { data: string }) => void) | null = null;
  onerror: (() => void) | null = null;
  onclose: (() => void) | null = null;

  constructor(public url: string) {
    FakeWebSocket.instances.push(this);
  }

  // Test-driver helpers.
  open() {
    this.readyState = FakeWebSocket.OPEN;
    this.onopen?.();
  }
  deliver(obj: unknown) {
    this.onmessage?.({ data: JSON.stringify(obj) });
  }
  drop() {
    this.readyState = 3;
    this.onclose?.();
  }
  close() {
    this.readyState = 3;
  }
}

const NATIVE_WS = globalThis.WebSocket;

beforeEach(() => {
  FakeWebSocket.instances = [];
  vi.useFakeTimers();
  // @ts-expect-error — installing a test double over the DOM type.
  globalThis.WebSocket = FakeWebSocket;
});

afterEach(() => {
  vi.useRealTimers();
  globalThis.WebSocket = NATIVE_WS;
});

const frame = (id: string, seq: number) => ({
  event_id: id,
  investigation_id: "inv-1",
  action_type: "evidence.retrieve.delivered",
  payload: { supporting_claims: [], evidentiary_gaps: [] },
  param_version: "v1",
  emitted_at: `2026-05-26T00:00:0${seq}Z`,
});

describe("useEventStream — reconnect / resume (M2)", () => {
  it("reconnects after a drop without losing accumulated events", () => {
    const { result } = renderHook(() => useEventStream("inv-1"));

    // First socket opens and delivers two events.
    const ws1 = FakeWebSocket.instances[0];
    act(() => ws1.open());
    expect(result.current.status).toBe("open");
    act(() => ws1.deliver(frame("e1", 1)));
    act(() => ws1.deliver(frame("e2", 2)));
    expect(result.current.events.map((e) => e.event_id)).toEqual(["e1", "e2"]);

    // Socket drops. The hook schedules a backoff reconnect.
    act(() => ws1.drop());
    expect(result.current.status).toBe("closed");

    // Advance past the first backoff (1s) so the reconnect fires.
    act(() => vi.advanceTimersByTime(1_000));
    expect(FakeWebSocket.instances.length).toBe(2);
    expect(result.current.reconnects).toBe(1);

    // The new socket opens — the events from before the drop are still there.
    const ws2 = FakeWebSocket.instances[1];
    act(() => ws2.open());
    expect(result.current.status).toBe("open");
    expect(result.current.events.map((e) => e.event_id)).toEqual(["e1", "e2"]);
  });

  it("a replayed event after reconnect carries the same event_id (so downstream dedupe is exact)", () => {
    const { result } = renderHook(() => useEventStream("inv-1"));
    const ws1 = FakeWebSocket.instances[0];
    act(() => ws1.open());
    act(() => ws1.deliver(frame("e1", 1)));

    act(() => ws1.drop());
    act(() => vi.advanceTimersByTime(1_000));
    const ws2 = FakeWebSocket.instances[1];
    act(() => ws2.open());

    // The server replays e1 across the reconnect window (at-least-once).
    act(() => ws2.deliver(frame("e1", 1)));
    act(() => ws2.deliver(frame("e2", 2)));

    // useEventStream itself is append-only (it does not dedupe — that is
    // useInvestigation's job). The invariant that makes the dedupe EXACT is
    // that the replayed frame keeps the same event_id, so a Set<event_id>
    // collapses it. Prove the identity is stable:
    const ids = result.current.events.map((e) => e.event_id);
    expect(ids).toEqual(["e1", "e1", "e2"]);
    const deduped = [...new Set(ids)];
    expect(deduped).toEqual(["e1", "e2"]); // one e1 — no double narration
  });

  it("drops ping keepalive frames — they never enter the event list", () => {
    const { result } = renderHook(() => useEventStream("inv-1"));
    const ws1 = FakeWebSocket.instances[0];
    act(() => ws1.open());
    act(() => ws1.deliver({ type: "ping" }));
    act(() => ws1.deliver(frame("e1", 1)));
    act(() => ws1.deliver({ type: "ping" }));
    expect(result.current.events.map((e) => e.event_id)).toEqual(["e1"]);
  });

  it("backoff grows across CONSECUTIVE failed reconnects (1s → 2s), and resets on a successful open", () => {
    renderHook(() => useEventStream("inv-1"));
    // ws1 opens then drops → first backoff is 1s.
    const ws1 = FakeWebSocket.instances[0];
    act(() => ws1.open());
    act(() => ws1.drop());
    act(() => vi.advanceTimersByTime(1_000));
    expect(FakeWebSocket.instances.length).toBe(2);

    // ws2 never opens — it drops immediately. The next backoff is 2s, so at
    // 1s there must be NO new socket; only at 2s does it reconnect.
    const ws2 = FakeWebSocket.instances[1];
    act(() => ws2.drop());
    act(() => vi.advanceTimersByTime(1_000));
    expect(FakeWebSocket.instances.length).toBe(2);
    act(() => vi.advanceTimersByTime(1_000));
    expect(FakeWebSocket.instances.length).toBe(3);

    // ws3 opens successfully — that resets the backoff. A subsequent drop
    // reconnects after 1s again, not 4s.
    const ws3 = FakeWebSocket.instances[2];
    act(() => ws3.open());
    act(() => ws3.drop());
    act(() => vi.advanceTimersByTime(1_000));
    expect(FakeWebSocket.instances.length).toBe(4);
  });
});
