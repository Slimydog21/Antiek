// ─────────────────────────────────────────────────────────────────────────
// openDocument — the ONE door resolver (antiek-reader SPR-05 M1).
//
// SPR-01 pinned the `OpenDocument` type contract (openDocument.contract.ts —
// types + JSDoc only). SPR-03 built the one `<Reader>`, mounted by `BookReader`
// at the `/read/:documentId` route, which already fetches the typed-block body
// through the §9.0-gated `GET /books/{id}/full-text` endpoint and refuses to
// rich-render a withheld body (deny-by-default, enforced in BookReader). THIS
// file is the SPR-05 resolver every open-a-document door calls instead of
// re-implementing a renderer or `navigate('/wrestle/:id')`.
//
// ── Why navigation, not a bespoke mount ──────────────────────────────────
// The one Reader is route-mounted (`/read/:documentId` → BookReader → the one
// `<Reader>`). `openDocument` therefore RESOLVES to that route: it never
// constructs a second renderer, and it never re-implements the gate. The
// authoritative serve boundary is the route's own fetch (BookReader's
// §9.0-defended `structuredDoc` gate over the `/full-text` response). This
// keeps deny-by-default in exactly one place (rigor #4: "only CALL the gate").
//
// ── The serve gate (§9.0) ────────────────────────────────────────────────
// `checkServeGate` is a PRE-FLIGHT over the SAME `/books/{id}/full-text`
// endpoint (`serve_full_text_guarded`) the Reader consults — it never opens a
// SECOND, ungated fetch path. A caller that wants an honest deny/not-found
// BEFORE navigating (no flash of an empty reader) consults it; the route's gate
// is the load-bearing enforcement regardless. A 404 ⇒ missing (honest
// not-found); `servable === false` ⇒ gated (the Reader shows the snippet/deny
// panel, never the full body); `servable === true` ⇒ open.
// ─────────────────────────────────────────────────────────────────────────

import { useCallback } from "react";
import { useNavigate } from "react-router-dom";

import type {
  OpenDocument,
  OpenDocumentOptions,
  ServeGateResult,
} from "./openDocument.contract";
import { getBookFullText } from "../api/books";

/** sessionStorage key the reader's `usePosition` reads to land on a page. The
 *  `page` opt seeds it (the existing Library / MetaReading precedent — no new
 *  mechanism), so the reader opens on the requested page. */
const READ_POS_KEY = (documentId: string) => `antiek.read.pos.${documentId}`;

/**
 * Build the `/read/:documentId` target (path + search) the one Reader mounts
 * on, encoding the opts the Reader reads back. Pure (no navigation, no
 * storage) so it is unit-testable and reusable (e.g. an `<a href>` door).
 *
 *  - `page`      → carried both as `?page=` AND seeded into the sessionStorage
 *                  locator via `seedReadPosition` (the existing reader reads the
 *                  locator; the query param is the explicit, shareable record).
 *  - `chunkId`   → `?chunk=` (the Reader resolves chunk → block/region).
 *  - `highlight` → `?hl=document_id:block_id[:char_start-char_end]` — a compact
 *                  encoding of the SPR-01 `Region` the Reader anchors to.
 *  - `mode`      → `?mode=inspect` (the "view original" register). 'read' (the
 *                  default) is omitted to keep the URL clean.
 */
export function buildReaderTarget(
  documentId: string,
  opts?: OpenDocumentOptions,
): { path: string; search: string } {
  const path = `/read/${encodeURIComponent(documentId)}`;
  const params = new URLSearchParams();
  if (opts?.page !== undefined && opts.page !== null && opts.page >= 0) {
    params.set("page", String(opts.page));
  }
  if (opts?.chunkId) {
    params.set("chunk", opts.chunkId);
  }
  if (opts?.highlight) {
    params.set("hl", encodeRegion(opts.highlight));
  }
  if (opts?.mode && opts.mode !== "read") {
    params.set("mode", opts.mode);
  }
  const search = params.toString();
  return { path, search: search ? `?${search}` : "" };
}

/** Compact `Region` encoding for the `?hl=` param. A whole-block region omits
 *  the char range; a sub-block highlight carries `:start-end`. Symmetric with
 *  `decodeRegion`. The pieces are encoded so an id containing a ':' survives. */
export function encodeRegion(region: import("../types/document_model.gen").Region): string {
  const head = `${encodeURIComponent(region.document_id)}:${encodeURIComponent(region.block_id)}`;
  if (
    region.char_start !== undefined &&
    region.char_start !== null &&
    region.char_end !== undefined &&
    region.char_end !== null
  ) {
    return `${head}:${region.char_start}-${region.char_end}`;
  }
  return head;
}

/** Inverse of `encodeRegion`. Returns null for a malformed token (honest — the
 *  Reader then opens without a highlight rather than anchoring to a bad span). */
export function decodeRegion(
  token: string | null,
): import("../types/document_model.gen").Region | null {
  if (!token) return null;
  const parts = token.split(":");
  if (parts.length < 2) return null;
  const document_id = decodeURIComponent(parts[0]);
  const block_id = decodeURIComponent(parts[1]);
  if (!document_id || !block_id) return null;
  const region: import("../types/document_model.gen").Region = { document_id, block_id };
  if (parts.length >= 3) {
    const m = parts[2].match(/^(\d+)-(\d+)$/);
    if (m) {
      const start = parseInt(m[1], 10);
      const end = parseInt(m[2], 10);
      if (Number.isFinite(start) && Number.isFinite(end) && end >= start) {
        region.char_start = start;
        region.char_end = end;
      }
    }
  }
  return region;
}

/** Seed the reader's page locator so it opens on the requested page (the
 *  existing sessionStorage convention `usePosition` owns — not a new path).
 *  Best-effort: private-mode storage failures are swallowed (the reader still
 *  opens, just at its saved page). */
export function seedReadPosition(documentId: string, page: number | undefined | null): void {
  if (page === undefined || page === null || page < 0) return;
  try {
    window.sessionStorage.setItem(READ_POS_KEY(documentId), String(page));
  } catch {
    /* private mode — the reader still opens, just not at the seeded page */
  }
}

/**
 * Pre-flight the §9.0 serve gate for a document (the SAME `/full-text`
 * endpoint the Reader consults — never a second, ungated path). Deny-by-default:
 *
 *  - a 404 ⇒ `{ found: false }` (honest not-found);
 *  - `servable === false` ⇒ `{ found: true, servable: false }` (gated — the
 *    Reader will show the snippet/deny panel, never the full body);
 *  - `servable === true` ⇒ `{ found: true, servable: true }` (open the body).
 *
 * Callers use this to render an honest state BEFORE navigation; the route's own
 * gate enforces regardless (defense in depth). It NEVER widens the gate.
 */
export interface ServeGateVerdict {
  found: boolean;
  servable: boolean;
  reason: string | null;
  result: ServeGateResult | null;
}

export async function checkServeGate(documentId: string): Promise<ServeGateVerdict> {
  try {
    const r = await getBookFullText(documentId);
    return {
      found: true,
      servable: r.servable === true,
      reason: r.reason ?? null,
      // The api client's FullTextResponse is the JSON projection of the gate
      // result; surface the fields the contract's ServeGateResult names.
      result: {
        document_id: r.document_id,
        servable: r.servable,
        servability: r.servability,
        full_text: r.full_text,
        snippet: r.snippet,
        title: r.title,
        author: r.author,
        reason: r.reason,
        tier: r.tier,
        ad_eligible: r.ad_eligible,
        canonical_url: r.canonical_url,
        license: r.license,
      },
    };
  } catch (e: unknown) {
    if (e instanceof Error && e.message === "book_not_found") {
      return { found: false, servable: false, reason: "not_found", result: null };
    }
    // A network/other error is NOT a servability verdict — surface it honestly
    // (deny-by-default: we do not treat an unknown error as "servable").
    return {
      found: false,
      servable: false,
      reason: e instanceof Error ? e.message : String(e),
      result: null,
    };
  }
}

/**
 * The ONE door, as a hook. Returns an `OpenDocument` (the SPR-01 contract type)
 * that resolves a document by id and navigates to the one Reader route,
 * forwarding the opts. Every open-a-document affordance calls THIS instead of
 * navigating to `/wrestle/:id` or mounting a bespoke renderer.
 *
 * The route's mount (BookReader) consults the §9.0 gate and shows an honest
 * gated/not-found state for a withheld/missing doc — so `openDocument` itself
 * stays a thin, synchronous navigation (no flash-of-gate logic duplicated
 * here). A caller that wants to gate BEFORE navigating uses `checkServeGate`.
 */
export function useOpenDocument(): OpenDocument {
  const navigate = useNavigate();
  return useCallback<OpenDocument>(
    (documentId: string, opts?: OpenDocumentOptions): void => {
      if (!documentId) return; // a door with no resolvable target is a no-op (honest)
      seedReadPosition(documentId, opts?.page);
      const { path, search } = buildReaderTarget(documentId, opts);
      navigate(`${path}${search}`);
    },
    [navigate],
  );
}
