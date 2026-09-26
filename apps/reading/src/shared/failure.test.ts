import { describe, expect, it } from "vitest";

import { ApiError } from "../lib/api";
import { describeFailure } from "./failure";

/**
 * describeFailure turns anything a fetch can throw into plain words. The rule
 * it enforces (lane A DB-2; the frontend audit of main d61e5256d, F-04/F-05/F-06):
 * no HTTP status, method, path or response body ever reaches the person
 * reading the page. The status survives only as a field for logs and tests.
 */
const LEAK = /\b[45]\d\d\b|\bHTTP\b|\b(GET|POST|PUT|PATCH|DELETE) \/|Traceback|<html|"detail"|[a-z]+_[a-z_]+|KeyError/;

describe("describeFailure", () => {
  it("leads with what the page was trying to do", () => {
    const f = describeFailure(new ApiError("GET /investigations failed: HTTP 503", 503, "Service Unavailable"), {
      what: "load your research",
    });
    expect(f.title).toBe("Couldn't load your research.");
    expect(f.kind).toBe("unavailable");
    expect(f.retryable).toBe(true);
    expect(f.diagnostics?.status).toBe(503);
  });

  it("has a plain title when the caller names no action", () => {
    expect(describeFailure(new ApiError("x", 500, "")).title).toBe("That didn't work.");
  });

  it.each([
    [401, "unauthorized", false],
    [403, "forbidden", false],
    [404, "not_found", false],
    [409, "conflict", true],
    [413, "too_large", false],
    [422, "invalid", false],
    [429, "rate_limited", true],
    [451, "legal", false],
    [500, "server", true],
    [501, "server", false],
    [502, "server", true],
    [505, "server", false],
    [507, "server", false],
    [511, "network_auth", false],
    [503, "unavailable", true],
    [504, "timeout", true],
  ] as const)("maps HTTP %i to %s (retryable %s)", (status, kind, retryable) => {
    const f = describeFailure(new ApiError(`GET /x failed: HTTP ${status}`, status, "raw"), { what: "open this" });
    expect(f.kind).toBe(kind);
    expect(f.retryable).toBe(retryable);
    expect(f.diagnostics?.status).toBe(status);
  });

  it("never shows a status, method, path, code or body, for status 0 and every status 100-599", () => {
    const bodies = [
      "<html><body><h1>502 Bad Gateway</h1></body></html>",
      '{"detail":"reading_state_stale_revision"}',
      "Traceback (most recent call last): KeyError: 'doc'",
      "source_merge_requires_two_members",
      "",
    ];
    for (const status of [0, ...Array.from({ length: 500 }, (_, i) => i + 100)]) {
      for (const body of bodies) {
        const f = describeFailure(new ApiError(`POST /books/1/ask failed: HTTP ${status}`, status, body), {
          what: "ask the book",
        });
        expect(`${f.title} ${f.detail}`, `status ${status}`).not.toMatch(LEAK);
      }
    }
  });

  it("passes the DRW failure envelope's message through verbatim (drw-plan-failure-contract.md §4)", () => {
    const body = JSON.stringify({
      detail: {
        code: "provider_unconfigured",
        message: "No model provider is configured. Set a provider key and restart.",
        retryable: false,
      },
    });
    const f = describeFailure(new ApiError("POST /research/plans failed: HTTP 503", 503, body), {
      what: "plan the research",
    });
    expect(f.diagnostics?.serverCode).toBe("provider_unconfigured");
    expect(f.detail).toBe("No model provider is configured. Set a provider key and restart.");
    expect(f.retryable).toBe(false);
  });

  it("calls a thrown fetch offline, and an abort or time-out a timeout", () => {
    expect(describeFailure(new TypeError("Failed to fetch")).kind).toBe("offline");
    expect(describeFailure(new DOMException("The operation timed out.", "TimeoutError")).kind).toBe("timeout");
    expect(describeFailure(new DOMException("aborted", "AbortError")).kind).toBe("timeout");
  });

  it("names a response the page couldn't read, without echoing it", () => {
    const f = describeFailure(new ApiError("project tabs: malformed snapshot", 0, '{"nope":1}'), { what: "load your tabs" });
    expect(f.kind).toBe("malformed");
    expect(f.detail).not.toContain("nope");
  });

  it("treats anything else as unknown, and never echoes it", () => {
    const f = describeFailure("boom", { what: "save your notes" });
    expect(f.kind).toBe("unknown");
    expect(f.title).toBe("Couldn't save your notes.");
    expect(f.detail).not.toContain("boom");
  });

  it("passes a recognized `unknown` DRW envelope through, with the envelope's retryable", () => {
    const body = JSON.stringify({ detail: { code: "unknown", message: "whatever", retryable: false } });
    const f = describeFailure(new ApiError("POST /research/plans failed: HTTP 500", 500, body));
    expect(f.diagnostics?.serverCode).toBe("unknown");
    expect(f.detail).toBe("Something unexpected went wrong. Try again.");
    expect(f.retryable).toBe(false);
  });

  it("shows the contract headline, never the server's own message, even a hostile one", () => {
    const body = JSON.stringify({
      detail: { code: "provider_upstream_error", message: "GET /x HTTP 500 internal_problem <html>", retryable: true },
    });
    const f = describeFailure(new ApiError("POST /research/plans failed: HTTP 502", 502, body), { what: "plan the research" });
    expect(f.detail).toBe("The model provider returned an error. Retry, or check your key's quota.");
    expect(`${f.title} ${f.detail}`).not.toMatch(LEAK);
  });

  it("never echoes any non-request value", () => {
    for (const thrown of [new Error("secret GET /x HTTP 500"), null, undefined, { secret: "leak" }, 42]) {
      const f = describeFailure(thrown, { what: "load this" });
      expect(f.kind).toBe("unknown");
      expect(`${f.title} ${f.detail}`).not.toMatch(/secret|leak|42|HTTP/);
    }
  });

  it("calls a non-error status unknown and drops an impossible status from diagnostics", () => {
    expect(describeFailure(new ApiError("x", 304, "")).kind).toBe("unknown");
    expect(describeFailure(new ApiError("x", Number.NaN, "")).diagnostics?.status).toBeUndefined();
  });

  it("falls back to the plain title when `what` carries error text", () => {
    for (const what of ["GET /investigations failed: HTTP 503", "reading_state_stale_revision", "<b>x</b>"]) {
      expect(describeFailure(new ApiError("x", 500, ""), { what }).title).toBe("That didn't work.");
    }
  });
});
