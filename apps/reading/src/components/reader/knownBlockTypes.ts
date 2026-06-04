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
 * instead of throwing. (The render-time error boundary is the second line of
 * defense for field-level skew within a known type.)
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

/** True iff every block is a non-null object with a known `type` discriminator.
 *  An empty array is valid (an empty-but-well-formed doc). */
export function allBlockTypesKnown(blocks: unknown[]): boolean {
  return blocks.every(
    (b): b is { type: string } =>
      typeof b === "object" &&
      b !== null &&
      typeof (b as { type?: unknown }).type === "string" &&
      KNOWN_BLOCK_TYPES.has((b as { type: string }).type),
  );
}
