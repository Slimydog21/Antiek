/**
 * failure.ts — one plain-language description for anything a request can throw.
 *
 * Every surface that shows a failed load or action calls `describeFailure` and
 * renders `title` and `detail`. Neither ever contains an HTTP status, a method,
 * a path, a server code or a response body: those are for logs, and a person
 * reading the page can do nothing with them (lane A's DB-2 bar; the frontend
 * audit of main d61e5256d, F-04/F-05/F-06). The status and any server code are
 * kept in `diagnostics`, which is for logs and tests only: never render it and
 * never spread the result into markup.
 *
 * It adds no failure code. The closed DRW set in `lib/api.ts`
 * (docs/decisions/drw-plan-failure-contract.md, "no sixth code") is passed
 * through: when a body carries that envelope, including a recognized
 * `unknown`, `detail` is the contract's verbatim headline and `retryable` is
 * the envelope's. The server's own `message` is never shown. Everything else
 * is described by the HTTP status, a display mapping and not a new code.
 *
 * Server `detail` strings are never shown: they are usually codes
 * (`reading_state_stale_revision`), and a code is not a sentence.
 */
import { ApiError, FAILURE_HEADLINES, parseFailureEnvelope, type FailureCode } from "../lib/api";

export type FailureKind =
  | "offline"
  | "unauthorized"
  | "forbidden"
  | "not_found"
  | "conflict"
  | "too_large"
  | "invalid"
  | "rate_limited"
  | "legal"
  | "network_auth"
  | "unavailable"
  | "server"
  | "timeout"
  | "malformed"
  | "unknown";

export interface DescribedFailure {
  /** "Couldn't <what>." or "That didn't work." */
  readonly title: string;
  /** A short, plain message: what happened and what to do. */
  readonly detail: string;
  readonly retryable: boolean;
  readonly kind: FailureKind;
  /** For logs and tests only. Never render it. */
  readonly diagnostics?: { readonly status?: number; readonly serverCode?: FailureCode };
}

const DETAIL: Record<FailureKind, string> = {
  offline: "Antiek can't be reached right now. Try again in a moment; if it keeps failing, check your connection.",
  unauthorized: "You're signed out. Sign in again to continue.",
  forbidden: "This isn't available to your account.",
  not_found: "It may have been moved or removed.",
  conflict: "It changed somewhere else. Reload to see the latest, then try again.",
  too_large: "It's too large to send.",
  invalid: "Antiek couldn't accept that request.",
  rate_limited: "Too many requests at once. Wait a moment, then try again.",
  legal: "This is unavailable for legal reasons.",
  network_auth: "The network you're on needs you to sign in. Open its sign-in page, then try again.",
  unavailable: "Antiek is busy or restarting. Try again in a moment.",
  server: "Something went wrong on Antiek's side. Try again.",
  timeout: "It took too long to answer. Try again.",
  malformed: "Antiek sent an answer this page couldn't read. Try again.",
  unknown: "Something unexpected went wrong. Try again.",
};

/** Statuses where an identical retry can succeed. Every other status is not retryable. */
const RETRYABLE_STATUS: ReadonlySet<number> = new Set([0, 408, 409, 429, 500, 502, 503, 504]);

/** Text a title must never carry: a status, a method with a path, "HTTP", a snake_case code, markup or JSON. */
const HOSTILE = /\b[1-5]\d\d\b|\bHTTP\b|\b(GET|POST|PUT|PATCH|DELETE)\s+\/|[a-z]+_[a-z_]+|[<>{}]|Traceback/;

function kindForStatus(status: number): FailureKind {
  if (status === 0) return "malformed";
  if (status < 400 || status > 599) return "unknown";
  if (status === 401) return "unauthorized";
  if (status === 403) return "forbidden";
  if (status === 404 || status === 410) return "not_found";
  if (status === 408 || status === 504) return "timeout";
  if (status === 409) return "conflict";
  if (status === 413) return "too_large";
  if (status === 429) return "rate_limited";
  if (status === 451) return "legal";
  if (status === 511) return "network_auth";
  if (status === 503) return "unavailable";
  if (status >= 500) return "server";
  return "invalid";
}

/**
 * `what` is a caller-authored imperative phrase ("load your research"), never
 * text derived from the error. If it carries anything a title must not, the
 * generic title is used instead, so the guarantee holds at this boundary.
 */
function titleFor(what: string | undefined): string {
  const action = what?.trim().replace(/[.!]+$/, "");
  if (!action || HOSTILE.test(action)) return "That didn't work.";
  return `Couldn't ${action}.`;
}

const validStatus = (status: number): number | undefined =>
  Number.isInteger(status) && status >= 100 && status <= 599 ? status : undefined;

export function describeFailure(err: unknown, ctx: { what?: string } = {}): DescribedFailure {
  const title = titleFor(ctx.what);
  if (err instanceof ApiError) {
    const status = validStatus(err.status);
    const kind = kindForStatus(Number.isInteger(err.status) ? err.status : -1);
    const envelope = parseFailureEnvelope(err);
    if (envelope) {
      return {
        title,
        detail: FAILURE_HEADLINES[envelope.code],
        retryable: envelope.retryable,
        kind,
        diagnostics: { status, serverCode: envelope.code },
      };
    }
    const retryable = RETRYABLE_STATUS.has(Number.isInteger(err.status) ? err.status : -1);
    return { title, detail: DETAIL[kind], retryable, kind, diagnostics: { status } };
  }
  if (err instanceof DOMException && (err.name === "AbortError" || err.name === "TimeoutError")) {
    return { title, detail: DETAIL.timeout, retryable: true, kind: "timeout" };
  }
  if (err instanceof TypeError) {
    return { title, detail: DETAIL.offline, retryable: true, kind: "offline" };
  }
  return { title, detail: DETAIL.unknown, retryable: true, kind: "unknown" };
}
