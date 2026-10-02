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
//
// FAILURE SEMANTICS (2026-10-01, data-loss fix). The previous revision cleared
// the buffer BEFORE the send and had no branch for 500/503, so a failed batch
// was dropped permanently and invisibly (prod: ~19.4% of flushes lost over
// 24h; see .audit/2026-10-01-anatomy/emitter-impact.md). Now:
//  - a batch is cleared ONLY on a confirmed 2xx;
//  - transient failures (network error, 5xx, 429) keep the batch queued and
//    retry with bounded exponential backoff (attempt cap + total-wait cap,
//    honoring Retry-After). A retry is an EXACT replay of the same bytes,
//    which the server dedupes by batch_ref (frame_attention_accrual.py), so
//    re-sending is safe;
//  - permanent failures (4xx other than 429) drop the batch DELIBERATELY and
//    count it (getFrameTelemetryMetrics().dropped, plus onError);
//  - beacon flushes (pagehide/visibilitychange) cannot read the delivery
//    status, so the batch stays queued and is counted as beaconUnconfirmed
//    until a confirming fetch resolves it.

import { API_BASE } from "../../lib/api";
import {
  FRAME_TELEMETRY_SCHEMA_VERSION,
  type FrameSecond,
  type WindowFrameBatch,
} from "./frameContract";

const TELEMETRY_PATH = "/api/ad/frame-telemetry";

/** Retry policy for TRANSIENT failures (network error, 5xx, 429). Bounded on
 *  both axes — attempt count and total wait — so a down backend degrades to a
 *  counted drop, never a spin. */
const RETRY_BASE_DELAY_MS = 1_000;
const RETRY_MAX_DELAY_MS = 8_000;
const RETRY_MAX_ATTEMPTS = 5;
const RETRY_MAX_TOTAL_WAIT_MS = 60_000;
/** After a beacon hand-off, wait this long before the confirming fetch. */
const BEACON_CONFIRM_DELAY_MS = 1_000;
/** Hard outbox ceiling. At the default 30s flush interval the total-wait cap
 *  already bounds depth to ~3; this covers pathological manual-stop bursts. */
const MAX_OUTBOX_BATCHES = 10;

/** How the emitter surfaces a flush failure (route absent / version mismatch /
 *  network / deliberate drop). Surfacing (not swallowing) is the honesty
 *  requirement: a future mismatch is detectable, not invisible. */
export type TelemetryError =
  | { kind: "route-absent"; status: number; windowId: string }
  | { kind: "version-mismatch"; sent: string; windowId: string }
  | { kind: "network"; message: string; windowId: string }
  | { kind: "dropped"; status: number | null; attempts: number; windowId: string };

/**
 * Process-level counters for the flush path — the observability the dropped
 * batches never had. Module-level because emitters are per-window and
 * short-lived; the loss signal is a property of the route, not of one window.
 */
export interface FrameTelemetryMetrics {
  /** Batches confirmed accepted (2xx) by the server. */
  delivered: number;
  /** Transient failures (network / 5xx / 429) that scheduled a retry. */
  retried: number;
  /** Batches deliberately dropped: permanent 4xx (not 429), retry-attempt cap
   *  reached, or total-wait cap exceeded. 404/409/422 surface their specific
   *  onError kind; every other drop also fires onError({kind:"dropped"}). */
  dropped: number;
  /** Batches handed to sendBeacon, whose delivery status CANNOT be read. Each
   *  stays queued for a confirming fetch; if the page unloads first, this
   *  counter is the honest record that delivery was never confirmed. */
  beaconUnconfirmed: number;
}

const metrics: FrameTelemetryMetrics = {
  delivered: 0,
  retried: 0,
  dropped: 0,
  beaconUnconfirmed: 0,
};

/** Snapshot of the module-level flush counters. */
export function getFrameTelemetryMetrics(): FrameTelemetryMetrics {
  return { ...metrics };
}

/** Reset the counters. Test hook — production code never calls this. */
export function resetFrameTelemetryMetrics(): void {
  metrics.delivered = 0;
  metrics.retried = 0;
  metrics.dropped = 0;
  metrics.beaconUnconfirmed = 0;
}

/** Parse a Retry-After header (delta-seconds or HTTP-date) to ms. */
function parseRetryAfterMs(value: string | null): number | null {
  if (value === null) return null;
  const seconds = Number(value);
  if (Number.isFinite(seconds) && seconds >= 0) return seconds * 1_000;
  const at = Date.parse(value);
  if (!Number.isNaN(at)) return Math.max(0, at - Date.now());
  return null;
}

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
  /** Richer variant of post() that also exposes the Retry-After header.
   *  Optional: a transport that omits it retries on the client's own backoff
   *  schedule. */
  postDetailed?(
    url: string,
    body: string,
  ): Promise<{ status: number; retryAfterMs: number | null }>;
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
      return (await this.postDetailed!(url, body)).status;
    },
    async postDetailed(url, body) {
      try {
        const resp = await fetch(url, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body,
          credentials: "include",
          keepalive: true,
        });
        return { status: resp.status, retryAfterMs: parseRetryAfterMs(resp.headers.get("Retry-After")) };
      } catch {
        return { status: 0, retryAfterMs: null };
      }
    },
  };
}

/** One flushed batch awaiting confirmation. The body is frozen at enqueue time
 *  so a retry is an EXACT replay — the server dedupes by batch_ref. */
interface PendingBatch {
  body: string;
  /** Fetch sends attempted so far (a beacon hand-off is not confirmable). */
  attempts: number;
  /** Date.now() of the first transient failure, for the total-wait cap. */
  firstFailureAt: number | null;
  /** Do not fetch-send before this time — the backoff governor. */
  notBefore: number;
  /** True once handed to sendBeacon (status unreadable -> stays queued). */
  beaconQueued: boolean;
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
  /** Flushed batches not yet confirmed delivered. Cleared ONLY on 2xx, a
   *  deliberate (counted) drop, or never. */
  private outbox: PendingBatch[] = [];
  private retryTimer: ReturnType<typeof setTimeout> | null = null;
  private retryFireAt = 0;
  private draining = false;
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

  /** Flushed batches not yet confirmed delivered (retry/beacon queue). */
  get outboxDepth(): number {
    return this.outbox.length;
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
   * Flush the buffered seconds as ONE batch and drive the outbox. Terminal
   * flushes (hidden / stop) prefer sendBeacon so navigation doesn't lose the
   * batch; the periodic flush uses fetch so it can read the status. Either
   * way: POST-only, never a DB writer.
   */
  private flush(reason: "interval" | "hidden" | "stop"): void {
    if (this.buffer.length > 0) {
      const batch: WindowFrameBatch = {
        window_id: this.windowId,
        seconds: this.buffer,
        // AFA-S1 (frame-telemetry-v2): the emitter sends NO value. The client
        // measures attention; the SERVER prices the window at accrual time. A
        // value the client can set is a value the client can forge — so the
        // field is gone from the wire shape, not merely set to 0.
        schema_version: FRAME_TELEMETRY_SCHEMA_VERSION,
      };
      this.buffer = [];
      this.outbox.push({
        body: JSON.stringify(batch),
        attempts: 0,
        firstFailureAt: null,
        notBefore: 0,
        beaconQueued: false,
      });
      // Hard bound: the outbox never grows without limit. The overflow batch
      // is dropped deliberately and COUNTED, never silently.
      while (this.outbox.length > MAX_OUTBOX_BATCHES) {
        this.dropBatch(this.outbox.shift()!, null);
      }
    }
    if (this.outbox.length === 0) return;

    if (reason !== "interval") {
      // Terminal flush: prefer the keepalive beacon. A beacon's delivery
      // status CANNOT be read, so the batch is NOT cleared — it stays queued,
      // is counted as beaconUnconfirmed, and a confirming fetch is scheduled.
      // If the page survives (tab-switch), the fetch resolves it; if the page
      // unloads, the counter is the honest record of non-confirmation.
      const url = `${API_BASE}${TELEMETRY_PATH}`;
      let allQueued = true;
      for (const pending of this.outbox) {
        if (pending.beaconQueued) continue;
        if (this.transport.beacon(url, pending.body)) {
          pending.beaconQueued = true;
          pending.notBefore = Date.now() + BEACON_CONFIRM_DELAY_MS;
          metrics.beaconUnconfirmed++;
        } else {
          allQueued = false;
        }
      }
      if (allQueued) {
        this.armTimer(BEACON_CONFIRM_DELAY_MS);
        return;
      }
      // Beacon unavailable for at least one batch: fall through to fetch
      // (which is keepalive too) so its status is read.
    }
    void this.drainOutbox();
  }

  /** Fetch-send outbox heads in order until the queue empties or a batch must
   *  wait out its backoff. At most one drain runs at a time. */
  private async drainOutbox(): Promise<void> {
    if (this.draining) return;
    this.draining = true;
    try {
      const url = `${API_BASE}${TELEMETRY_PATH}`;
      while (this.outbox.length > 0) {
        const head = this.outbox[0]!;
        const waitMs = head.notBefore - Date.now();
        if (waitMs > 0) {
          this.armTimer(waitMs);
          break;
        }
        const { status, retryAfterMs } = await this.send(url, head.body);
        head.attempts++;
        if (status >= 200 && status < 300) {
          // Confirmed acceptance — ONLY now is the batch cleared.
          this.outbox.shift();
          metrics.delivered++;
          continue;
        }
        if (isTransient(status)) {
          head.firstFailureAt ??= Date.now();
          if (status === 0) {
            this.onError?.({
              kind: "network",
              message: "frame-telemetry POST failed",
              windowId: this.windowId,
            });
          }
          const delayMs = this.retryDelayMs(head.attempts, retryAfterMs);
          const waited = Date.now() - head.firstFailureAt;
          if (head.attempts >= RETRY_MAX_ATTEMPTS || waited + delayMs > RETRY_MAX_TOTAL_WAIT_MS) {
            // Bounds exhausted: a counted drop, not a spin.
            this.outbox.shift();
            this.dropBatch(head, status);
            continue;
          }
          head.notBefore = Date.now() + delayMs;
          metrics.retried++;
          this.armTimer(delayMs);
          break; // one waiting batch gates the queue; the timer resumes the drain
        }
        // Permanent failure (4xx that is not 429): the server will never
        // accept these bytes. Surface the specific cause, then drop
        // DELIBERATELY and count it — never silently.
        const surfaced = this.reportPermanentError(status);
        this.outbox.shift();
        this.dropBatch(head, status, surfaced);
      }
    } finally {
      this.draining = false;
    }
  }

  private async send(
    url: string,
    body: string,
  ): Promise<{ status: number; retryAfterMs: number | null }> {
    if (this.transport.postDetailed) return this.transport.postDetailed(url, body);
    return { status: await this.transport.post(url, body), retryAfterMs: null };
  }

  /** Exponential backoff, floored at the server's Retry-After hint when one
   *  was sent (e.g. the 503 writer-busy response carries Retry-After: 1). */
  private retryDelayMs(attempts: number, retryAfterMs: number | null): number {
    const backoff = Math.min(RETRY_MAX_DELAY_MS, RETRY_BASE_DELAY_MS * 2 ** (attempts - 1));
    return Math.max(backoff, retryAfterMs ?? 0);
  }

  /** Arm the retry/confirmation timer; re-arms earlier if the new deadline
   *  is sooner than the pending one. */
  private armTimer(delayMs: number): void {
    const fireAt = Date.now() + delayMs;
    if (this.retryTimer !== null && this.retryFireAt <= fireAt) return;
    if (this.retryTimer !== null) clearTimeout(this.retryTimer);
    this.retryFireAt = fireAt;
    this.retryTimer = setTimeout(() => {
      this.retryTimer = null;
      void this.drainOutbox();
    }, delayMs);
  }

  /** The pre-existing specific surfaces. Returns true when a specific error
   *  was fired, so dropBatch does not double-report the same failure. */
  private reportPermanentError(status: number): boolean {
    if (status === 404) {
      // Route absent (the live route is ad_routes.py:141; a 404 means an old
      // deployment predating it). Surface it — do not pretend it succeeded.
      this.onError?.({ kind: "route-absent", status, windowId: this.windowId });
      return true;
    }
    if (status === 409 || status === 422) {
      // The backend rejected the stamped schema version (mismatch). Surface
      // the exact version we sent so a dispute can isolate the divergence.
      this.onError?.({
        kind: "version-mismatch",
        sent: FRAME_TELEMETRY_SCHEMA_VERSION,
        windowId: this.windowId,
      });
      return true;
    }
    return false;
  }

  /** Count the drop always; fire the dropped event only when no more specific
   *  error already surfaced this failure. */
  private dropBatch(batch: PendingBatch, status: number | null, surfaced = false): void {
    metrics.dropped++;
    if (!surfaced) {
      this.onError?.({ kind: "dropped", status, attempts: batch.attempts, windowId: this.windowId });
    }
  }
}

/** Transient = worth an exact-replay retry: network error, rate-limit, or any
 *  5xx. Everything else 4xx is permanent for these bytes. */
function isTransient(status: number): boolean {
  return status === 0 || status === 429 || (status >= 500 && status < 600);
}
