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

import { moveBlock, traceReaderPath, type TraceTarget } from "./writeApi";

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

describe("traceReaderPath", () => {
  const target: TraceTarget = {
    kind: "source_span",
    full_text_allowed: true,
    document_id: "doc/one",
    document_title: "Source",
    chunk_ids: ["chunk primary", "chunk-secondary"],
    servability_status: "public_domain",
    detail: null,
  };

  it("carries only the primary chunk and a closed Write return id", () => {
    expect(traceReaderPath(target, "dlv/one")).toBe(
      "/read/doc%2Fone?chunk=chunk+primary&return_write=dlv%2Fone",
    );
  });

  it("opens the document root when no chunk or return id exists", () => {
    expect(traceReaderPath({ ...target, chunk_ids: [] })).toBe("/read/doc%2Fone");
  });

  it("refuses a non-servable target", () => {
    expect(traceReaderPath({ ...target, full_text_allowed: false }, "dlv-1")).toBeNull();
  });
});
