// ─────────────────────────────────────────────────────────────────────────
// openDocument — the ONE door contract (antiek-reader SPR-01 M3).
//
// THIS FILE IS TYPES + JSDoc ONLY. It ships NO implementation. The runtime
// implementation lives in `openDocument.ts`, routes open-a-document affordances
// through `/read/:documentId`, and keeps redundant renderers out of production
// doors. SPR-01 pinned the signature so downstream call sites can type-import
// the seam without re-litigating its shape.
//
// The diagnosis this closes (master spec): four-plus renderers exist by
// accident and several doors (ChunkModal, DocumentsIndex, the CommandPalette
// document action) currently navigate to `/wrestle/{id}` (the pdf.js page-1
// surface) instead of the real Reader. `openDocument` is the single resolver
// every tab calls; there is exactly ONE Reader behind it (the
// `reading_surface.py` invariant, now enforced by SPR-09's conformance test).
// ─────────────────────────────────────────────────────────────────────────

import type { Region } from "../types/document_model.gen";

/**
 * Options for opening a document. All optional — `openDocument(id)` opens the
 * whole document in read mode.
 *
 * - `page`     — jump to a page (for documents with a paginated/original view).
 * - `chunkId`  — scroll to the page/region that a graph chunk maps to (the
 *                "open in document" affordance from a research ChunkModal / a
 *                citation). The Reader may resolve chunkId to a page; it does
 *                not fabricate a SPR-01 Region block id from the chunk.
 * - `highlight`— a span (in document space) to highlight on open — e.g. a
 *                Write trace-to-source landing on the cited passage, or a
 *                deep-research "cite source" jump. `Region` is the SAME type
 *                the `ReaderSurfaceContract` (reading_surface.py) pins, shared
 *                via codegen so frontend and backend never drift.
 * - `mode`     — `'read'` (the typeset reading register, default) or
 *                `'inspect'` (the provenance/raw view — "view original" toggle).
 */
export interface OpenDocumentOptions {
  page?: number;
  chunkId?: string;
  highlight?: Region;
  mode?: "read" | "inspect";
}

/**
 * Open a document in the ONE Reader.
 *
 * Every production open-a-document affordance routes through this single
 * function. `/wrestle` is killed as an OPEN target (its upload affordance
 * survives only as an INGEST entry point).
 *
 * ── REQUIRED RIGHTS/TIER SEAM ───────────────────────────────────────────────
 * `openDocument` MUST NOT route around the serve gate. The authoritative gate
 * is the backend `substrate.books.serve.serve_full_text` (deny-by-default; §9.0
 * Hachette/Bartz legal gate), surfaced to the frontend over
 * `GET /books/{documentId}/full-text` (which routes through
 * `serve_full_text_guarded` — `interfaces/research/api/books.py`). The runtime
 * resolver may stay a thin navigation function, but the mounted Reader route
 * MUST fetch through that endpoint and render the FULL typed-block body only
 * when the gate returns it. A gated document renders its snippet/metadata view,
 * a taken-down document renders the takedown notice. A second, ungated fetch
 * path would re-open the §9.0 leak. The owner/personal-reading full-read switch
 * (`serve_full_text(..., owner=True)`) is the only widening, and only for the
 * operator's own fetched third-party content.
 *
 * Returns void: it navigates/mounts as a side effect (it does not return the
 * document — the Reader fetches the typed model via the gated endpoint).
 */
export type OpenDocument = (
  documentId: string,
  opts?: OpenDocumentOptions,
) => void;

/**
 * The route-level props for the ONE Reader surface. BookReader fetches the
 * typed-block `Document` (document_model.gen.ts) for `documentId` through the
 * gated endpoint above; `page` / `chunkId` / `highlight` position it.
 *
 * There is exactly one component with this prop shape — the "compose, don't
 * fork" invariant. SPR-09's conformance test asserts no second document
 * renderer is importable in the production bundle.
 */
export interface ReaderProps {
  documentId: string;
  page?: number;
  chunkId?: string;
  /** A span (document space) to highlight on open. */
  highlight?: Region;
  /** Read (typeset) vs inspect (provenance/original) register. Default 'read'. */
  mode?: "read" | "inspect";
}

/**
 * The shape of the gated serve response the Reader route consults before
 * rendering the full body. Documented here (not a fetch impl) so gate checks are
 * typed against the contract, not an ad-hoc object.
 *
 * Field names mirror the REAL `FullTextResponse` returned by
 * `GET /books/{document_id}/full-text` (`interfaces/research/api/books.py`),
 * which is the JSON projection of `ServeResult` (`substrate/books/serve.py`).
 * NOTE (verified): this endpoint's servability field is `servable` (a boolean
 * derived from the deny-by-default gate) — `full_text` is populated ONLY when
 * `servable === true`; a gated document returns `snippet`; a taken-down or
 * not-found document returns neither. `servable === false` ⇒ the Reader MUST
 * NOT render the full typed body. (A 404 is returned when `found` is false, so
 * a successful response always describes a real document.)
 */
export interface ServeGateResult {
  document_id: string;
  /** Deny-by-default §9.0 answer. False ⇒ render snippet/metadata, never full. */
  servable: boolean;
  /** The classifier status string (e.g. "servable" / "gated" / "taken_down"). */
  servability: string | null;
  /** Populated ONLY when servable === true. */
  full_text: string | null;
  /** Populated for gated documents. */
  snippet: string | null;
  title: string | null;
  author: string | null;
  /** Human-readable denial reason (audit / messaging). */
  reason: string;
  /** arXiv rights context (null for non-arXiv documents). */
  tier?: string | null;
  ad_eligible?: boolean;
  canonical_url?: string | null;
  license?: string | null;
}
