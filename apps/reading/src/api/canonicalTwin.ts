import { API_BASE, ApiError, apiFetch } from "../lib/api";

export interface CanonicalTwinView {
  document_id: string;
  source_asset_id: string;
  source_hash: string;
  title: string;
  html_fragment: string;
  authority: "advisory";
  authority_label: string;
  shareable: false;
  reviewed_promotions_href: string;
}

export interface ReviewedPromotionSummary {
  candidate_id: string;
  node_id: string;
  review_id: string;
  kind: "insight" | "question";
  text: string;
  evidence_count: number;
  href: string;
}

export interface ReviewedPromotionCollection {
  source_asset_id: string;
  source_hash: string;
  items: ReviewedPromotionSummary[];
  complete: true;
  authority: "current_owner_reviewed_source_promotions_v1";
}

export interface PromotionCitation {
  citation_id: string;
  node_id: string;
  owner_id: string;
  candidate_id: string;
  candidate_digest: string;
  review_id: string;
  ordinal: number;
  citation_kind: "canonical_twin" | "evidence";
  document_id: string;
  chunk_id: string;
  range_start: number | null;
  range_end: number | null;
  text_sha256: string;
  chunk_sha256: string;
  document_sha256: string | null;
  source_envelope_sha256: string | null;
  content_class: string | null;
  schema: "antiek.canonical-twin-node-citation.v1";
}

export interface CurrentPromotionDetail {
  node: {
    candidate_id: string;
    node_id: string;
    review_id: string;
    kind: "insight" | "question";
    text: string;
    owner_id: string;
    status: "current";
    authority: "owner_reviewed_evidence_bound_graph_node_v1";
  };
  citations: PromotionCitation[];
  status: "current";
  authority: "owner_reviewed_evidence_bound_node_citations_v1";
}

type Decoder<T> = (value: unknown) => T;

function record(value: unknown, keys: readonly string[], label: string): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new Error(`${label}_invalid`);
  }
  const result = value as Record<string, unknown>;
  if (Object.keys(result).sort().join("\0") !== [...keys].sort().join("\0")) {
    throw new Error(`${label}_fields_invalid`);
  }
  return result;
}

function text(value: unknown, label: string, maximum = 4096): string {
  if (
    typeof value !== "string" ||
    value.length === 0 ||
    new TextEncoder().encode(value).length > maximum ||
    [...value].some((character) =>
      (character.charCodeAt(0) < 32 && !"\n\t\r".includes(character)) ||
      character.charCodeAt(0) === 127,
    )
  ) {
    throw new Error(`${label}_invalid`);
  }
  return value;
}

function nullableText(value: unknown, label: string): string | null {
  return value === null ? null : text(value, label, 512);
}

function digest(value: unknown, label: string): string {
  const result = text(value, label, 64);
  if (!/^[0-9a-f]{64}$/.test(result)) throw new Error(`${label}_invalid`);
  return result;
}

function nullableDigest(value: unknown, label: string): string | null {
  return value === null ? null : digest(value, label);
}

function integer(value: unknown, label: string, maximum = 1_000_000): number {
  if (!Number.isSafeInteger(value) || (value as number) < 0 || (value as number) > maximum) {
    throw new Error(`${label}_invalid`);
  }
  return value as number;
}

function literal<T extends string | boolean>(value: unknown, expected: T, label: string): T {
  if (value !== expected) throw new Error(`${label}_invalid`);
  return expected;
}

function decodeTwin(value: unknown): CanonicalTwinView {
  const item = record(
    value,
    ["document_id", "source_asset_id", "source_hash", "title", "html_fragment", "authority", "authority_label", "shareable", "reviewed_promotions_href"],
    "canonical_twin",
  );
  const result: CanonicalTwinView = {
    document_id: text(item.document_id, "document_id", 512),
    source_asset_id: text(item.source_asset_id, "source_asset_id", 512),
    source_hash: text(item.source_hash, "source_hash", 512),
    title: text(item.title, "title", 4096),
    html_fragment: text(item.html_fragment, "html_fragment", 2_000_000),
    authority: literal(item.authority, "advisory", "twin_authority"),
    authority_label: text(item.authority_label, "authority_label", 512),
    shareable: literal(item.shareable, false, "shareable"),
    reviewed_promotions_href: text(item.reviewed_promotions_href, "promotions_href", 2048),
  };
  return result;
}

function decodeSummary(value: unknown): ReviewedPromotionSummary {
  const item = record(value, ["candidate_id", "node_id", "review_id", "kind", "text", "evidence_count", "href"], "promotion_summary");
  const kind = item.kind;
  if (kind !== "insight" && kind !== "question") throw new Error("promotion_kind_invalid");
  const result: ReviewedPromotionSummary = {
    candidate_id: text(item.candidate_id, "candidate_id", 512),
    node_id: text(item.node_id, "node_id", 512),
    review_id: text(item.review_id, "review_id", 512),
    kind,
    text: text(item.text, "promotion_text", 8_000),
    evidence_count: integer(item.evidence_count, "evidence_count", 16),
    href: text(item.href, "promotion_href", 2048),
  };
  if (result.evidence_count < 1) throw new Error("evidence_count_invalid");
  return result;
}

function decodeCollection(value: unknown): ReviewedPromotionCollection {
  const item = record(value, ["source_asset_id", "source_hash", "items", "complete", "authority"], "promotion_collection");
  if (!Array.isArray(item.items) || item.items.length > 32) throw new Error("promotion_items_invalid");
  const items = item.items.map(decodeSummary);
  if (new Set(items.map((entry) => entry.candidate_id)).size !== items.length) {
    throw new Error("promotion_items_duplicate");
  }
  return {
    source_asset_id: text(item.source_asset_id, "source_asset_id", 512),
    source_hash: text(item.source_hash, "source_hash", 512),
    items,
    complete: literal(item.complete, true, "collection_complete"),
    authority: literal(item.authority, "current_owner_reviewed_source_promotions_v1", "collection_authority"),
  };
}

function decodeCitation(value: unknown): PromotionCitation {
  const item = record(value, ["citation_id", "node_id", "owner_id", "candidate_id", "candidate_digest", "review_id", "ordinal", "citation_kind", "document_id", "chunk_id", "range_start", "range_end", "text_sha256", "chunk_sha256", "document_sha256", "source_envelope_sha256", "content_class", "schema"], "promotion_citation");
  const citationKind = item.citation_kind;
  if (citationKind !== "canonical_twin" && citationKind !== "evidence") throw new Error("citation_kind_invalid");
  const rangeStart = item.range_start === null ? null : integer(item.range_start, "range_start", 2_000_000_000);
  const rangeEnd = item.range_end === null ? null : integer(item.range_end, "range_end", 2_000_000_000);
  if ((rangeStart === null) !== (rangeEnd === null) || (rangeStart !== null && rangeEnd! <= rangeStart)) throw new Error("citation_range_invalid");
  const result: PromotionCitation = {
    citation_id: text(item.citation_id, "citation_id", 512),
    node_id: text(item.node_id, "node_id", 512),
    owner_id: text(item.owner_id, "owner_id", 512),
    candidate_id: text(item.candidate_id, "candidate_id", 512),
    candidate_digest: digest(item.candidate_digest, "candidate_digest"),
    review_id: text(item.review_id, "review_id", 512),
    ordinal: integer(item.ordinal, "ordinal", 16),
    citation_kind: citationKind,
    document_id: text(item.document_id, "document_id", 512),
    chunk_id: text(item.chunk_id, "chunk_id", 512),
    range_start: rangeStart,
    range_end: rangeEnd,
    text_sha256: digest(item.text_sha256, "text_sha256"),
    chunk_sha256: digest(item.chunk_sha256, "chunk_sha256"),
    document_sha256: nullableDigest(item.document_sha256, "document_sha256"),
    source_envelope_sha256: nullableDigest(item.source_envelope_sha256, "source_envelope_sha256"),
    content_class: nullableText(item.content_class, "content_class"),
    schema: literal(item.schema, "antiek.canonical-twin-node-citation.v1", "citation_schema"),
  };
  if (
    (result.citation_kind === "canonical_twin" && (
      result.ordinal !== 0 ||
      result.range_start !== null ||
      result.range_end !== null ||
      result.document_sha256 !== null ||
      result.source_envelope_sha256 !== null ||
      result.content_class !== null ||
      result.text_sha256 !== result.chunk_sha256
    )) ||
    (result.citation_kind === "evidence" && (
      result.ordinal === 0 ||
      result.range_start === null ||
      result.range_end === null ||
      result.document_sha256 === null ||
      result.source_envelope_sha256 === null ||
      result.content_class === null
    ))
  ) {
    throw new Error("citation_binding_invalid");
  }
  return result;
}

function decodeDetail(value: unknown): CurrentPromotionDetail {
  const item = record(value, ["node", "citations", "status", "authority"], "promotion_detail");
  const node = record(item.node, ["node_id", "candidate_id", "review_id", "kind", "text", "owner_id", "status", "authority"], "promotion_node");
  const kind = node.kind;
  if (kind !== "insight" && kind !== "question") throw new Error("node_kind_invalid");
  if (!Array.isArray(item.citations) || item.citations.length < 2 || item.citations.length > 17) throw new Error("citations_invalid");
  return {
    node: {
      node_id: text(node.node_id, "node_id", 512),
      candidate_id: text(node.candidate_id, "candidate_id", 512),
      review_id: text(node.review_id, "review_id", 512),
      kind,
      text: text(node.text, "node_text", 8_000),
      owner_id: text(node.owner_id, "owner_id", 512),
      status: literal(node.status, "current", "node_status"),
      authority: literal(node.authority, "owner_reviewed_evidence_bound_graph_node_v1", "node_authority"),
    },
    citations: item.citations.map(decodeCitation),
    status: literal(item.status, "current", "detail_status"),
    authority: literal(item.authority, "owner_reviewed_evidence_bound_node_citations_v1", "detail_authority"),
  };
}

async function checkedJson<T>(response: Response, operation: string, decode: Decoder<T>): Promise<T> {
  if (!response.ok) {
    throw new ApiError(operation, response.status, await response.text());
  }
  return decode(await response.json());
}

function exactPrivateHref(href: string, pattern: RegExp): string {
  if (!pattern.test(href)) throw new Error("private_reader_link_invalid");
  return `${API_BASE}${href}`;
}

export async function getCanonicalTwin(
  sourceAssetId: string,
  sourceHash: string,
  signal?: AbortSignal,
): Promise<CanonicalTwinView> {
  const path = `/reader/sources/${encodeURIComponent(sourceAssetId)}/canonical-twin`;
  const query = new URLSearchParams({ source_hash: sourceHash });
  return checkedJson(
    await apiFetch(`${API_BASE}${path}?${query.toString()}`, { signal }),
    "GET canonical twin failed",
    decodeTwin,
  );
}

export async function getReviewedPromotions(
  href: string,
  signal?: AbortSignal,
): Promise<ReviewedPromotionCollection> {
  const target = exactPrivateHref(
    href,
    /^\/reader\/sources\/[^/?#]+\/reviewed-promotions\?source_hash=[^&#]+$/,
  );
  return checkedJson(
    await apiFetch(target, { signal }),
    "GET reviewed promotions failed",
    decodeCollection,
  );
}

export async function getCurrentPromotion(
  href: string,
  signal?: AbortSignal,
): Promise<CurrentPromotionDetail> {
  const target = exactPrivateHref(href, /^\/reader\/promotions\/[^/?#]+$/);
  return checkedJson(
    await apiFetch(target, { signal }),
    "GET current promotion failed",
    decodeDetail,
  );
}

const SAFE_HTML_TAGS = new Set(["p", "br", "hr", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "pre", "code", "ul", "ol", "li", "dl", "dt", "dd", "em", "strong", "i", "b", "u", "s", "sub", "sup", "small", "mark", "a", "figure", "figcaption", "table", "caption", "thead", "tbody", "tfoot", "tr", "th", "td", "section", "article", "div", "span"]);
const GLOBAL_HTML_ATTRS = new Set(["id", "title", "lang", "dir"]);

export function trustedCanonicalHtml(value: string): string {
  const template = document.createElement("template");
  template.innerHTML = value;
  for (const element of template.content.querySelectorAll("*")) {
    const tag = element.tagName.toLowerCase();
    if (!SAFE_HTML_TAGS.has(tag)) throw new Error("canonical_html_tag_invalid");
    for (const attribute of [...element.attributes]) {
      const allowed = GLOBAL_HTML_ATTRS.has(attribute.name) ||
        (tag === "a" && attribute.name === "href") ||
        (tag === "ol" && attribute.name === "start") ||
        ((tag === "th" || tag === "td") && ["colspan", "rowspan", "scope"].includes(attribute.name));
      if (!allowed || attribute.name.startsWith("on") || attribute.name === "style") throw new Error("canonical_html_attribute_invalid");
      if (attribute.name === "href") {
        const href = attribute.value;
        if (
          !(href.startsWith("#") || href.startsWith("/")) ||
          href.startsWith("//") ||
          href.includes("\\") ||
          /[\u0000-\u001f\u007f]/.test(href)
        ) throw new Error("canonical_html_link_invalid");
      }
    }
  }
  return value;
}
