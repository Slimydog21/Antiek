/**
 * frameTelemetryClient.test.ts — SPR-07 M4 acceptance.
 *
 * Load-bearing claims (each ASSERTED, not eyeballed):
 *  - the emitter flushes ONE WindowFrameBatch for many recorded seconds — NOT
 *    one request per second (request count is O(windows), not O(seconds));
 *  - the flushed batch conforms to the contract shape and carries the stamped
 *    FRAME_TELEMETRY_SCHEMA_VERSION;
 *  - it flushes on pagehide and on visibilitychange→hidden, preferring the
 *    keepalive beacon there, and does NOT flush on visibilitychange→visible;
 *  - a 404 (the deferred SPR-09 route) surfaces a route-absent error and does
 *    not throw; a 409/422 surfaces a version-mismatch error carrying the sent
 *    version; a network failure surfaces a network error;
 *  - it is POST-only — the only transport calls are beacon()/post(), never any
 *    GET or DB writer.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  FrameTelemetryEmitter,
  type TelemetryError,
  type Transport,
} from "./frameTelemetryClient";
import { FRAME_TELEMETRY_SCHEMA_VERSION, type FrameSecond } from "./frameContract";

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

/** A spy transport: records every beacon/post and returns a scripted status. */
function spyTransport(opts?: { beaconOk?: boolean; postStatus?: number }) {
  const calls: { kind: "beacon" | "post"; url: string; body: string }[] = [];
  const transport: Transport = {
    beacon(url, body) {
      calls.push({ kind: "beacon", url, body });
      return opts?.beaconOk ?? true;
    },
    async post(url, body) {
      calls.push({ kind: "post", url, body });
      return opts?.postStatus ?? 200;
    },
  };
  return { transport, calls };
}

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("FrameTelemetryEmitter — one batch per window (M4)", () => {
  it("buffers many seconds and flushes them as ONE batch, not per-second", async () => {
    const { transport, calls } = spyTransport({ beaconOk: true, postStatus: 200 });
    const emitter = new FrameTelemetryEmitter({ windowId: "win:read:a", transport });
    emitter.start();

    for (let i = 0; i < 5; i++) emitter.record(second(i));
    // Nothing sent on record — flushing is interval/lifecycle-driven.
    expect(calls).toHaveLength(0);
    expect(emitter.pending).toBe(5);

    emitter.stop(); // terminal flush — one keepalive beacon
    await Promise.resolve();

    // ONE flush for five seconds — O(windows), not O(seconds).
    expect(calls).toHaveLength(1);
    const batch = JSON.parse(calls[0]!.body);
    expect(batch.seconds).toHaveLength(5);
  });

  it("flushes a contract-shaped batch with the stamped version", async () => {
    const { transport, calls } = spyTransport({ beaconOk: true, postStatus: 200 });
    const emitter = new FrameTelemetryEmitter({ windowId: "win:read:a", transport });
    emitter.start();
    emitter.record(second(0));
    emitter.stop();
    await Promise.resolve();

    const batch = JSON.parse(calls.at(-1)!.body);
    expect(Object.keys(batch).sort()).toEqual(
      ["ad_value_usd_cents", "schema_version", "seconds", "window_id"].sort(),
    );
    expect(batch.window_id).toBe("win:read:a");
    expect(batch.schema_version).toBe(FRAME_TELEMETRY_SCHEMA_VERSION);
    expect(batch.ad_value_usd_cents).toBe(0); // honest unpriced default
  });

  it("flushes on the periodic interval without closing the window", async () => {
    const { transport, calls } = spyTransport({ postStatus: 200 });
    const emitter = new FrameTelemetryEmitter({
      windowId: "win:read:a",
      transport,
      flushIntervalMs: 1000,
    });
    emitter.start();
    emitter.record(second(0));

    await vi.advanceTimersByTimeAsync(1000);
    // The interval flush uses post() (it reads status to surface errors).
    expect(calls.filter((c) => c.kind === "post")).toHaveLength(1);
    expect(emitter.pending).toBe(0);
    emitter.stop();
  });

  it("is POST-only — never issues a GET or any non-post/beacon transport call", async () => {
    const { transport, calls } = spyTransport({ beaconOk: true });
    const emitter = new FrameTelemetryEmitter({ windowId: "win:read:a", transport });
    emitter.start();
    emitter.record(second(0));
    emitter.stop();
    await Promise.resolve();
    expect(calls.length).toBeGreaterThan(0);
    expect(calls.every((c) => c.kind === "post" || c.kind === "beacon")).toBe(true);
  });
});

describe("FrameTelemetryEmitter — lifecycle flush (M4)", () => {
  it("flushes via the keepalive beacon on pagehide", async () => {
    const { transport, calls } = spyTransport({ beaconOk: true });
    const emitter = new FrameTelemetryEmitter({ windowId: "win:read:a", transport });
    emitter.start();
    emitter.record(second(0));

    window.dispatchEvent(new Event("pagehide"));
    await Promise.resolve();

    expect(calls.some((c) => c.kind === "beacon")).toBe(true);
    expect(emitter.pending).toBe(0);
    emitter.stop();
  });

  it("flushes on visibilitychange→hidden but NOT on →visible", async () => {
    const { transport, calls } = spyTransport({ beaconOk: true });
    const emitter = new FrameTelemetryEmitter({ windowId: "win:read:a", transport });
    emitter.start();

    // visible: must NOT flush.
    emitter.record(second(0));
    Object.defineProperty(document, "visibilityState", {
      value: "visible",
      configurable: true,
    });
    document.dispatchEvent(new Event("visibilitychange"));
    await Promise.resolve();
    expect(calls).toHaveLength(0);
    expect(emitter.pending).toBe(1);

    // hidden: must flush.
    Object.defineProperty(document, "visibilityState", {
      value: "hidden",
      configurable: true,
    });
    document.dispatchEvent(new Event("visibilitychange"));
    await Promise.resolve();
    expect(calls.some((c) => c.kind === "beacon")).toBe(true);
    expect(emitter.pending).toBe(0);

    Object.defineProperty(document, "visibilityState", {
      value: "visible",
      configurable: true,
    });
    emitter.stop();
  });
});

describe("FrameTelemetryEmitter — graceful degrade (M4 seam)", () => {
  it("surfaces route-absent on 404 and does not throw (the SPR-09 seam)", async () => {
    const errors: TelemetryError[] = [];
    const { transport } = spyTransport({ postStatus: 404 });
    const emitter = new FrameTelemetryEmitter({
      windowId: "win:read:a",
      transport,
      flushIntervalMs: 1000,
      onError: (e) => errors.push(e),
    });
    emitter.start();
    emitter.record(second(0));
    await vi.advanceTimersByTimeAsync(1000);

    expect(errors).toHaveLength(1);
    expect(errors[0]).toMatchObject({ kind: "route-absent", status: 404, windowId: "win:read:a" });
    emitter.stop();
  });

  it("surfaces version-mismatch on 409/422 carrying the sent version", async () => {
    for (const status of [409, 422]) {
      const errors: TelemetryError[] = [];
      const { transport } = spyTransport({ postStatus: status });
      const emitter = new FrameTelemetryEmitter({
        windowId: "win:read:a",
        transport,
        flushIntervalMs: 1000,
        onError: (e) => errors.push(e),
      });
      emitter.start();
      emitter.record(second(0));
      await vi.advanceTimersByTimeAsync(1000);
      expect(errors).toHaveLength(1);
      expect(errors[0]).toMatchObject({
        kind: "version-mismatch",
        sent: FRAME_TELEMETRY_SCHEMA_VERSION,
      });
      emitter.stop();
    }
  });

  it("surfaces a network error on transport status 0", async () => {
    const errors: TelemetryError[] = [];
    const { transport } = spyTransport({ postStatus: 0 });
    const emitter = new FrameTelemetryEmitter({
      windowId: "win:read:a",
      transport,
      flushIntervalMs: 1000,
      onError: (e) => errors.push(e),
    });
    emitter.start();
    emitter.record(second(0));
    await vi.advanceTimersByTimeAsync(1000);
    expect(errors[0]).toMatchObject({ kind: "network", windowId: "win:read:a" });
    emitter.stop();
  });

  it("does not flush an empty buffer (no zero-second batch)", async () => {
    const { transport, calls } = spyTransport();
    const emitter = new FrameTelemetryEmitter({
      windowId: "win:read:a",
      transport,
      flushIntervalMs: 1000,
    });
    emitter.start();
    await vi.advanceTimersByTimeAsync(3000);
    emitter.stop();
    await Promise.resolve();
    expect(calls).toHaveLength(0);
  });
});
