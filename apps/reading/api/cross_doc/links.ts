// SPR-07 M1 — TS client for the cross_doc query endpoint.
//
// The Python implementation lives at ``services/cross_doc/query.py``.
// This module is the TypeScript boundary the reading-surface Gutter
// component imports — same polyglot-seam discipline as
// ``apps/reading/api/library/ingest.ts``.
//
// Wire status: at SPR-07 closeout the FastAPI route for cross_doc has
// not yet been written (that's a Sprint-8+ thread — the cross_doc
// query layer is operator-only and gets a REST handler when the same
// surface needs the query from a non-browser context). Until then the
// client calls the wire URL and gracefully falls back to an in-process
// stub via ``setCrossDocStub`` — the same shape ``behaviorEvents.ts``
// uses for the no-op-on-wire emit.
//
// The stub is what the Vitest tests inject; production code never
// reaches into it.

/** One pill's worth of data. Mirrors ``CrossDocLink`` in the Python
 *  layer. The ``source`` field is the leg the link came from
 *  ('similarity' / 'user_asserted' / 'citation'); the gutter pill
 *  renders the source badge from it. */
export interface CrossDocLink {
  chunk_id: string;
  doc_title: string;
  document_id: string;
  page: number;
  snippet: string;
  score: number;
  source: "similarity" | "user_asserted" | "citation";
  source_tier: number;
}

/** Input shape — mirrors ``Highlight`` in the Python layer. */
export interface CrossDocHighlight {
  document_id: string;
  page: number;
  bbox: [number, number, number, number];
  selected_text: string;
}

/** Optional client config. */
export interface CrossDocFetchOptions {
  /** Max pills the surface can render. UI default = 3 (see
   *  ``GutterPill`` comment for the rationale). */
  topK?: number;
  /** Public-graph toggle — defaults to FALSE per SPR-07 M7 and
   *  master-spec §13.9 dependency. */
  includePublicGraph?: boolean;
  /** Override for tests/preview. */
  signal?: AbortSignal;
}

/** Typed error thrown by ``fetchCrossDocLinks``. */
export class CrossDocFetchError extends Error {
  status: number;
  code: string;
  constructor(status: number, code: string, detail?: string) {
    super(`cross-doc fetch failed: ${code} (HTTP ${status})${detail ? ` — ${detail}` : ""}`);
    this.status = status;
    this.code = code;
    this.name = "CrossDocFetchError";
  }
}

/** Stub shape used by Vitest. Tests register a stub via
 *  ``setCrossDocStub`` and the client short-circuits the network call.
 *  This is intentional — there is no FastAPI handler at SPR-07
 *  closeout so production builds will fall through to the stub-or-
 *  empty path and return []. The SPR-08 sprint that adds the handler
 *  removes the stub fallback. */
export type CrossDocStub = (
  highlight: CrossDocHighlight,
  options: Required<Pick<CrossDocFetchOptions, "topK" | "includePublicGraph">>,
) => Promise<CrossDocLink[]>;

let _stub: CrossDocStub | null = null;

export function setCrossDocStub(stub: CrossDocStub | null): void {
  _stub = stub;
}

function apiBase(): string {
  const env = (import.meta as { env?: { VITE_ANTIEK_API_BASE?: string } }).env;
  return (env?.VITE_ANTIEK_API_BASE || "").replace(/\/+$/, "");
}

/** Fetch up to ``topK`` cross-doc links for a highlight.
 *
 *  Wire layer: POSTs to ``/api/cross_doc/links`` with the highlight as
 *  JSON. When the endpoint is not yet live (HTTP 404 or the wire
 *  layer rejects), we degrade to the registered stub or an empty
 *  array — the gutter surface must NEVER throw on a missing endpoint
 *  (the operator's highlight succeeded; we just have no pills to
 *  show). */
export async function fetchCrossDocLinks(
  highlight: CrossDocHighlight,
  options: CrossDocFetchOptions = {},
): Promise<CrossDocLink[]> {
  const topK = options.topK ?? 3;
  const includePublicGraph = options.includePublicGraph ?? false;

  // Stub path — used by tests and (today) by the production build,
  // because the FastAPI route hasn't shipped yet. The stub returning
  // [] is the production default until Sprint 8+ wires the handler.
  if (_stub) {
    return _stub(highlight, { topK, includePublicGraph });
  }

  // Wire path — POST. Wrap in try/catch and return [] on any failure
  // so the surface stays useful even with a broken endpoint.
  const url = `${apiBase()}/api/cross_doc/links`;
  try {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      signal: options.signal,
      body: JSON.stringify({
        highlight,
        top_k: topK,
        include_public_graph: includePublicGraph,
      }),
    });
    if (!res.ok) {
      // 404 = endpoint not yet implemented — silent empty. 4xx/5xx =
      // log via the error subclass but still return [] so the UI
      // doesn't crash a highlight session over a backend hiccup.
      if (res.status === 404) return [];
      throw new CrossDocFetchError(res.status, `http_${res.status}`);
    }
    const json = (await res.json()) as { links?: CrossDocLink[] };
    return json.links ?? [];
  } catch (err) {
    // AbortError is a normal user signal — pass [] through. Anything
    // else logs but does not crash the surface.
    if (err instanceof DOMException && err.name === "AbortError") {
      return [];
    }
    if (err instanceof CrossDocFetchError) {
      console.warn("[cross_doc] fetch failed:", err.message);
    } else {
      console.warn("[cross_doc] unexpected fetch error:", err);
    }
    return [];
  }
}
