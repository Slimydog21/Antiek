// SPR-06 / SPR-22 polyglot seam — user-state TS client.
//
// Wraps GET /api/users/me/is-returning. Used by the post-login routing
// resolver to distinguish a real returning operator from a first-time
// visitor without relying on the per-device localStorage proxy.
//
// Failure mode: this client races the substrate call against a
// short timeout and resolves to null on miss. The caller falls back
// to the localStorage proxy when null is returned — same posture as
// the SPR-03 ingest client's "if the substrate is unreachable, the
// TS layer keeps working with what it has."

const DEFAULT_TIMEOUT_MS = 1500;

export interface IsReturningResponse {
  user_id: string;
  is_returning: boolean;
  last_session_at: string | null;
  threshold_days: number;
}

export interface IsReturningOptions {
  userId?: string;
  thresholdDays?: number;
  timeoutMs?: number;
  /** Override fetch — used by tests. */
  fetcher?: typeof fetch;
}

/** Call the substrate's authoritative is-returning answer. Returns
 *  null on any failure (network, timeout, non-200) so the caller can
 *  fall back to the localStorage proxy. */
export async function fetchIsReturning(
  options: IsReturningOptions = {},
): Promise<IsReturningResponse | null> {
  const {
    userId = "__operator__",
    thresholdDays = 1,
    timeoutMs = DEFAULT_TIMEOUT_MS,
    fetcher = fetch,
  } = options;

  const params = new URLSearchParams({
    user_id: userId,
    threshold_days: String(thresholdDays),
  });
  const url = `/api/users/me/is-returning?${params.toString()}`;

  // AbortController gives us a hard timeout. Without one the post-
  // login resolver could stall the route for the full default
  // network timeout (often 30s+).
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetcher(url, {
      method: "GET",
      credentials: "include",
      signal: controller.signal,
    });
    if (!res.ok) return null;
    return (await res.json()) as IsReturningResponse;
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
  }
}
