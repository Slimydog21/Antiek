import { beforeEach, describe, expect, it, vi } from "vitest";

const { apiFetch } = vi.hoisted(() => ({ apiFetch: vi.fn() }));
vi.mock("../lib/api", () => ({
  API_BASE: "/api",
  apiFetch,
  ApiError: class ApiError extends Error {
    constructor(message: string, public status: number, public body: string) {
      super(message);
    }
  },
}));

import { fetchTwinNotes, mergeSpawnOutputs, openEngagementSession, recordTwinNote } from "./engagement";

describe("trimmed engagement client", () => {
  beforeEach(() => apiFetch.mockReset());

  it.each([
    ["session", () => openEngagementSession({ asset_id: "book", selection_text: "passage" }), "/engagement/sessions/open", "POST"],
    ["twins", () => fetchTwinNotes("book"), "/engagement/twins/book", undefined],
    ["note", () => recordTwinNote({ asset_id: "book", kind: "insight", text: "note" }), "/engagement/twins", "POST"],
    ["merge", () => mergeSpawnOutputs({ parent_asset_id: "book", spawn_ids: ["spn"] }), "/engagement/merge", "POST"],
  ])("calls only the allowed %s endpoint", async (_name, call, path, method) => {
    apiFetch.mockResolvedValue(new Response("{}", { status: 200 }));
    await call();
    const [url, init] = apiFetch.mock.calls[0];
    expect(url).toContain(path);
    expect(init?.method).toBe(method);
  });

  it("keeps server errors visible to callers", async () => {
    apiFetch.mockResolvedValue(new Response("merge blocked", { status: 400 }));
    await expect(mergeSpawnOutputs({ parent_asset_id: "book", spawn_ids: ["spn"] }))
      .rejects.toThrow(/merge blocked/);
  });
});
