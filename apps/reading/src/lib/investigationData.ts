export function requireInvestigationId(value: unknown): string {
  if (typeof value !== "string") {
    throw new TypeError("investigation_id must be a non-empty string");
  }
  const trimmed = value.trim();
  if (!trimmed) {
    throw new TypeError("investigation_id must be a non-empty string");
  }
  return trimmed;
}
