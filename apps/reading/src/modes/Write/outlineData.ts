import type { GenerationResult, OutlineBlockView } from "./writeApi";

const GENERATION_STATUSES = new Set<GenerationResult["status"]>([
  "generated",
  "gap",
  "gate_failed",
  "invalid",
]);

function nonEmptyString(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

function nullableString(value: unknown): string | null {
  return value == null ? null : nonEmptyString(value);
}

function finiteNonNegativeNumber(value: unknown): number | null {
  const parsed =
    typeof value === "number"
      ? value
      : typeof value === "string" && value.trim() !== ""
        ? Number(value)
        : Number.NaN;
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : null;
}

function nonNegativeSafeInteger(value: unknown): number | null {
  const parsed = finiteNonNegativeNumber(value);
  return parsed !== null && Number.isSafeInteger(parsed) ? parsed : null;
}

function safeStringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) => {
    const text = nonEmptyString(item);
    return text ? [text] : [];
  });
}

function safeNumberArray(value: unknown): number[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) => {
    const number = nonNegativeSafeInteger(item);
    return number === null ? [] : [number];
  });
}

export function safeProseProvenance(value: unknown): Record<string, string[]> {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  return Object.fromEntries(
    Object.entries(value).flatMap(([key, rawIds]) => {
      const paragraph = nonEmptyString(key);
      const ids = safeStringArray(rawIds);
      return paragraph && ids.length ? [[paragraph, ids]] : [];
    }),
  );
}

export function safeOutlineBlocks(blocks: OutlineBlockView[]): OutlineBlockView[] {
  return blocks.flatMap((block) => {
    const outlineBlockId = nonEmptyString(block.outline_block_id);
    const sectionId = nonEmptyString(block.section_id);
    if (!outlineBlockId || !sectionId) return [];
    return [
      {
        ...block,
        outline_block_id: outlineBlockId,
        section_id: sectionId,
        block_kind: nonEmptyString(block.block_kind) ?? "insight",
        provenance_kind: nonEmptyString(block.provenance_kind) ?? "graph_node",
        node_id: nullableString(block.node_id),
        content: nullableString(block.content),
        node_label: nullableString(block.node_label),
        block_index: finiteNonNegativeNumber(block.block_index) ?? 0,
        is_user_originated: block.is_user_originated === true,
      },
    ];
  });
}

export function safeGenerationResult(
  result: GenerationResult,
  sectionId: string,
): GenerationResult {
  const status =
    typeof result.status === "string" &&
    GENERATION_STATUSES.has(result.status as GenerationResult["status"])
      ? (result.status as GenerationResult["status"])
      : "invalid";
  return {
    ...result,
    status,
    section_id: nonEmptyString(result.section_id) ?? sectionId,
    prose_text: nonEmptyString(result.prose_text) ?? undefined,
    detail: nonEmptyString(result.detail) ?? undefined,
    gate_passed: typeof result.gate_passed === "boolean" ? result.gate_passed : null,
    all_claims_cited:
      typeof result.all_claims_cited === "boolean" ? result.all_claims_cited : null,
    unsupported_paragraphs: safeNumberArray(result.unsupported_paragraphs),
    fabricated_citations: safeStringArray(result.fabricated_citations),
    prose_provenance: safeProseProvenance(result.prose_provenance),
  };
}
