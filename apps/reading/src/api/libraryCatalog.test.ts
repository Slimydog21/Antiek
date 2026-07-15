import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../lib/api", () => ({
  API_BASE: "",
  apiFetch: vi.fn(),
}));

import { apiFetch } from "../lib/api";
import {
  fetchLibraryCatalog,
  formatServability,
  LibraryCatalogHttpError,
  parseBookSummary,
  parseLibraryPage,
} from "./libraryCatalog";

const mockFetch = apiFetch as unknown as ReturnType<typeof vi.fn>;

beforeEach(() => {
  mockFetch.mockReset();
});
afterEach(() => {
  vi.restoreAllMocks();
});

const work = {
  document_id: "doc-1",
  title: "Scaling Laws",
  author: "Kaplan",
  servability: "servable",
  servable_full_text: true,
  page_count: 12,
  cover_uri: null,
  ip_holder_id: null,
  taken_down: false,
};

describe("parse honesty", () => {
  it("accepts metadata-only summary", () => {
    const s = parseBookSummary(work);
    expect(s.document_id).toBe("doc-1");
    expect(s.servable_full_text).toBe(true);
  });

  it("rejects body-like keys on works", () => {
    expect(() =>
      parseBookSummary({ ...work, body: "secret full text" }),
    ).toThrow(/body/);
    expect(() => parseBookSummary({ ...work, full_text: "nope" })).toThrow(
      /full_text/,
    );
    expect(() =>
      parseLibraryPage({
        works: [{ ...work, content: "x" }],
        total: 1,
        page: 1,
        page_size: 20,
      }),
    ).toThrow(/content/);
    expect(() =>
      parseLibraryPage({
        works: [work],
        total: 1,
        page: 1,
        page_size: 20,
        debug: { payload: { raw_text: "nested leak" } },
      }),
    ).toThrow(/raw_text/);
  });

  it("rejects missing required fields without inventing", () => {
    expect(() => parseBookSummary({ title: "x" })).toThrow(/document_id/);
    expect(() =>
      parseLibraryPage({ works: [work], total: -1, page: 1, page_size: 20 }),
    ).toThrow(/total/);
    expect(() =>
      parseBookSummary({ ...work, title: { value: "coerce me" } }),
    ).toThrow(/title/);
    expect(() => parseBookSummary({ ...work, page_count: 1.5 })).toThrow(
      /page_count/,
    );
    expect(() =>
      parseLibraryPage({ works: [work], total: 0, page: 1, page_size: 20 }),
    ).toThrow(/works length/);
  });

  it("formatServability honesty", () => {
    expect(formatServability(parseBookSummary(work))).toMatch(/servable/i);
    expect(
      formatServability(
        parseBookSummary({
          ...work,
          servable_full_text: false,
          servability: "rights_gated",
        }),
      ),
    ).toMatch(/gated/i);
    expect(
      formatServability(parseBookSummary({ ...work, taken_down: true })),
    ).toMatch(/taken down/i);
  });
});

describe("fetchLibraryCatalog", () => {
  it("GETs /library with query and parses page", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        works: [work],
        total: 1,
        page: 1,
        page_size: 20,
      }),
      text: async () => "",
    } as unknown as Response);

    const page = await fetchLibraryCatalog({
      filter: "servable",
      search: "scaling",
      page: 1,
      page_size: 20,
    });
    expect(page.total).toBe(1);
    expect(page.works[0].title).toBe("Scaling Laws");
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringMatching(/^\/library\?/),
      expect.objectContaining({ method: "GET" }),
    );
    const url = mockFetch.mock.calls[0][0] as string;
    expect(url).toMatch(/filter=servable/);
    expect(url).toMatch(/search=scaling/);
  });

  it("surfaces HTTP errors", async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      status: 500,
      text: async () => "db down",
      json: async () => ({}),
    } as unknown as Response);
    await expect(fetchLibraryCatalog()).rejects.toBeInstanceOf(
      LibraryCatalogHttpError,
    );
  });

  it("rejects invalid request pagination before network I/O", async () => {
    await expect(fetchLibraryCatalog({ page: 0 })).rejects.toThrow(/page/);
    await expect(fetchLibraryCatalog({ page_size: 201 })).rejects.toThrow(
      /page_size/,
    );
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it("rejects body leakage on 200", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        works: [{ ...work, raw_text: "leaked" }],
        total: 1,
        page: 1,
        page_size: 20,
      }),
      text: async () => "",
    } as unknown as Response);
    await expect(fetchLibraryCatalog()).rejects.toThrow(/raw_text/);
  });
});
