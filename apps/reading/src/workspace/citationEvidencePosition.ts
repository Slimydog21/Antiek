const PREFIX = "antiek:citation-evidence-position:v1:";

function validReceipt(value: unknown): value is string {
  return typeof value === "string" && /^[a-f0-9]{64}$/.test(value);
}

export function loadCitationEvidencePosition(
  receiptSha256: unknown,
  anchorCount: number,
  storage?: Pick<Storage, "getItem">,
): number {
  if (!validReceipt(receiptSha256) || !Number.isInteger(anchorCount) || anchorCount < 1 || anchorCount > 64) return 0;
  try {
    const raw = (storage ?? window.sessionStorage).getItem(`${PREFIX}${receiptSha256}`);
    if (!raw) return 0;
    const value = JSON.parse(raw) as Record<string, unknown>;
    if (
      !value || typeof value !== "object" || Array.isArray(value)
      || Object.keys(value).sort().join("|") !== "anchor_count|index|receipt_sha256|version"
      || value.version !== 1 || value.receipt_sha256 !== receiptSha256
      || value.anchor_count !== anchorCount || !Number.isInteger(value.index)
      || (value.index as number) < 0 || (value.index as number) >= anchorCount
    ) return 0;
    return value.index as number;
  } catch {
    return 0;
  }
}

export function storeCitationEvidencePosition(
  receiptSha256: unknown,
  anchorCount: number,
  index: number,
  storage?: Pick<Storage, "setItem">,
): boolean {
  if (
    !validReceipt(receiptSha256) || !Number.isInteger(anchorCount) || anchorCount < 1 || anchorCount > 64
    || !Number.isInteger(index) || index < 0 || index >= anchorCount
  ) return false;
  try {
    (storage ?? window.sessionStorage).setItem(`${PREFIX}${receiptSha256}`, JSON.stringify({
      version: 1, receipt_sha256: receiptSha256, index, anchor_count: anchorCount,
    }));
    return true;
  } catch {
    return false;
  }
}
