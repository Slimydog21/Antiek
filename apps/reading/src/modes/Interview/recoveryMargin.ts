export const LEGACY_INTERVIEW_NOTE_PREFIX = "antiek.interview-notes.";
const RECOVERY_PREFIX = "antiek.interview-margin-recovery.v1.";

export type InterviewMarginRecovery = {
  schema_version: 1;
  account_scope: string;
  interview_id: string;
  base_revision: number;
  base_content_sha256: string;
  body: string;
  saved_at: string;
};

const hex64 = (value: unknown): value is string =>
  typeof value === "string" && /^[0-9a-f]{64}$/.test(value);

export function recoveryMarginKey(scope: string): string {
  if (!hex64(scope)) throw new Error("invalid interview recovery scope");
  return RECOVERY_PREFIX + scope;
}

export function readRecoveryMargin(
  scope: string,
  accountScope: string,
  interviewId: string,
): InterviewMarginRecovery | null {
  try {
    const raw = window.localStorage.getItem(recoveryMarginKey(scope));
    if (raw === null) return null;
    const value: unknown = JSON.parse(raw);
    if (typeof value !== "object" || value === null) return null;
    const row = value as Record<string, unknown>;
    if (
      row.schema_version !== 1 || row.account_scope !== accountScope ||
      row.interview_id !== interviewId || !Number.isInteger(row.base_revision) ||
      (row.base_revision as number) < 0 || !hex64(row.base_content_sha256) ||
      typeof row.body !== "string" || typeof row.saved_at !== "string"
    ) return null;
    return value as InterviewMarginRecovery;
  } catch {
    return null;
  }
}

export function writeRecoveryMargin(scope: string, value: InterviewMarginRecovery): boolean {
  try {
    window.localStorage.setItem(recoveryMarginKey(scope), JSON.stringify(value));
    return true;
  } catch {
    return false;
  }
}

export function removeRecoveryMargin(scope: string): void {
  try { window.localStorage.removeItem(recoveryMarginKey(scope)); } catch { /* best effort */ }
}

export function hasLegacyInterviewNote(interviewId: string): boolean {
  const wanted = LEGACY_INTERVIEW_NOTE_PREFIX + interviewId;
  try {
    for (let i = 0; i < window.localStorage.length; i += 1) {
      if (window.localStorage.key(i) === wanted) return true;
    }
  } catch { return false; }
  return false;
}
