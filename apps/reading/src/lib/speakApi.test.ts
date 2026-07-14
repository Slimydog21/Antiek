import { beforeEach, describe, expect, it, vi } from "vitest";

const apiFetch = vi.hoisted(() => vi.fn());

vi.mock("./api", () => ({ apiFetch }));

import { assembleDraft } from "./speakApi";

const COMMAND_1 = "00000000-0000-4000-8000-000000000001";
const COMMAND_2 = "00000000-0000-4000-8000-000000000002";
const stored = new Map<string, string>();

vi.stubGlobal("localStorage", {
  getItem: (key: string) => stored.get(key) ?? null,
  setItem: (key: string, value: string) => stored.set(key, value),
  removeItem: (key: string) => stored.delete(key),
  clear: () => stored.clear(),
});

function response(status = 200): Response {
  return new Response(JSON.stringify({ prose_text: "Draft", excluded_claim_ids: [] }), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("Speak draft command identity", () => {
  beforeEach(() => {
    apiFetch.mockReset();
    stored.clear();
    vi.restoreAllMocks();
    vi.spyOn(crypto, "randomUUID").mockReturnValue(COMMAND_1);
  });

  it("retains one command after a lost response and clears it on success", async () => {
    apiFetch.mockRejectedValueOnce(new TypeError("response lost"));
    await expect(assembleDraft("project-1", false)).rejects.toThrow("response lost");
    apiFetch.mockResolvedValueOnce(response());
    await expect(assembleDraft("project-1", false)).resolves.toEqual({
      prose: "Draft",
      excludedCount: 0,
    });
    const keys = apiFetch.mock.calls.map(
      ([, init]) => (init.headers as Record<string, string>)["Idempotency-Key"],
    );
    expect(keys).toEqual([COMMAND_1, COMMAND_1]);
    expect(stored.size).toBe(0);
  });

  it("recovers a pending command across a browser reload", async () => {
    stored.set('antiek:speak-draft:["project-2",true]', COMMAND_2);
    apiFetch.mockResolvedValueOnce(response());
    await assembleDraft("project-2", true);
    const init = apiFetch.mock.calls[0][1];
    expect((init.headers as Record<string, string>)["Idempotency-Key"]).toBe(COMMAND_2);
  });

  it("abandons a command rejected before acceptance", async () => {
    vi.mocked(crypto.randomUUID)
      .mockReturnValueOnce(COMMAND_1)
      .mockReturnValueOnce(COMMAND_2);
    apiFetch.mockResolvedValueOnce(response(409));
    await expect(assembleDraft("project-3", false)).rejects.toThrow("HTTP 409");
    apiFetch.mockResolvedValueOnce(response());
    await assembleDraft("project-3", false);
    const keys = apiFetch.mock.calls.map(
      ([, init]) => (init.headers as Record<string, string>)["Idempotency-Key"],
    );
    expect(keys).toEqual([COMMAND_1, COMMAND_2]);
  });

  it("coalesces simultaneous assembly requests into one command", async () => {
    let resolve!: (value: Response) => void;
    apiFetch.mockReturnValueOnce(
      new Promise<Response>((done) => {
        resolve = done;
      }),
    );
    const first = assembleDraft("project-4", false);
    const second = assembleDraft("project-4", false);
    expect(apiFetch).toHaveBeenCalledTimes(1);
    resolve(response());
    await expect(Promise.all([first, second])).resolves.toEqual([
      { prose: "Draft", excludedCount: 0 },
      { prose: "Draft", excludedCount: 0 },
    ]);
  });
});
