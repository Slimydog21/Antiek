import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../lib/api", () => ({
  API_BASE: "",
  apiFetch: vi.fn(),
}));

import { apiFetch } from "../lib/api";
import {
  SourcePackHttpError,
  formatSourcePackSummary,
  parseSourcePackResult,
  postSourcePack,
} from "./sourcePack";

const mockFetch = apiFetch as unknown as ReturnType<typeof vi.fn>;

beforeEach(() => mockFetch.mockReset());
afterEach(() => vi.restoreAllMocks());

const sample = {
  selected: ["arxiv"],
  entries: [
    {
      source: "arxiv",
      pack_status: "included",
      readiness_status: "ready",
      adapter_importable: true,
      offline_probe_ok: true,
      runner_consumes_today: false,
      note: "ok",
    },
  ],
  pack_text: "# Deep research source pack\n",
  included_count: 1,
  notes: ["live_fetch_authorized=false"],
  authority: "advisory_preflight",
  live_fetch_authorized: false,
};

describe("parseSourcePackResult", () => {
  it("parses valid pack", () => {
    const r = parseSourcePackResult(sample);
    expect(r.included_count).toBe(1);
    expect(r.live_fetch_authorized).toBe(false);
  });

  it("rejects live_fetch true and wrong authority", () => {
    expect(() =>
      parseSourcePackResult({ ...sample, live_fetch_authorized: true }),
    ).toThrow(/live_fetch/);
    expect(() =>
      parseSourcePackResult({ ...sample, authority: "live" }),
    ).toThrow(/authority/);
  });
});

describe("postSourcePack", () => {
  it("POSTs", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => sample,
      text: async () => "",
    } as unknown as Response);
    const r = await postSourcePack({ selected: ["arxiv"] });
    expect(r.pack_text).toMatch(/source pack/);
  });

  it("rejects empty selected without network", async () => {
    await expect(postSourcePack({ selected: [] })).rejects.toThrow(/selected/);
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it("HTTP errors", async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      status: 400,
      text: async () => "bad",
      json: async () => ({}),
    } as unknown as Response);
    await expect(postSourcePack({ selected: ["arxiv"] })).rejects.toBeInstanceOf(
      SourcePackHttpError,
    );
  });
});

describe("formatSourcePackSummary", () => {
  it("summarizes", () => {
    expect(formatSourcePackSummary(parseSourcePackResult(sample))).toMatch(
      /included=1/,
    );
  });
});
