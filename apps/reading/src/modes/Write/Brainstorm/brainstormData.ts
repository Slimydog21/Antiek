import type { BrainstormEmitResult } from "../writeApi";

function nonEmptyString(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

function finiteNonNegativeNumber(value: unknown): number {
  const parsed =
    typeof value === "number"
      ? value
      : typeof value === "string" && value.trim() !== ""
        ? Number(value)
        : Number.NaN;
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : 0;
}

function stringArray(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) => {
    const text = nonEmptyString(item);
    return text ? [text] : [];
  });
}

function uniqueStringArray(value: unknown): string[] {
  return Array.from(new Set(stringArray(value)));
}

export function safeBrainstormEmitResult(result: BrainstormEmitResult): BrainstormEmitResult {
  return {
    block_ids: uniqueStringArray(result.block_ids),
    insight_count: finiteNonNegativeNumber(result.insight_count),
    question_count: finiteNonNegativeNumber(result.question_count),
    data_count: finiteNonNegativeNumber(result.data_count),
    skipped_duplicates: finiteNonNegativeNumber(result.skipped_duplicates),
    flagged_unverified: uniqueStringArray(result.flagged_unverified),
  };
}
