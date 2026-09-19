import { API_BASE, ApiError, apiFetch } from "../lib/api";

export type HtmlDocumentResolver = "hosted_document" | "engagement_document";
export type HtmlDocumentResumeRef = {
  resolver: HtmlDocumentResolver;
  document_id: string;
};
export type HydratedHtmlDocument = HtmlDocumentResumeRef & {
  schema_version: 1;
  title: string;
  view_format: "html";
  html: string;
};

function exactObject(value: unknown, keys: readonly string[]): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new Error("invalid HTML document reference response");
  }
  const object = value as Record<string, unknown>;
  const expected = [...keys].sort();
  const actual = Object.keys(object).sort();
  if (actual.length !== expected.length || actual.some((key, index) => key !== expected[index])) {
    throw new Error("invalid HTML document reference response");
  }
  return object;
}

export function isHtmlDocumentIdentifier(value: unknown): value is string {
  return typeof value === "string"
    && value.length > 0
    && value === value.trim()
    && new TextEncoder().encode(value).length <= 512
    && !/[\u0000-\u001f\u007f-\u009f]/u.test(value);
}

export function parseHtmlDocumentResumeRef(value: unknown): HtmlDocumentResumeRef | null {
  try {
    const object = exactObject(value, ["resolver", "document_id"]);
    if (
      (object.resolver !== "hosted_document" && object.resolver !== "engagement_document")
      || !isHtmlDocumentIdentifier(object.document_id)
    ) {
      return null;
    }
    return { resolver: object.resolver, document_id: object.document_id };
  } catch {
    return null;
  }
}

export function parseHydratedHtmlDocument(
  value: unknown,
  expected: HtmlDocumentResumeRef,
): HydratedHtmlDocument {
  const object = exactObject(value, [
    "schema_version", "resolver", "document_id", "title", "view_format", "html",
  ]);
  if (
    object.schema_version !== 1
    || object.resolver !== expected.resolver
    || object.document_id !== expected.document_id
    || !isHtmlDocumentIdentifier(object.document_id)
    || typeof object.title !== "string"
    || !object.title.trim()
    || object.view_format !== "html"
    || typeof object.html !== "string"
    || !object.html.trim()
    || object.html.trimStart().toLowerCase().startsWith("%pdf")
    || !/^\s*(?:<!doctype\s+html\b|<html\b)/iu.test(object.html)
  ) {
    throw new Error("invalid HTML document reference response");
  }
  return {
    schema_version: 1,
    resolver: expected.resolver,
    document_id: expected.document_id,
    title: object.title,
    view_format: "html",
    html: object.html,
  };
}

export async function fetchHtmlDocumentReference(
  reference: HtmlDocumentResumeRef,
  signal?: AbortSignal,
): Promise<HydratedHtmlDocument> {
  const response = await apiFetch(
    `${API_BASE}/account/html-document-refs/${reference.resolver}/${encodeURIComponent(reference.document_id)}`,
    { signal, cache: "no-store" },
  );
  if (!response.ok) {
    throw new ApiError(
      "HTML document reference is unavailable",
      response.status,
      await response.text(),
    );
  }
  return parseHydratedHtmlDocument(await response.json(), reference);
}
