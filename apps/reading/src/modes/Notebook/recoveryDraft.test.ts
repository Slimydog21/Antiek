import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  hasLegacyNotebookDraft,
  readRecoveryDraft,
  recoveryDraftKey,
  writeRecoveryDraft,
} from "./recoveryDraft";

const ACCOUNT = "a".repeat(64);
const RECOVERY = "b".repeat(64);
const HASH = "c".repeat(64);

function installStorage(): Storage {
  const values = new Map<string, string>();
  const storage: Storage = {
    get length() { return values.size; },
    clear: () => values.clear(),
    getItem: (key) => values.get(key) ?? null,
    key: (index) => [...values.keys()][index] ?? null,
    removeItem: (key) => void values.delete(key),
    setItem: (key, value) => void values.set(key, String(value)),
  };
  Object.defineProperty(window, "localStorage", { configurable: true, value: storage });
  return storage;
}

beforeEach(installStorage);

describe("notebook recovery drafts", () => {
  it("round-trips only through an opaque server-derived key", () => {
    const draft = {
      schema_version: 2 as const,
      account_scope: ACCOUNT,
      notebook_id: "nb-1",
      base_revision: 3,
      base_content_sha256: HASH,
      doc: { type: "doc", content: [] },
      saved_at: "2026-07-15T00:00:00Z",
    };
    expect(writeRecoveryDraft(RECOVERY, draft)).toBe(true);
    expect(window.localStorage.key(0)).toBe(recoveryDraftKey(RECOVERY));
    expect(readRecoveryDraft(RECOVERY, ACCOUNT, "nb-1")).toEqual(draft);
  });

  it("rejects account, notebook, schema, hash, and revision mismatches", () => {
    window.localStorage.setItem(recoveryDraftKey(RECOVERY), JSON.stringify({
      schema_version: 2,
      account_scope: ACCOUNT,
      notebook_id: "nb-1",
      base_revision: -1,
      base_content_sha256: HASH,
      doc: { type: "doc" },
      saved_at: "now",
    }));
    expect(readRecoveryDraft(RECOVERY, ACCOUNT, "nb-1")).toBeNull();
    expect(readRecoveryDraft(RECOVERY, "d".repeat(64), "nb-1")).toBeNull();
    expect(readRecoveryDraft(RECOVERY, ACCOUNT, "nb-2")).toBeNull();
    window.localStorage.setItem(recoveryDraftKey(RECOVERY), JSON.stringify({
      schema_version: 2, account_scope: ACCOUNT, notebook_id: "nb-1",
      base_revision: 1, base_content_sha256: HASH,
      doc: { type: "not-a-doc", content: {} }, saved_at: "now",
    }));
    expect(readRecoveryDraft(RECOVERY, ACCOUNT, "nb-1")).toBeNull();
  });

  it("detects a legacy key by enumeration without reading its bytes", () => {
    window.localStorage.setItem("antiek.notebook.nb-legacy", "FOREIGN SECRET");
    const getItem = vi.spyOn(window.localStorage, "getItem");
    expect(hasLegacyNotebookDraft("nb-legacy")).toBe(true);
    expect(getItem).not.toHaveBeenCalled();
  });

  it("rejects attacker-chosen recovery scopes", () => {
    expect(() => recoveryDraftKey("nb-1")).toThrow(/invalid notebook recovery scope/);
  });
});
