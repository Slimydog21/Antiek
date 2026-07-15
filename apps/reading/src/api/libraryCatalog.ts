/**
 * Library catalog client (PR 797 /library contract).
 *
 * GET /library?filter=&search=&page=&page_size=
 *
 * Metadata-only summaries. Body-like keys are rejected at the client
 * boundary (§9.0 catalog honesty). Full text remains a separate route.
 */

import { API_BASE, apiFetch } from "../lib/api";
import type { Servability } from "./books";

export type LibraryFilter = "servable" | "gated" | "all";

export interface BookSummary {
  document_id: string;
  title: string | null;
  author: string | null;
  servability: Servability;
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

const SERVABILITY_VALUES = new Set<Servability>([
  "public_domain",
  "platform_authored",
  "publisher_opted_in",
  "source_declared_open",
  "gated_metadata_only",
  "taken_down",
]);
const FULL_TEXT_SERVABLE = new Set<Servability>([
  "public_domain",
  "platform_authored",
  "publisher_opted_in",
  "source_declared_open",
]);

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

function assertNoBodyKeys(
  value: unknown,
  path: string,
  seen = new WeakSet<object>(),
): void {
  if (value === null || typeof value !== "object") return;
  if (seen.has(value)) return;
  seen.add(value);
  if (Array.isArray(value)) {
    value.forEach((item, index) =>
      assertNoBodyKeys(item, `${path}[${index}]`, seen),
    );
    return;
  }
  const obj = value as Record<string, unknown>;
  for (const [key, nested] of Object.entries(obj)) {
    if ((FORBIDDEN_BODY_KEYS as readonly string[]).includes(key)) {
      throw new Error(
        `library catalog response rejected: body-like key ${key} at ${path}`,
      );
    }
    assertNoBodyKeys(nested, `${path}.${key}`, seen);
  }
}

function requireNullableString(value: unknown, path: string): string | null {
  if (value === null) return null;
  if (typeof value !== "string") {
    throw new Error(
      `library catalog response rejected: ${path} must be string or null`,
    );
  }
  return value;
}

function requireNonnegativeInteger(value: unknown, path: string): number {
  if (typeof value !== "number" || !Number.isSafeInteger(value) || value < 0) {
    throw new Error(
      `library catalog response rejected: ${path} must be a nonnegative safe integer`,
    );
  }
  return value;
}

export function parseBookSummary(raw: unknown, path = "work"): BookSummary {
  if (!raw || typeof raw !== "object") {
    throw new Error(
      `library catalog response rejected: ${path} must be object`,
    );
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
  const pageCount = requireNonnegativeInteger(
    o.page_count,
    `${path}.page_count`,
  );
  if (
    typeof o.servability !== "string" ||
    !SERVABILITY_VALUES.has(o.servability as Servability)
  ) {
    throw new Error(
      `library catalog response rejected: ${path}.servability is invalid`,
    );
  }
  const servability = o.servability as Servability;
  if (o.taken_down !== (servability === "taken_down")) {
    throw new Error(
      `library catalog response rejected: ${path}.taken_down contradicts servability`,
    );
  }
  if (o.servable_full_text !== FULL_TEXT_SERVABLE.has(servability)) {
    throw new Error(
      `library catalog response rejected: ${path}.servable_full_text contradicts servability`,
    );
  }
  return {
    document_id: o.document_id,
    title: requireNullableString(o.title, `${path}.title`),
    author: requireNullableString(o.author, `${path}.author`),
    servability,
    servable_full_text: o.servable_full_text,
    page_count: pageCount,
    cover_uri: requireNullableString(o.cover_uri, `${path}.cover_uri`),
    ip_holder_id: requireNullableString(o.ip_holder_id, `${path}.ip_holder_id`),
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
  const total = requireNonnegativeInteger(o.total, "total");
  const page = requireNonnegativeInteger(o.page, "page");
  const pageSize = requireNonnegativeInteger(o.page_size, "page_size");
  if (page < 1)
    throw new Error("library catalog response rejected: page must be >= 1");
  if (pageSize < 1 || pageSize > 200) {
    throw new Error(
      "library catalog response rejected: page_size must be in 1..200",
    );
  }
  const lastPage = Math.max(1, Math.ceil(total / pageSize));
  if (page > lastPage) {
    throw new Error(
      "library catalog response rejected: page exceeds the final page",
    );
  }
  const expectedWorks = Math.min(
    pageSize,
    Math.max(0, total - (page - 1) * pageSize),
  );
  if (o.works.length !== expectedWorks) {
    throw new Error(
      "library catalog response rejected: works length contradicts pagination metadata",
    );
  }
  return {
    works: o.works.map((w, i) => parseBookSummary(w, `works[${i}]`)),
    total,
    page,
    page_size: pageSize,
  };
}

export async function fetchLibraryCatalog(
  req: LibraryCatalogRequest = {},
): Promise<LibraryPage> {
  if (
    req.page !== undefined &&
    (!Number.isSafeInteger(req.page) || req.page < 1)
  ) {
    throw new RangeError("library catalog page must be a positive integer");
  }
  if (
    req.page_size !== undefined &&
    (!Number.isSafeInteger(req.page_size) ||
      req.page_size < 1 ||
      req.page_size > 200)
  ) {
    throw new RangeError(
      "library catalog page_size must be an integer in 1..200",
    );
  }
  const params = new URLSearchParams();
  params.set("filter", req.filter ?? "all");
  if (req.search) params.set("search", req.search);
  if (req.page !== undefined) params.set("page", String(req.page));
  if (req.page_size !== undefined)
    params.set("page_size", String(req.page_size));

  const res = await apiFetch(`${API_BASE}/library?${params.toString()}`, {
    method: "GET",
  });
  const raw = await readOkBody(res);
  const page = parseLibraryPage(raw);
  const expectedPage = req.page ?? 1;
  const expectedPageSize = req.page_size ?? 20;
  if (page.page !== expectedPage || page.page_size !== expectedPageSize) {
    throw new Error(
      "library catalog response rejected: returned pagination does not match request",
    );
  }
  return page;
}

export function formatServability(summary: BookSummary): string {
  if (summary.taken_down) return "taken down";
  if (summary.servable_full_text) return "servable HTML/full-text";
  return `gated (${summary.servability})`;
}
