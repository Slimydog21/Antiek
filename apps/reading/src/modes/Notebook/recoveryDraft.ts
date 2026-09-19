import type { JSONContent } from "@tiptap/core";

export const LEGACY_NOTEBOOK_PREFIX = "antiek.notebook.";
const DRAFT_PREFIX = "antiek.notebook-draft.v2.";

export type NotebookRecoveryDraft = {
  schema_version: 2;
  account_scope: string;
  notebook_id: string;
  base_revision: number;
  base_content_sha256: string;
  doc: JSONContent;
  saved_at: string;
};

function isHex64(value: unknown): value is string {
  return typeof value === "string" && /^[0-9a-f]{64}$/.test(value);
}

function isDraft(value: unknown): value is NotebookRecoveryDraft {
  if (typeof value !== "object" || value === null) return false;
  const row = value as Record<string, unknown>;
  return (
    row.schema_version === 2 &&
    isHex64(row.account_scope) &&
    typeof row.notebook_id === "string" &&
    row.notebook_id.length > 0 &&
    Number.isInteger(row.base_revision) &&
    (row.base_revision as number) >= 0 &&
    isHex64(row.base_content_sha256) &&
    isTipTapDoc(row.doc) &&
    typeof row.saved_at === "string"
  );
}

function isTipTapDoc(value: unknown): value is JSONContent {
  if (typeof value !== "object" || value === null) return false;
  const doc = value as Record<string, unknown>;
  return (
    doc.type === "doc" &&
    Array.isArray(doc.content) &&
    doc.content.every((node) => typeof node === "object" && node !== null)
  );
}

export function recoveryDraftKey(recoveryScope: string): string {
  if (!isHex64(recoveryScope)) throw new Error("invalid notebook recovery scope");
  return DRAFT_PREFIX + recoveryScope;
}

export function readRecoveryDraft(
  recoveryScope: string,
  accountScope: string,
  notebookId: string,
): NotebookRecoveryDraft | null {
  try {
    const raw = window.localStorage.getItem(recoveryDraftKey(recoveryScope));
    if (raw === null) return null;
    const parsed: unknown = JSON.parse(raw);
    if (
      !isDraft(parsed) ||
      parsed.account_scope !== accountScope ||
      parsed.notebook_id !== notebookId
    ) {
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}

export function writeRecoveryDraft(
  recoveryScope: string,
  draft: NotebookRecoveryDraft,
): boolean {
  try {
    window.localStorage.setItem(recoveryDraftKey(recoveryScope), JSON.stringify(draft));
    return true;
  } catch {
    return false;
  }
}

export function removeRecoveryDraft(recoveryScope: string): void {
  try {
    window.localStorage.removeItem(recoveryDraftKey(recoveryScope));
  } catch {
    // Recovery cleanup is best effort; never convert a server save into failure.
  }
}

export function hasLegacyNotebookDraft(notebookId: string): boolean {
  const wanted = LEGACY_NOTEBOOK_PREFIX + notebookId;
  try {
    for (let index = 0; index < window.localStorage.length; index += 1) {
      if (window.localStorage.key(index) === wanted) return true;
    }
  } catch {
    return false;
  }
  return false;
}
