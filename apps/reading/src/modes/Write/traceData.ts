import type { TraceTarget } from "./writeApi";

function nonEmptyString(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
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

function stringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) => {
    const text = nonEmptyString(item);
    return text ? [text] : [];
  });
}

export function safeTraceTarget(target: TraceTarget): TraceTarget {
  const fullTextAllowed = target.full_text_allowed === true;
  return {
    kind: nonEmptyString(target.kind) ?? "unknown",
    full_text_allowed: fullTextAllowed,
    document_id: fullTextAllowed ? nonEmptyString(target.document_id) : null,
    document_title: fullTextAllowed ? nonEmptyString(target.document_title) : null,
    chunk_ids: fullTextAllowed ? stringArray(target.chunk_ids) : [],
    primary_chunk_index: fullTextAllowed
      ? finiteNonNegativeNumber(target.primary_chunk_index)
      : null,
    primary_section_path: fullTextAllowed ? nonEmptyString(target.primary_section_path) : null,
    servability_status: nonEmptyString(target.servability_status),
    detail: nonEmptyString(target.detail),
  };
}
