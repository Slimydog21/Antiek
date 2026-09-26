/**
 * failure.ts — one plain-language description for anything a request can throw.
 *
 * Every surface that shows a failed load or action calls `describeFailure` and
 * renders `title` and `detail`. Neither ever contains an HTTP status, a method,
 * a path, a server code or a response body: those are for logs, and a person
 * reading the page can do nothing with them (lane A's DB-2 bar; the frontend
 * audit of main d61e5256d, F-04/F-05/F-06). `status` survives as a field for
 * logging and tests only. Never render it.
 *
 * It adds no failure codes. The closed DRW set in `lib/api.ts`
 * (docs/decisions/drw-plan-failure-contract.md, "no sixth code") is passed
 * through: when a body carries that envelope, `serverCode` is set and `detail`
 * is the contract's verbatim headline. Everything else is described by the
 * HTTP status class, which is a display mapping, not a new code.
 *
 * Server `detail` strings are never shown: they are usually codes
 * (`reading_state_stale_revision`), and a code is not a sentence.
 */
import { ApiError, FAILURE_HEADLINES, classifyClientError, type FailureCode } from "../lib/api";

export type FailureKind =
  | "offline"
  | "unauthorized"
  | "forbidden"
  | "not_found"
  | "conflict"
  | "too_large"
  | "invalid"
  | "rate_limited"
  | "unavailable"
  | "server"
  | "timeout"
  | "malformed"
  | "unknown";

export interface DescribedFailure {
  /** "Couldn't <what>." or "That didn't work." */
  title: string;
  /** One plain sentence: what happened and what to do. */
  detail: string;
  retryable: boolean;
  kind: FailureKind;
  /** The HTTP status, for logs and tests only. Never render it. */
  status?: number;
  /** Set only when the body carried the closed DRW failure envelope. */
  serverCode?: FailureCode;
}

const DETAIL: Record<FailureKind, string> = {
  offline: "Antiek can't be reached right now. Check your connection, then try again.",
  unauthorized: "You're signed out. Sign in again to continue.",
  forbidden: "This isn't available to your account.",
  not_found: "It may have been moved or removed.",
  conflict: "It changed somewhere else. Reload to see the latest, then try again.",
  too_large: "It's too large to send.",
  invalid: "Antiek couldn't accept that request.",
  rate_limited: "Too many requests at once. Wait a moment, then try again.",
  unavailable: "Antiek is busy or restarting. Try again in a moment.",
  server: "Something went wrong on Antiek's side. Try again.",
  timeout: "It took too long to answer. Try again.",
  malformed: "Antiek sent an answer this page couldn't read. Try again.",
  unknown: "Something unexpected went wrong. Try again.",
};

const RETRYABLE: Record<FailureKind, boolean> = {
  offline: true,
  unauthorized: false,
  forbidden: false,
  not_found: false,
  conflict: true,
  too_large: false,
  invalid: false,
  rate_limited: true,
  unavailable: true,
  server: true,
  timeout: true,
  malformed: true,
  unknown: true,
};

function kindForStatus(status: number): FailureKind {
  if (status === 0) return "malformed";
  if (status === 401) return "unauthorized";
  if (status === 403) return "forbidden";
  if (status === 404 || status === 410) return "not_found";
  if (status === 408 || status === 504) return "timeout";
  if (status === 409) return "conflict";
  if (status === 413) return "too_large";
  if (status === 429) return "rate_limited";
  if (status === 503) return "unavailable";
  if (status >= 500) return "server";
  return "invalid";
}

function titleFor(what: string | undefined): string {
  const action = what?.trim().replace(/[.!]+$/, "");
  return action ? `Couldn't ${action}.` : "That didn't work.";
}

export function describeFailure(err: unknown, ctx: { what?: string } = {}): DescribedFailure {
  const title = titleFor(ctx.what);
  if (err instanceof ApiError) {
    const kind = kindForStatus(err.status);
    const status = err.status === 0 ? undefined : err.status;
    const envelope = classifyClientError(err);
    if (envelope.code !== "unknown") {
      return {
        title,
        detail: FAILURE_HEADLINES[envelope.code],
        retryable: envelope.retryable,
        kind,
        status,
        serverCode: envelope.code,
      };
    }
    return { title, detail: DETAIL[kind], retryable: RETRYABLE[kind], kind, status };
  }
  if (err instanceof DOMException && (err.name === "AbortError" || err.name === "TimeoutError")) {
    return { title, detail: DETAIL.timeout, retryable: RETRYABLE.timeout, kind: "timeout" };
  }
  if (err instanceof TypeError) {
    return { title, detail: DETAIL.offline, retryable: RETRYABLE.offline, kind: "offline" };
  }
  return { title, detail: DETAIL.unknown, retryable: RETRYABLE.unknown, kind: "unknown" };
}
