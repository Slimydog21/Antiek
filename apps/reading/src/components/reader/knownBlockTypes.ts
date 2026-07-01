import type { Block } from "../../types/document_model.gen";

/**
 * The known block `type` discriminators (Reader SPR-03, D1 defense-in-depth).
 *
 * The single source of truth is the `Block` discriminated union in the
 * generated `document_model.gen` (itself emitted from the Pydantic models). This
 * set MUST stay in lockstep with that union: the `satisfies Record<Block["type"],
 * true>` below makes the compiler fail the build if a NEW block type is added to
 * the model without being listed here (and a typo'd / removed key fails too). So
 * a schema change can't silently leave this validator stale.
 *
 * Used by the `structuredDoc` gate to reject a doc carrying a block whose `type`
 * is NOT renderable (a schema-skew / poisoned blob) BEFORE it reaches the
 * dispatcher's `assertNever`, so such a doc takes the clean legacy fallback
 * instead of throwing. The renderability guard below extends that same
 * pre-render defense to required fields that would otherwise throw inside
 * InlineSpans/renderMath.
 */
const KNOWN_BLOCK_TYPE_MAP = {
  heading: true,
  paragraph: true,
  list: true,
  table: true,
  code: true,
  math: true,
  figure: true,
  blockquote: true,
  footnote: true,
} satisfies Record<Block["type"], true>;

export const KNOWN_BLOCK_TYPES: ReadonlySet<string> = new Set(
  Object.keys(KNOWN_BLOCK_TYPE_MAP),
);

function record(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null ? (value as Record<string, unknown>) : null;
}

function nullableString(value: unknown): boolean {
  return value === undefined || value === null || typeof value === "string";
}

function inlineSpansRenderable(spans: unknown): boolean {
  return Array.isArray(spans) && spans.every(inlineSpanRenderable);
}

function inlineSpanRenderable(span: unknown): boolean {
  const s = record(span);
  if (!s || typeof s.type !== "string") return false;
  switch (s.type) {
    case "text":
    case "code":
      return typeof s.text === "string";
    case "math":
      return typeof s.tex === "string";
    case "citation":
      return (
        typeof s.source_document_id === "string" &&
        typeof s.chunk_id === "string" &&
        typeof s.marker === "string"
      );
    case "strong":
    case "emphasis":
      return inlineSpansRenderable(s.children);
    case "link":
      return typeof s.href === "string" && inlineSpansRenderable(s.children);
    default:
      return false;
  }
}

function tableCellsRenderable(cells: unknown): boolean {
  return Array.isArray(cells) && cells.every(inlineSpansRenderable);
}

function blockRenderable(block: unknown): boolean {
  const b = record(block);
  if (!b || typeof b.type !== "string" || !KNOWN_BLOCK_TYPES.has(b.type)) return false;
  switch (b.type) {
    case "heading":
      return typeof b.level === "number" && inlineSpansRenderable(b.spans);
    case "paragraph":
      return inlineSpansRenderable(b.spans);
    case "list":
      return (
        Array.isArray(b.items) &&
        b.items.every((item) => {
          const i = record(item);
          return i ? i.type === "list_item" && blocksRenderable(i.blocks) : false;
        })
      );
    case "table":
      return (
        (b.header === undefined || tableCellsRenderable(b.header)) &&
        (b.rows === undefined ||
          (Array.isArray(b.rows) && b.rows.every((row) => tableCellsRenderable(row))))
      );
    case "code":
      return typeof b.text === "string" && nullableString(b.lang);
    case "math":
      return typeof b.tex === "string";
    case "figure":
      return (
        nullableString(b.src) &&
        nullableString(b.alt) &&
        (b.caption === undefined || inlineSpansRenderable(b.caption))
      );
    case "blockquote":
      return blocksRenderable(b.blocks);
    case "footnote":
      return typeof b.id === "string" && blocksRenderable(b.blocks);
    default:
      return false;
  }
}

/** True iff every block has the fields the Reader dereferences during render.
 *  This is not a full schema clone; it is the narrow pre-render crash gate. */
export function blocksRenderable(blocks: unknown): boolean {
  return Array.isArray(blocks) && blocks.every(blockRenderable);
}
