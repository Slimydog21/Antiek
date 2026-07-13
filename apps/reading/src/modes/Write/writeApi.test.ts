import { beforeEach, describe, expect, it, vi } from "vitest";

const apiFetch = vi.hoisted(() => vi.fn());

vi.mock("../../lib/api", () => ({
  API_BASE: "",
  ApiError: class ApiError extends Error {
    constructor(
      message: string,
      public status: number,
      public body: string,
    ) {
      super(message);
    }
  },
  apiFetch,
}));

import { moveBlock } from "./writeApi";

const COMMAND_1 = "00000000-0000-4000-8000-000000000001";
const COMMAND_2 = "00000000-0000-4000-8000-000000000002";

function response(status: number): Response {
  return new Response("{}", {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function commandKeys(): string[] {
  return apiFetch.mock.calls.map(([, init]) =>
    (init.headers as Record<string, string>)["Idempotency-Key"]
  );
}

describe("moveBlock convergence", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    apiFetch.mockReset();
    vi.spyOn(crypto, "randomUUID").mockReturnValue(COMMAND_1);
  });

  it("reuses one command after a network rejection", async () => {
    apiFetch.mockRejectedValueOnce(new TypeError("lost response"));
    apiFetch.mockResolvedValueOnce(response(202));

    await moveBlock("block-1", "section-1", 2);

    expect(apiFetch).toHaveBeenCalledTimes(2);
    expect(commandKeys()).toEqual([COMMAND_1, COMMAND_1]);
  });

  it("reuses one command after a server failure", async () => {
    apiFetch.mockResolvedValueOnce(response(500));
    apiFetch.mockResolvedValueOnce(response(202));

    await moveBlock("block-2", "section-1", 3);

    expect(apiFetch).toHaveBeenCalledTimes(2);
    expect(commandKeys()).toEqual([COMMAND_1, COMMAND_1]);
  });

  it("keeps the command for a later manual retry", async () => {
    apiFetch.mockRejectedValueOnce(new TypeError("offline"));
    apiFetch.mockRejectedValueOnce(new TypeError("still offline"));
    await expect(moveBlock("block-3", "section-1", 4)).rejects.toThrow("still offline");

    apiFetch.mockResolvedValueOnce(response(202));
    await moveBlock("block-3", "section-1", 4);

    expect(commandKeys()).toEqual([COMMAND_1, COMMAND_1, COMMAND_1]);
  });

  it("does not retry a terminal client error", async () => {
    vi.mocked(crypto.randomUUID)
      .mockReturnValueOnce(COMMAND_1)
      .mockReturnValueOnce(COMMAND_2);
    apiFetch.mockResolvedValueOnce(response(409));

    await expect(moveBlock("block-4", "section-1", 5)).rejects.toThrow("HTTP 409");
    apiFetch.mockResolvedValueOnce(response(202));
    await moveBlock("block-4", "section-1", 5);

    expect(apiFetch).toHaveBeenCalledTimes(2);
    expect(commandKeys()).toEqual([COMMAND_1, COMMAND_2]);
  });
});
