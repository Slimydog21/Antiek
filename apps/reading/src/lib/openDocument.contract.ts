// ─────────────────────────────────────────────────────────────────────────
// openDocument — the ONE door contract (antiek-reader SPR-01 M3).
//
// THIS FILE IS TYPES + JSDoc ONLY. It ships NO implementation. SPR-05
// implements `openDocument`, routes every open-a-document affordance through
// it, and deletes the four redundant renderers. SPR-01 pins the signature so
// downstream call sites can type-import it TODAY (the seam other sprints
// compose against without re-litigating its shape).
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
 * - `chunkId`  — scroll to the block/region that a graph chunk maps to (the
 *                "open in document" affordance from a research ChunkModal / a
 *                citation). The Reader resolves chunkId → Region internally.
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
 * Every open-a-document affordance routes through this single function — see
 * `~/specs/antiek-reader/migration-map.md` for the exhaustive door list SPR-05
 * must converge. `/wrestle` is killed as an OPEN target (its upload affordance
 * survives only as an INGEST entry point).
 *
 * ── REQUIRED RIGHTS/TIER SEAM (binding on the SPR-05 implementation) ────────
 * `openDocument` MUST consult the serve gate BEFORE mounting the Reader. The
 * authoritative gate is the backend `substrate.books.serve.serve_full_text`
 * (deny-by-default; §9.0 Hachette/Bartz legal gate), surfaced to the frontend
 * over `GET /books/{documentId}/full-text` (which routes through
 * `serve_full_text_guarded` — `interfaces/research/api/books.py`). The response
 * carries the servability verdict (`serves_full_text` / `servable`), the
 * snippet-vs-full-text body, and the arXiv rights context (`tier`,
 * `ad_eligible`, `canonical_url`, `license`). The Reader renders the FULL
 * typed-block body only when the gate returns it; a gated document renders its
 * snippet/metadata view, a taken-down document renders the takedown notice.
 * SPR-05 MUST NOT route around this gate (a second, ungated fetch path would
 * re-open the §9.0 leak). The owner/personal-reading full-read switch
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
 * The props the ONE `<Reader>` mounts with (SPR-03 builds the component; SPR-05
 * wires `openDocument` to mount it). The Reader fetches the typed-block
 * `Document` (document_model.gen.ts) for `documentId` through the gated
 * endpoint above; `page` / `chunkId` / `highlight` position it.
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
 * The shape of the gated serve response `openDocument` consults before
 * mounting. Documented here (not a fetch impl) so SPR-05's gate call is typed
 * against the contract, not an ad-hoc object.
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
