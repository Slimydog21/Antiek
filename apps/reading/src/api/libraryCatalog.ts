/**
 * Library catalog client (PR #797 /library contract).
 *
 * GET /library?filter=&search=&page=&page_size=
 *
 * Metadata-only summaries. Body-like keys are rejected at the client
 * boundary (§9.0 catalog honesty). Full text remains a separate route.
 */

import { API_BASE, apiFetch } from "../lib/api";

export type LibraryFilter = "servable" | "gated" | "all";

export interface BookSummary {
  document_id: string;
  title: string | null;
  author: string | null;
  servability: string;
  servable_full_text: boolean;
  page_count: number;
  cover_uri: string | null;
  ip_holder_id: string | null;
  taken_down: boolean;
}

export interface LibraryPage {
  works: BookSummary[];
  total: number;
  page: number;
  page_size: number;
}

export interface LibraryCatalogRequest {
  filter?: LibraryFilter;
  search?: string;
  page?: number;
  page_size?: number;
}

/** Forbidden on catalog summaries — never invent/allow body payloads here. */
export const FORBIDDEN_BODY_KEYS = [
  "raw_text",
  "full_text",
  "body",
  "body_text",
  "content",
  "served_body",
  "text",
] as const;

export class LibraryCatalogHttpError extends Error {
  readonly status: number;
  readonly body: string;

  constructor(status: number, body: string) {
    super(`library catalog API ${status}: ${body.slice(0, 200)}`);
    this.name = "LibraryCatalogHttpError";
    this.status = status;
    this.body = body;
  }
}

async function readOkBody(res: Response): Promise<unknown> {
  if (!res.ok) {
    const text = await res.text();
    throw new LibraryCatalogHttpError(res.status, text);
  }
  return res.json() as Promise<unknown>;
}

function assertNoBodyKeys(obj: Record<string, unknown>, path: string): void {
  for (const k of FORBIDDEN_BODY_KEYS) {
    if (k in obj) {
      throw new Error(
        `library catalog response rejected: body-like key ${k} at ${path}`,
      );
    }
  }
}

export function parseBookSummary(raw: unknown, path = "work"): BookSummary {
  if (!raw || typeof raw !== "object") {
    throw new Error(`library catalog response rejected: ${path} must be object`);
  }
  const o = raw as Record<string, unknown>;
  assertNoBodyKeys(o, path);
  if (typeof o.document_id !== "string" || !o.document_id.trim()) {
    throw new Error(
      `library catalog response rejected: ${path}.document_id required`,
    );
  }
  if (typeof o.servable_full_text !== "boolean") {
    throw new Error(
      `library catalog response rejected: ${path}.servable_full_text must be boolean`,
    );
  }
  if (typeof o.taken_down !== "boolean") {
    throw new Error(
      `library catalog response rejected: ${path}.taken_down must be boolean`,
    );
  }
  if (typeof o.page_count !== "number" || !Number.isFinite(o.page_count)) {
    throw new Error(
      `library catalog response rejected: ${path}.page_count must be finite number`,
    );
  }
  if (typeof o.servability !== "string") {
    throw new Error(
      `library catalog response rejected: ${path}.servability must be string`,
    );
  }
  return {
    document_id: o.document_id,
    title: o.title === null || o.title === undefined ? null : String(o.title),
    author:
      o.author === null || o.author === undefined ? null : String(o.author),
    servability: o.servability,
    servable_full_text: o.servable_full_text,
    page_count: o.page_count,
    cover_uri:
      o.cover_uri === null || o.cover_uri === undefined
        ? null
        : String(o.cover_uri),
    ip_holder_id:
      o.ip_holder_id === null || o.ip_holder_id === undefined
        ? null
        : String(o.ip_holder_id),
    taken_down: o.taken_down,
  };
}

export function parseLibraryPage(body: unknown): LibraryPage {
  if (!body || typeof body !== "object") {
    throw new Error("library catalog response must be an object");
  }
  const o = body as Record<string, unknown>;
  assertNoBodyKeys(o, "page");
  if (!Array.isArray(o.works)) {
    throw new Error("library catalog response rejected: works must be array");
  }
  if (typeof o.total !== "number" || !Number.isFinite(o.total) || o.total < 0) {
    throw new Error("library catalog response rejected: total must be nonnegative number");
  }
  if (typeof o.page !== "number" || !Number.isFinite(o.page) || o.page < 1) {
    throw new Error("library catalog response rejected: page must be >= 1");
  }
  if (
    typeof o.page_size !== "number" ||
    !Number.isFinite(o.page_size) ||
    o.page_size < 1
  ) {
    throw new Error("library catalog response rejected: page_size must be >= 1");
  }
  return {
    works: o.works.map((w, i) => parseBookSummary(w, `works[${i}]`)),
    total: o.total,
    page: o.page,
    page_size: o.page_size,
  };
}

export async function fetchLibraryCatalog(
  req: LibraryCatalogRequest = {},
): Promise<LibraryPage> {
  const params = new URLSearchParams();
  params.set("filter", req.filter ?? "all");
  if (req.search) params.set("search", req.search);
  if (req.page !== undefined) params.set("page", String(req.page));
  if (req.page_size !== undefined) params.set("page_size", String(req.page_size));

  const res = await apiFetch(`${API_BASE}/library?${params.toString()}`, {
    method: "GET",
  });
  const raw = await readOkBody(res);
  return parseLibraryPage(raw);
}

export function formatServability(summary: BookSummary): string {
  if (summary.taken_down) return "taken down";
  if (summary.servable_full_text) return "servable HTML/full-text";
  return `gated (${summary.servability})`;
}
