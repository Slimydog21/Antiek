/**
 * frameTelemetryClient.retry.test.ts — loss-recovery acceptance (2026-10-01).
 *
 * The defect these tests pin (audit: .audit/2026-10-01-anatomy/emitter-impact.md):
 * the emitter used to clear its buffer BEFORE the send and had no branch for
 * 500/503, so every failed flush was dropped permanently and invisibly
 * (~19.4% of prod flushes over 24h). The server dedupes an exact replay by
 * batch_ref, so re-sending the same bytes is safe.
 *
 * Load-bearing claims (each ASSERTED, not eyeballed):
 *  - a 503 leaves the batch queued and the next flush re-sends the SAME
 *    window_id with the SAME seconds (exact replay);
 *  - a 500 retries with bounded exponential backoff and stops: at most
 *    RETRY_MAX_ATTEMPTS sends, then ONE counted drop, then silence;
 *  - a 202 clears the batch — no re-send, no duplicate accrual;
 *  - a permanent 4xx (not 429) drops the batch deliberately: the drop counter
 *    increments, onError fires {kind:"dropped"}, and there is no retry;
 *  - a Retry-After header raises the retry floor;
 *  - a beacon flush does NOT pretend to deliver: the batch stays queued and
 *    is counted beaconUnconfirmed until a confirming fetch resolves it.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as client from "./frameTelemetryClient";
import { FrameTelemetryEmitter, type TelemetryError, type Transport } from "./frameTelemetryClient";
import type { FrameSecond } from "./frameContract";

function second(index: number): FrameSecond {
  return {
    second_index: index,
    lens: "read",
    samples: [
      {
        asset_id: `doc-${index}`,
        viewport_area_fraction: 0.5,
        prominence: 0.5,
        focused_dwell_ms: 1000,
      },
    ],
  };
}

/** A scripted transport: post() returns the next status in ``postStatuses``
 *  (the last one repeats once the script is exhausted). */
function scriptedTransport(opts?: {
  beaconOk?: boolean;
  postStatuses?: number[];
  detailed?: { status: number; retryAfterMs: number | null }[];
}) {
  const calls: { kind: "beacon" | "post"; url: string; body: string }[] = [];
  const statuses = [...(opts?.postStatuses ?? [200])];
  const detailed = opts?.detailed ? [...opts.detailed] : null;
  const transport: Transport = {
    beacon(url, body) {
      calls.push({ kind: "beacon", url, body });
      return opts?.beaconOk ?? true;
    },
    async post(url, body) {
      calls.push({ kind: "post", url, body });
      if (statuses.length > 1) return statuses.shift()!;
      return statuses[0]!;
    },
  };
  if (detailed) {
    transport.postDetailed = async (url, body) => {
      calls.push({ kind: "post", url, body });
      if (detailed.length > 1) return detailed.shift()!;
      return detailed[0]!;
    };
  }
  return { transport, calls };
}

type TransportCall = { kind: "beacon" | "post"; url: string; body: string };
const posts = (calls: TransportCall[]) => calls.filter((c) => c.kind === "post");

beforeEach(() => {
  vi.useFakeTimers();
  client.resetFrameTelemetryMetrics?.();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("FrameTelemetryEmitter — failed flush is recoverable", () => {
  it("a 503 leaves the batch queued and the next flush re-sends the SAME window_id", async () => {
    const { transport, calls } = scriptedTransport({ postStatuses: [503, 202] });
    const emitter = new FrameTelemetryEmitter({
      windowId: "win:read:retry",
      transport,
      flushIntervalMs: 1000,
    });
    emitter.start();
    emitter.record(second(0));
    emitter.record(second(1));
    emitter.record(second(2));

    await vi.advanceTimersByTimeAsync(1000);
    // The 503 did NOT clear the batch: one send, and it stays queued.
    expect(posts(calls)).toHaveLength(1);
    expect(emitter.outboxDepth).toBe(1);

    // Backoff elapses -> the SAME batch is re-sent (exact replay is safe:
    // the server dedupes by batch_ref).
    await vi.advanceTimersByTimeAsync(1000);
    expect(posts(calls)).toHaveLength(2);
    const first = JSON.parse(posts(calls)[0]!.body);
    const resent = JSON.parse(posts(calls)[1]!.body);
    expect(resent.window_id).toBe("win:read:retry");
    expect(resent.window_id).toBe(first.window_id);
    expect(resent.seconds).toEqual(first.seconds);

    // The 202 confirmed it: queue empty, no third send.
    expect(emitter.outboxDepth).toBe(0);
    await vi.advanceTimersByTimeAsync(10_000);
    expect(posts(calls)).toHaveLength(2);
    emitter.stop();
  });

  it("a 500 retries with bounded backoff and does not spin forever", async () => {
    const errors: TelemetryError[] = [];
    const { transport, calls } = scriptedTransport({ postStatuses: [500] });
    const emitter = new FrameTelemetryEmitter({
      windowId: "win:read:bounded",
      transport,
      flushIntervalMs: 1000,
      onError: (e) => errors.push(e),
    });
    emitter.start();
    emitter.record(second(0));

    // Far more wall-clock than the retry policy allows: attempts must be
    // capped (5 sends) and the batch then dropped and COUNTED, not spun on.
    await vi.advanceTimersByTimeAsync(120_000);
    expect(posts(calls)).toHaveLength(5);
    expect(client.getFrameTelemetryMetrics?.().retried).toBe(4);
    expect(client.getFrameTelemetryMetrics?.().dropped).toBe(1);
    expect(errors).toContainEqual(
      expect.objectContaining({ kind: "dropped", status: 500, windowId: "win:read:bounded" }),
    );
    expect(emitter.outboxDepth).toBe(0);

    // After the drop: silence. No spin.
    const sendsSoFar = posts(calls).length;
    await vi.advanceTimersByTimeAsync(120_000);
    expect(posts(calls)).toHaveLength(sendsSoFar);
    emitter.stop();
  });

  it("a 202 clears the batch (confirmed delivery, no duplicate accrual)", async () => {
    const { transport, calls } = scriptedTransport({ postStatuses: [202] });
    const emitter = new FrameTelemetryEmitter({
      windowId: "win:read:ok",
      transport,
      flushIntervalMs: 1000,
    });
    emitter.start();
    emitter.record(second(0));

    await vi.advanceTimersByTimeAsync(1000);
    expect(posts(calls)).toHaveLength(1);
    expect(emitter.outboxDepth).toBe(0);
    expect(client.getFrameTelemetryMetrics?.().delivered).toBe(1);
    expect(client.getFrameTelemetryMetrics?.().dropped).toBe(0);

    // Nothing re-sends later: the accepted batch is gone from the queue.
    await vi.advanceTimersByTimeAsync(30_000);
    expect(posts(calls)).toHaveLength(1);
    emitter.stop();
  });

  it("a permanent 4xx drops the batch deliberately, counts it, and does not retry", async () => {
    const errors: TelemetryError[] = [];
    const { transport, calls } = scriptedTransport({ postStatuses: [400] });
    const emitter = new FrameTelemetryEmitter({
      windowId: "win:read:perm",
      transport,
      flushIntervalMs: 1000,
      onError: (e) => errors.push(e),
    });
    emitter.start();
    emitter.record(second(0));

    await vi.advanceTimersByTimeAsync(1000);
    expect(posts(calls)).toHaveLength(1);
    expect(client.getFrameTelemetryMetrics?.().dropped).toBe(1);
    expect(errors).toContainEqual(
      expect.objectContaining({ kind: "dropped", status: 400, windowId: "win:read:perm" }),
    );
    expect(emitter.outboxDepth).toBe(0);

    // A permanent rejection is not retried.
    await vi.advanceTimersByTimeAsync(30_000);
    expect(posts(calls)).toHaveLength(1);
    emitter.stop();
  });

  it("honors Retry-After as the retry floor on a 503", async () => {
    const { transport, calls } = scriptedTransport({
      detailed: [
        { status: 503, retryAfterMs: 5000 },
        { status: 202, retryAfterMs: null },
      ],
    });
    const emitter = new FrameTelemetryEmitter({
      windowId: "win:read:retry-after",
      transport,
      flushIntervalMs: 1000,
    });
    emitter.start();
    emitter.record(second(0));

    await vi.advanceTimersByTimeAsync(1000);
    expect(posts(calls)).toHaveLength(1); // the 503

    // The client's own backoff (1s) must NOT fire the retry — the server
    // asked for 5s.
    await vi.advanceTimersByTimeAsync(1000);
    expect(posts(calls)).toHaveLength(1);
    await vi.advanceTimersByTimeAsync(3000);
    expect(posts(calls)).toHaveLength(1);

    // At 5s past the failure the retry goes out and is confirmed.
    await vi.advanceTimersByTimeAsync(1000);
    expect(posts(calls)).toHaveLength(2);
    expect(emitter.outboxDepth).toBe(0);
    emitter.stop();
  });
});

describe("FrameTelemetryEmitter — beacon flushes do not pretend to deliver", () => {
  it("a beacon hand-off keeps the batch queued until a fetch confirms it", async () => {
    const { transport, calls } = scriptedTransport({ beaconOk: true, postStatuses: [202] });
    const emitter = new FrameTelemetryEmitter({
      windowId: "win:read:beacon",
      transport,
      flushIntervalMs: 1000,
    });
    emitter.start();
    emitter.record(second(0));
    emitter.record(second(1));
    emitter.stop(); // terminal flush -> beacon

    // The beacon's status is unreadable, so the batch is NOT cleared: it is
    // queued and counted as unconfirmed.
    expect(calls.filter((c) => c.kind === "beacon")).toHaveLength(1);
    expect(emitter.outboxDepth).toBe(1);
    expect(client.getFrameTelemetryMetrics?.().beaconUnconfirmed).toBe(1);
    expect(client.getFrameTelemetryMetrics?.().delivered).toBe(0);

    // The confirming fetch then re-sends the SAME bytes (idempotent replay)
    // and only the 202 clears the queue.
    await vi.advanceTimersByTimeAsync(1000);
    expect(posts(calls)).toHaveLength(1);
    expect(JSON.parse(posts(calls)[0]!.body).window_id).toBe("win:read:beacon");
    expect(emitter.outboxDepth).toBe(0);
    expect(client.getFrameTelemetryMetrics?.().delivered).toBe(1);
  });
});
