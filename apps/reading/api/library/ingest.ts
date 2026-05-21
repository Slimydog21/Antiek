// SPR-03 / M1 — Universal-library ingestion API client.
//
// The actual ingest endpoint is FastAPI Python (see
// interfaces/research/api/library.py for the route handler). This
// module is the TypeScript client that SPR-06 (Reading UI) imports
// so the consumer-facing paste-URL flow has typed call sites and
// doesn't string-format its own URLs.
//
// Why a client wrapper rather than fetch() inline at the call site:
// the polyglot-seam discipline (architecture_notes §11.1) puts the
// contract in one place. If the URL shape or status semantics ever
// shift, SPR-06's components don't need to know.

import type {
  IngestJob,
  IngestJobStatus,
  IngestRequest,
  IngestResponse,
} from "./types";

/** Base URL for the substrate API. Resolved at runtime so dev,
 *  staging, and prod can point at different origins via
 *  ``VITE_ANTIEK_API_BASE``. */
function apiBase(): string {
  const env = (import.meta as { env?: { VITE_ANTIEK_API_BASE?: string } }).env;
  return (env?.VITE_ANTIEK_API_BASE || "").replace(/\/+$/, "");
}

/** POST a URL to the universal-library ingest endpoint.
 *  Returns the initial response — caller polls ``getIngestJob`` if
 *  status is not yet terminal. */
export async function postIngest(
  body: IngestRequest,
  init?: RequestInit,
): Promise<IngestResponse> {
  const url = `${apiBase()}/api/library/ingest`;
  const res = await fetch(url, {
    ...init,
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    credentials: "include",  // ANTIEK_SESSION cookie
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    if (res.status === 400 || res.status === 401) {
      const detail = await res.json().catch(() => ({}));
      throw new IngestError(res.status, detail?.error?.code || `http_${res.status}`, detail);
    }
    throw new IngestError(res.status, `http_${res.status}`, {});
  }
  return res.json() as Promise<IngestResponse>;
}

/** GET the current state of an in-flight ingest job. */
export async function getIngestJob(
  jobId: string,
  init?: RequestInit,
): Promise<IngestJob> {
  const url = `${apiBase()}/api/library/ingest/${encodeURIComponent(jobId)}`;
  const res = await fetch(url, {
    ...init,
    method: "GET",
    credentials: "include",
  });
  if (!res.ok) {
    throw new IngestError(res.status, `http_${res.status}`, {});
  }
  return res.json() as Promise<IngestJob>;
}

/** Options for ``pollUntilTerminal``. */
export interface PollOptions {
  intervalMs?: number;
  timeoutMs?: number;
  onUpdate?: (job: IngestJob) => void;
}

/** Helper: poll until the job is in a terminal state.
 *  ``onUpdate`` fires each tick so the UI can render progress. */
export async function pollUntilTerminal(
  jobId: string,
  opts: PollOptions = {},
): Promise<IngestJob> {
  const intervalMs = opts.intervalMs ?? 1500;
  const timeoutMs = opts.timeoutMs ?? 90_000;
  const onUpdate = opts.onUpdate;
  const start = Date.now();
  // Loop until terminal or timeout.
  // eslint-disable-next-line no-constant-condition
  while (true) {
    const job = await getIngestJob(jobId);
    onUpdate?.(job);
    if (job.status === "succeeded" || job.status === "failed") {
      return job;
    }
    if (Date.now() - start > timeoutMs) {
      throw new IngestError(0, "poll_timeout", { jobId });
    }
    await new Promise((r) => setTimeout(r, intervalMs));
  }
}

/** Typed error thrown by ingest client methods. */
export class IngestError extends Error {
  status: number;
  code: string;
  detail: unknown;
  constructor(status: number, code: string, detail: unknown) {
    super(`ingest failed: ${code} (HTTP ${status})`);
    this.status = status;
    this.code = code;
    this.detail = detail;
  }
}

export type { IngestJob, IngestJobStatus, IngestRequest, IngestResponse };
