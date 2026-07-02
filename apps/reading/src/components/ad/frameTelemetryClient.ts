// Contract-conformant frame-attention telemetry emitter (SPR-07 M4).
//
// The binding flush rule (frame_attention.py, "BATCHING / FLUSH RULE"):
// telemetry is NOT one request per second. The emitter BUFFERS per-second
// FrameSeconds client-side for the lifetime of a window and FLUSHES ONE compact
// WindowFrameBatch per window — on a periodic interval ceiling AND on
// pagehide / visibilitychange-hidden, whichever comes first. The backend
// aggregates the batch to per-asset accrual before any DB write; the emitter's
// job is the compact batch, so request count is O(windows) not O(seconds).
//
// Live route: interfaces/research/api/ad_routes.py:141 registers
// `POST /api/ad/frame-telemetry`; schema or deployment mismatches surface
// through ``onError`` and never throw into the render path.

import { API_BASE } from "../../lib/api";
import {
  FRAME_TELEMETRY_SCHEMA_VERSION,
  type FrameSecond,
  type WindowFrameBatch,
} from "./frameContract";

const TELEMETRY_PATH = "/api/ad/frame-telemetry";

/** How the emitter surfaces a flush failure (route absent / version mismatch /
 *  network). Surfacing (not swallowing) is the honesty requirement: a future
 *  mismatch is detectable, not invisible. */
export type TelemetryError =
  | { kind: "route-absent"; status: number; windowId: string }
  | { kind: "version-mismatch"; sent: string; windowId: string }
  | { kind: "network"; message: string; windowId: string };

export interface FrameTelemetryEmitterOptions {
  windowId: string;
  /** Periodic flush ceiling in ms (default 30s) — the batch is flushed at
   *  least this often even if the window stays open, so a very long session
   *  doesn't buffer unbounded. */
  flushIntervalMs?: number;
  /** Surfaced on any flush failure. Never throws into the caller. */
  onError?: (err: TelemetryError) => void;
  /** Injectable for tests; defaults to the real fetch/sendBeacon. */
  transport?: Transport;
}

/** The POST surface, split so a test can mock fetch + beacon independently and
 *  so pagehide can prefer the keepalive beacon. */
export interface Transport {
  /** Best-effort, survives navigation. Returns false if unavailable so the
   *  caller can fall back to fetch. */
  beacon(url: string, body: string): boolean;
  /** The interactive flush. Resolves to the HTTP status (0 on network error). */
  post(url: string, body: string): Promise<number>;
}

function defaultTransport(): Transport {
  return {
    beacon(url, body) {
      if (typeof navigator === "undefined" || !navigator.sendBeacon) return false;
      // application/json so the deferred route parses it the same as a fetch
      // POST — no separate text/plain code path on the backend.
      return navigator.sendBeacon(url, new Blob([body], { type: "application/json" }));
    },
    async post(url, body) {
      try {
        const resp = await fetch(url, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body,
          credentials: "include",
          keepalive: true,
        });
        return resp.status;
      } catch {
        return 0;
      }
    },
  };
}

/**
 * Buffers per-second samples for one window and flushes one WindowFrameBatch.
 *
 * Lifecycle: construct on window open → ``record`` once per second from the
 * sampler (M3) → ``start`` to arm the periodic + pagehide/visibility flushes →
 * ``stop`` on window close (final flush). One emitter per window; the
 * window_id is the trace anchor stamped on every accrual derived from the batch.
 */
export class FrameTelemetryEmitter {
  private readonly windowId: string;
  private readonly flushIntervalMs: number;
  private readonly onError?: (err: TelemetryError) => void;
  private readonly transport: Transport;

  private buffer: FrameSecond[] = [];
  private timer: ReturnType<typeof setInterval> | null = null;
  // pagehide is terminal — flush unconditionally (its visibilityState is
  // unreliable / often still "visible" as the page tears down). A
  // visibilitychange flushes ONLY when actually hidden so →visible never
  // double-sends. Two distinct handlers, not one gated on visibilityState.
  private readonly boundFlushOnPageHide = () => void this.flush("hidden");
  private readonly boundFlushOnVisibility = () => this.flushOnVisibilityChange();
  private started = false;

  constructor(opts: FrameTelemetryEmitterOptions) {
    this.windowId = opts.windowId;
    this.flushIntervalMs = opts.flushIntervalMs ?? 30_000;
    this.onError = opts.onError;
    this.transport = opts.transport ?? defaultTransport();
  }

  /** Buffer one second. Does not flush — flushing is interval/lifecycle-driven
   *  so request count stays O(windows), not O(seconds). */
  record(second: FrameSecond): void {
    this.buffer.push(second);
  }

  /** Arm the periodic flush + the pagehide/visibilitychange flush. Idempotent. */
  start(): void {
    if (this.started) return;
    this.started = true;
    this.timer = setInterval(() => void this.flush("interval"), this.flushIntervalMs);
    if (typeof document !== "undefined") {
      // pagehide is the reliable terminal event on navigation/close; a
      // visibilitychange→hidden covers tab-switch / background. Both flush via
      // the keepalive beacon so the batch survives the navigation that fires
      // them (a plain fetch would be cancelled mid-navigation).
      window.addEventListener("pagehide", this.boundFlushOnPageHide);
      document.addEventListener("visibilitychange", this.boundFlushOnVisibility);
    }
  }

  /** Final flush + teardown. Safe to call more than once. */
  stop(): void {
    if (this.timer) {
      clearInterval(this.timer);
      this.timer = null;
    }
    if (typeof document !== "undefined") {
      window.removeEventListener("pagehide", this.boundFlushOnPageHide);
      document.removeEventListener("visibilitychange", this.boundFlushOnVisibility);
    }
    this.started = false;
    void this.flush("stop");
  }

  /** The number of buffered seconds not yet flushed (test/inspection hook). */
  get pending(): number {
    return this.buffer.length;
  }

  private flushOnVisibilityChange(): void {
    // Only flush when actually hidden — a visibilitychange→visible must not
    // double-send. (pagehide is handled separately and always flushes.)
    if (typeof document !== "undefined" && document.visibilityState === "visible") {
      return;
    }
    void this.flush("hidden");
  }

  /**
   * Flush the buffered seconds as ONE batch. ``viaBeacon`` flushes (hidden /
   * stop) prefer sendBeacon so navigation doesn't lose the batch; the periodic
   * flush uses fetch so it can read the status and surface a route-absent /
   * version-mismatch error. Either way: POST-only, never a DB writer.
   */
  private async flush(reason: "interval" | "hidden" | "stop"): Promise<void> {
    if (this.buffer.length === 0) return;
    const seconds = this.buffer;
    this.buffer = [];
    const batch: WindowFrameBatch = {
      window_id: this.windowId,
      seconds,
      // SPR-10 prices the second; until then the emitter sends 0 (honest — no
      // fabricated value). The backend treats 0 as "unpriced this window".
      ad_value_usd_cents: 0,
      schema_version: FRAME_TELEMETRY_SCHEMA_VERSION,
    };
    const body = JSON.stringify(batch);
    const url = `${API_BASE}${TELEMETRY_PATH}`;

    if (reason !== "interval") {
      // Terminal flush: prefer the keepalive beacon. If it can't be queued,
      // fall through to fetch (which is keepalive too).
      if (this.transport.beacon(url, body)) return;
    }

    const status = await this.transport.post(url, body);
    if (status === 0) {
      this.onError?.({ kind: "network", message: "frame-telemetry POST failed", windowId: this.windowId });
      return;
    }
    if (status === 404) {
      // Route absent (the live route is ad_routes.py:141; a 404 means an old
      // deployment predating it). Surface it — do not pretend it succeeded.
      this.onError?.({ kind: "route-absent", status, windowId: this.windowId });
      return;
    }
    if (status === 409 || status === 422) {
      // The backend rejected the stamped schema version (mismatch). Surface
      // the exact version we sent so a dispute can isolate the divergence.
      this.onError?.({ kind: "version-mismatch", sent: FRAME_TELEMETRY_SCHEMA_VERSION, windowId: this.windowId });
      return;
    }
  }
}
