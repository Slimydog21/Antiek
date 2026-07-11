import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../lib/api", () => ({
  API_BASE: "",
  apiFetch: vi.fn(),
}));

import { apiFetch } from "../lib/api";
import {
  HtmlHostHttpError,
  formatHtmlHostSummary,
  parseHtmlHostReceipt,
  postHtmlHostEvaluate,
} from "./htmlHost";

const mockFetch = apiFetch as unknown as ReturnType<typeof vi.fn>;
const SHA = "c".repeat(64);

beforeEach(() => mockFetch.mockReset());
afterEach(() => vi.restoreAllMocks());

const sample = {
  host_allowed: true,
  hosted: false,
  acquisition_path: "free_copy",
  parent_asset_id: "asset-1",
  title: "Walden",
  html_sha256: SHA,
  html_bytes: 100,
  view_mode: "html",
  reasons: [],
  notes: ["hosted=false"],
  authority: "html_host_port_advisory",
  purchase_executed: false,
};

describe("parseHtmlHostReceipt", () => {
  it("parses allow", () => {
    const r = parseHtmlHostReceipt(sample);
    expect(r.host_allowed).toBe(true);
    expect(r.hosted).toBe(false);
  });

  it("rejects hosted true and purchase_executed true", () => {
    expect(() =>
      parseHtmlHostReceipt({ ...sample, hosted: true }),
    ).toThrow(/hosted/);
    expect(() =>
      parseHtmlHostReceipt({ ...sample, purchase_executed: true }),
    ).toThrow(/purchase_executed/);
  });

  it("rejects host_allowed without sha or wrong path", () => {
    expect(() =>
      parseHtmlHostReceipt({ ...sample, html_sha256: "bad" }),
    ).toThrow(/html_sha256/);
    expect(() =>
      parseHtmlHostReceipt({ ...sample, acquisition_path: "unknown" }),
    ).toThrow(/free_copy or purchase_intent/);
  });
});

describe("postHtmlHostEvaluate", () => {
  it("POSTs", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => sample,
      text: async () => "",
    } as unknown as Response);
    const r = await postHtmlHostEvaluate({
      title: "Walden",
      free_copy_preflight: { freely_available: true },
      html_projection: { ready: true, html_sha256: SHA, html_bytes: 100 },
    });
    expect(r.view_mode).toBe("html");
  });

  it("rejects purchase_executed without network", async () => {
    await expect(
      postHtmlHostEvaluate({
        title: "X",
        purchase_gate: {
          purchase_intent_allowed: true,
          purchase_executed: true,
        },
      }),
    ).rejects.toThrow(/purchase_executed/);
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it("HTTP errors", async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      status: 400,
      text: async () => "bad",
      json: async () => ({}),
    } as unknown as Response);
    await expect(
      postHtmlHostEvaluate({ title: "X" }),
    ).rejects.toBeInstanceOf(HtmlHostHttpError);
  });
});

describe("formatHtmlHostSummary", () => {
  it("summarizes", () => {
    expect(formatHtmlHostSummary(parseHtmlHostReceipt(sample))).toMatch(
      /host_allowed=true/,
    );
  });
});
