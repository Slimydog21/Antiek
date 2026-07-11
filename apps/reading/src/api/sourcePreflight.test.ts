import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../lib/api", () => ({
  API_BASE: "",
  apiFetch: vi.fn(),
}));

import { apiFetch } from "../lib/api";
import {
  formatProbeHonesty,
  parseSourcePolicyPreflight,
  postSourcePreflight,
  SourcePreflightHttpError,
} from "./sourcePreflight";

const mockFetch = apiFetch as unknown as ReturnType<typeof vi.fn>;

beforeEach(() => {
  mockFetch.mockReset();
});
afterEach(() => {
  vi.restoreAllMocks();
});

const entry = {
  source: "arxiv",
  status: "ready",
  runner_consumes_today: false,
  external_call_would_be_required: true,
  note: "import ok",
  adapter_importable: true,
  offline_probe_ok: true,
};

describe("parse honesty", () => {
  it("requires strict booleans — no invent true", () => {
    expect(() =>
      parseSourcePolicyPreflight({
        source_receipt_id: "r1",
        source_policy: ["arxiv"],
        gather_mode: "parallel",
        entries: [{ ...entry, offline_probe_ok: "yes" }],
        notes: [],
      }),
    ).toThrow(/offline_probe_ok must be boolean/);
    expect(() =>
      parseSourcePolicyPreflight({
        source_receipt_id: "r1",
        source_policy: ["arxiv"],
        gather_mode: "parallel",
        entries: [{ ...entry, runner_consumes_today: 1 }],
        notes: [],
      }),
    ).toThrow(/runner_consumes_today must be boolean/);
  });

  it("formatProbeHonesty reflects false consumption", () => {
    expect(formatProbeHonesty(entry as never)).toMatch(/does not claim consumption/i);
    expect(
      formatProbeHonesty({ ...entry, runner_consumes_today: true } as never),
    ).toMatch(/runner consumes today/i);
  });
});

describe("postSourcePreflight", () => {
  it("POSTs and parses body", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        source_receipt_id: "rcpt-1",
        source_policy: ["arxiv", "substack"],
        gather_mode: "parallel",
        entries: [entry, { ...entry, source: "substack", offline_probe_ok: false }],
        notes: [],
      }),
      text: async () => "",
    } as unknown as Response);

    const body = await postSourcePreflight({
      source_policy: ["arxiv", "substack"],
    });
    expect(body.source_receipt_id).toBe("rcpt-1");
    expect(body.entries[0].offline_probe_ok).toBe(true);
    expect(body.entries[1].offline_probe_ok).toBe(false);
    expect(mockFetch).toHaveBeenCalledWith(
      "/research/source-policy/preflight",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("rejects empty policy without network", async () => {
    await expect(postSourcePreflight({ source_policy: [] })).rejects.toThrow(
      /source_policy/,
    );
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it("surfaces HTTP errors", async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      status: 500,
      text: async () => "boom",
      json: async () => ({}),
    } as unknown as Response);
    await expect(
      postSourcePreflight({ source_policy: ["web"] }),
    ).rejects.toBeInstanceOf(SourcePreflightHttpError);
  });
});
