/**
 * contracts/anchor.ts — the highlight anchor every opener carries (SPR-06
 * M1/M4). ENTRY-SAFE: `import type` only toward the lazy chunk; the only
 * value code here is pure (and one `crypto.subtle` digest for the writer).
 *
 * `version` is REQUIRED: absence is a typed reason, never a missing key and
 * never "version 0". The wire shape is `BranchAnchor` (tabTree.ts:77-85);
 * `toBranchAnchor` is the only projection and it emits `source_locator`
 * only when the anchor already carries document-global scalar offsets AND a
 * selection digest (§1.4c rules 7/8/12). No producer does today: the
 * reader's locateSelection yields chunk-relative UTF-16 indices and the
 * only digest is the chunk's `node_text_sha256`, which is NOT the selection
 * digest (rule 8), so it never becomes `text_sha256`. `region_id` is a
 * per-projection RegionStore id and is never emitted.
 */
import type { BookAnchor } from "../../lib/api";
import type { BranchAnchor } from "../tabTree";

export type DocumentVersion =
  /** Reader: the chunk digest, BookAnchorPayload/AnchorMapChunk.node_text_sha256.
   *  The WHOLE-CHUNK digest, not the selection digest (rule 8). */
  | { kind: "node_text_sha256"; nodeId: string; sha256: string }
  /** Artifact feedback: src/api/feedback.ts FeedbackThread.artifact {version, content_sha256}. */
  | { kind: "artifact_version"; version: number; contentSha256: string }
  /** Writer: sha256(prose_text) at capture; no server revision exists. */
  | { kind: "prose_text_sha256"; sha256: string }
  /** Explicit absence with its reason; shown as unversioned, never as version 0.
   *  "reformat_forged_anchor": ReformatFlow.tsx:69 returns `{anchor_id}` cast
   *  as a BookAnchor with no payload; spawnFlows omits documentAnchor for it. */
  | { kind: "unversioned"; reason: "reader_page_only" | "writer_prose_block_unpersisted" | "metadata_only_anchor" | "reformat_forged_anchor" };

export type DocumentAnchorKind = "text" | "page" | "block";

export type AnchorRange =
  /** Reader text. unit: locateSelection counts UTF-16 (JS indices);
   *  artifactFeedbackSelection and the pinned payload count scalars. basis:
   *  "chunk" = offsets relative to the chunk's body_start (today's only
   *  producers); "document" = §1.4c document-global. selectionSha256 =
   *  sha256(utf8(projection[start:end])) (rule 8) and exists ONLY with basis
   *  "document" + unit "scalar". No producer sets it today. */
  | { kind: "text"; nodeId: string; start: number; end: number; unit: "utf16" | "scalar"; basis: "chunk" | "document"; selectionSha256?: string }
  /** BranchAnchor.page_index / BookAnchor.page_index_hint. A pagination artifact, never identity. */
  | { kind: "page"; pageIndex: number }
  /** Writer: BackendLocator (Write/Editor/locator.ts:48). Only sectionId/outlineBlockId are server-stable. */
  | { kind: "block"; sectionId: string; outlineBlockId: string | null; paragraphIndex: number | null; editorBlockId?: string };

export interface QuoteHint { quote: string; prefix: string; suffix: string }

interface AnchorBase {
  version: DocumentVersion;
  /** === range.kind, guard-enforced. */
  kind: DocumentAnchorKind;
  range: AnchorRange;
  /** null = withheld (§9.0 outboundText null) or metadata-only. Never an empty string. */
  quoteHint: QuoteHint | null;
}

/** Reader book: documentId is a book id (the companion/crossPane document space). */
export interface BookDocumentAnchor extends AnchorBase {
  space: "book";
  /** BookAnchor.document_id. */
  documentId: string;
  kind: "text" | "page";
  /** A pagination hint for a text anchor (BookAnchor.page_index_hint, the
   *  reader's current page). Never identity; absent when unknown. A page
   *  anchor carries its page in `range` instead. */
  pageIndex?: number;
  /** BookAnchor.anchor_id once pinned. */
  anchorId?: string;
  /** BookAnchor.investigation_id after link (first-link-wins). */
  investigationId?: string;
  status?: BookAnchor["status"];
}

/** Writer deliverable: NOT a book id. Never reaches crossPane or the companion documentId. */
export interface DeliverableDocumentAnchor extends AnchorBase {
  space: "deliverable";
  deliverableId: string;
  kind: "block";
}

export type DocumentAnchor = BookDocumentAnchor | DeliverableDocumentAnchor;

const isObject = (v: unknown): v is Record<string, unknown> =>
  typeof v === "object" && v !== null && !Array.isArray(v);
const nonEmpty = (v: unknown): v is string => typeof v === "string" && v.length > 0;
const SHA256_HEX = /^[0-9a-f]{64}$/;
const UNVERSIONED_REASONS: ReadonlySet<unknown> = new Set([
  "reader_page_only", "writer_prose_block_unpersisted", "metadata_only_anchor", "reformat_forged_anchor",
]);
const BOOK_STATUS: ReadonlySet<unknown> = new Set(["active", "drifted", "orphaned"]);

function isVersion(v: unknown): v is DocumentVersion {
  if (!isObject(v)) return false;
  switch (v.kind) {
    case "node_text_sha256": return nonEmpty(v.nodeId) && nonEmpty(v.sha256);
    case "artifact_version": return typeof v.version === "number" && nonEmpty(v.contentSha256);
    case "prose_text_sha256": return nonEmpty(v.sha256);
    case "unversioned": return UNVERSIONED_REASONS.has(v.reason);
    default: return false;
  }
}

function isRange(v: unknown): v is AnchorRange {
  if (!isObject(v)) return false;
  switch (v.kind) {
    case "text":
      return nonEmpty(v.nodeId) && typeof v.start === "number" && typeof v.end === "number" &&
        (v.unit === "utf16" || v.unit === "scalar") && (v.basis === "chunk" || v.basis === "document") &&
        (v.selectionSha256 === undefined || typeof v.selectionSha256 === "string");
    case "page":
      return typeof v.pageIndex === "number";
    case "block":
      return nonEmpty(v.sectionId) && (v.outlineBlockId === null || typeof v.outlineBlockId === "string") &&
        (v.paragraphIndex === null || typeof v.paragraphIndex === "number") &&
        (v.editorBlockId === undefined || typeof v.editorBlockId === "string");
    default:
      return false;
  }
}

function isQuoteHint(v: unknown): v is QuoteHint | null {
  if (v === null) return true;
  return isObject(v) && nonEmpty(v.quote) && typeof v.prefix === "string" && typeof v.suffix === "string";
}

export function isDocumentAnchor(v: unknown): v is DocumentAnchor {
  if (!isObject(v)) return false;
  if (!isVersion(v.version) || !isRange(v.range) || !isQuoteHint(v.quoteHint)) return false;
  if (v.kind !== v.range.kind) return false;
  if (v.space === "book") {
    if (!nonEmpty(v.documentId)) return false;
    if (v.kind !== "text" && v.kind !== "page") return false;
    if (v.pageIndex !== undefined && typeof v.pageIndex !== "number") return false;
    if (v.anchorId !== undefined && !nonEmpty(v.anchorId)) return false;
    if (v.investigationId !== undefined && !nonEmpty(v.investigationId)) return false;
    if (v.status !== undefined && !BOOK_STATUS.has(v.status)) return false;
    return true;
  }
  if (v.space === "deliverable") {
    return nonEmpty(v.deliverableId) && v.kind === "block";
  }
  return false;
}

/** A pinned row → contract anchor. Scalar, chunk-relative (the payload's own
 *  unit); the version is the chunk digest; the quote hint rides only when
 *  the pin carried a quote (metadata-only pins have none). */
export function anchorFromPin(
  a: Pick<BookAnchor, "anchor_id" | "document_id" | "anchor" | "page_index_hint" | "status" | "investigation_id">,
): BookDocumentAnchor {
  const p = a.anchor;
  const quote = p.quote ?? "";
  return {
    space: "book",
    documentId: a.document_id,
    version: { kind: "node_text_sha256", nodeId: p.node_id, sha256: p.node_text_sha256 },
    kind: "text",
    range: { kind: "text", nodeId: p.node_id, start: p.start_scalar, end: p.end_scalar, unit: "scalar", basis: "chunk" },
    quoteHint: quote ? { quote, prefix: p.prefix ?? "", suffix: p.suffix ?? "" } : null,
    ...(typeof a.page_index_hint === "number" ? { pageIndex: a.page_index_hint } : {}),
    ...(a.anchor_id ? { anchorId: a.anchor_id } : {}),
    ...(a.investigation_id ? { investigationId: a.investigation_id } : {}),
    ...(a.status ? { status: a.status } : {}),
  };
}

/** The reader's locateSelection tuple (Reading/index.tsx:566-582): UTF-16,
 *  chunk-relative. The version is the chunk digest when the anchor-map
 *  knows it, else an explicit metadata-only absence. */
export function anchorFromLocate(
  documentId: string,
  loc: { chunkId: string; start: number; end: number },
  nodeTextSha256: string | null,
  quote: QuoteHint | null,
  pageIndex: number | null,
): BookDocumentAnchor {
  return {
    space: "book",
    documentId,
    version: nodeTextSha256
      ? { kind: "node_text_sha256", nodeId: loc.chunkId, sha256: nodeTextSha256 }
      : { kind: "unversioned", reason: "metadata_only_anchor" },
    kind: "text",
    range: { kind: "text", nodeId: loc.chunkId, start: loc.start, end: loc.end, unit: "utf16", basis: "chunk" },
    quoteHint: quote && quote.quote ? quote : null,
    ...(pageIndex !== null ? { pageIndex } : {}),
  };
}

async function sha256Utf8(value: string): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(value));
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

/** The writer's block identity (BackendLocator). The version is the prose
 *  digest at capture (artifactFeedbackSelection.ts:33 precedent); with no
 *  prose the absence is typed. Never reads a store. */
export async function anchorFromWriterBlock(i: {
  deliverableId: string;
  sectionId: string;
  outlineBlockId: string | null;
  paragraphIndex: number | null;
  editorBlockId?: string;
  proseText: string | null;
}): Promise<DeliverableDocumentAnchor> {
  return {
    space: "deliverable",
    deliverableId: i.deliverableId,
    version: i.proseText !== null
      ? { kind: "prose_text_sha256", sha256: await sha256Utf8(i.proseText) }
      : { kind: "unversioned", reason: "writer_prose_block_unpersisted" },
    kind: "block",
    range: {
      kind: "block",
      sectionId: i.sectionId,
      outlineBlockId: i.outlineBlockId,
      paragraphIndex: i.paragraphIndex,
      ...(i.editorBlockId ? { editorBlockId: i.editorBlockId } : {}),
    },
    quoteHint: null,
  };
}

/** Wire projection, book space only. source_locator iff range.kind "text"
 *  && basis "document" && unit "scalar" && selectionSha256 is 64 hex (never
 *  true for today's producers). Otherwise document_id + quote/prefix/suffix
 *  (iff quoteHint) + page_index (iff a page is known). region_id never.
 *  Conditional spreads, no nulls. */
export function toBranchAnchor(a: BookDocumentAnchor): BranchAnchor {
  const r = a.range;
  const locator = r.kind === "text" && r.basis === "document" && r.unit === "scalar" &&
    typeof r.selectionSha256 === "string" && SHA256_HEX.test(r.selectionSha256)
    ? { start: r.start, end: r.end, text_sha256: r.selectionSha256 }
    : null;
  const page = r.kind === "page" ? r.pageIndex : a.pageIndex;
  return {
    document_id: a.documentId,
    ...(locator ? { source_locator: locator } : {}),
    ...(a.quoteHint ? { quote: a.quoteHint.quote, prefix: a.quoteHint.prefix, suffix: a.quoteHint.suffix } : {}),
    ...(page !== undefined ? { page_index: page } : {}),
  };
}

/** Dedupe key with unit+basis so UTF-16 and scalar anchors cannot collide.
 *  The text key's fields 3..5 are spawnFlows' (chunkId, start, end) tuple. */
export function anchorKey(a: DocumentAnchor): string {
  const r = a.range;
  if (a.space === "deliverable") {
    const b = r.kind === "block" ? r : null;
    return `deliverable|${a.deliverableId}|block|${b?.sectionId ?? ""}|${b?.outlineBlockId ?? ""}|${b?.paragraphIndex ?? ""}`;
  }
  if (r.kind === "text") return `book|${a.documentId}|text|${r.nodeId}|${r.start}|${r.end}|${r.unit}|${r.basis}`;
  if (r.kind === "page") return `book|${a.documentId}|page|${r.pageIndex}`;
  return `book|${a.documentId}|${r.kind}`;
}
