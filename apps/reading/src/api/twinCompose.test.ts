import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../lib/api", () => ({
  API_BASE: "",
  apiFetch: vi.fn(),
}));

import { apiFetch } from "../lib/api";
import {
  ComposeAnalysisHttpError,
  formatComposeMeta,
  formatHtmlPreview,
  parseComposeAnalysisResult,
  postComposeAnalysis,
} from "./twinCompose";

const mockFetch = apiFetch as unknown as ReturnType<typeof vi.fn>;

beforeEach(() => {
  mockFetch.mockReset();
});
afterEach(() => {
  vi.restoreAllMocks();
});

const sampleBody = {
  parent_asset_id: "asset-1",
  title: "Combined analysis",
  html: '<article class="antiek-twin-analysis"><h1>Combined analysis</h1></article>',
  twin_ids: ["t1", "t2"],
  insight_count: 2,
  question_count: 1,
};

describe("formatters", () => {
  it("meta and html preview", () => {
    expect(
      formatComposeMeta({
        parent_asset_id: "p",
        title: "T",
        html: "<p>x</p>",
        twin_ids: ["a"],
        insight_count: 3,
        question_count: 0,
      }),
    ).toBe("parent=p; twins=1; insights=3; questions=0");
    expect(formatHtmlPreview("short")).toBe("short");
    expect(formatHtmlPreview("x".repeat(300)).endsWith("…")).toBe(true);
    expect(formatHtmlPreview("   ")).toBe("(empty html)");
  });
});

describe("parseComposeAnalysisResult", () => {
  it("requires non-empty html, twin_ids, parent_asset_id", () => {
    expect(() =>
      parseComposeAnalysisResult({ ...sampleBody, html: "" }),
    ).toThrow(/html/);
    expect(() =>
      parseComposeAnalysisResult({ ...sampleBody, twin_ids: [] }),
    ).toThrow(/twin_ids/);
    expect(() =>
      parseComposeAnalysisResult({ ...sampleBody, parent_asset_id: "" }),
    ).toThrow(/parent_asset_id/);
  });

  it("rejects non-finite insight/question counts", () => {
    expect(() =>
      parseComposeAnalysisResult({ ...sampleBody, insight_count: Number.NaN }),
    ).toThrow(/insight_count/);
    expect(() =>
      parseComposeAnalysisResult({
        ...sampleBody,
        question_count: Number.POSITIVE_INFINITY,
      }),
    ).toThrow(/question_count/);
  });

  it("parses a valid draft", () => {
    const ok = parseComposeAnalysisResult(sampleBody);
    expect(ok.html).toMatch(/antiek-twin-analysis/);
    expect(ok.twin_ids).toEqual(["t1", "t2"]);
    expect(ok.parent_asset_id).toBe("asset-1");
    expect(ok.insight_count).toBe(2);
  });
});

describe("postComposeAnalysis", () => {
  it("POSTs compose and returns validated body", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => sampleBody,
      text: async () => "",
    } as unknown as Response);

    const body = await postComposeAnalysis({
      twin_ids: ["t1", "t2"],
      title: "Combined analysis",
      parent_asset_id: "asset-1",
    });
    expect(body.html).toMatch(/antiek-twin-analysis/);
    expect(mockFetch).toHaveBeenCalledWith(
      "/twins/compose",
      expect.objectContaining({ method: "POST" }),
    );
    const init = mockFetch.mock.calls[0][1] as { body: string };
    expect(JSON.parse(init.body)).toEqual({
      twin_ids: ["t1", "t2"],
      title: "Combined analysis",
      parent_asset_id: "asset-1",
    });
  });

  it("rejects empty twin_ids without network", async () => {
    await expect(postComposeAnalysis({ twin_ids: [] })).rejects.toThrow(
      /twin_ids/,
    );
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it("rejects 200 with empty html", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ ...sampleBody, html: "   " }),
      text: async () => "",
    } as unknown as Response);
    await expect(
      postComposeAnalysis({ twin_ids: ["t1"] }),
    ).rejects.toThrow(/html/);
  });

  it("surfaces HTTP errors (e.g. cross-parent 409)", async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      status: 409,
      text: async () => JSON.stringify({
        detail: { code: "cross_parent_compose_rejected" },
      }),
      json: async () => ({}),
    } as unknown as Response);
    await expect(
      postComposeAnalysis({ twin_ids: ["t1", "t2"] }),
    ).rejects.toBeInstanceOf(ComposeAnalysisHttpError);
  });
});
