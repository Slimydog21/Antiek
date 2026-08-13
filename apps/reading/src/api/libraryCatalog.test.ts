import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";

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
import { fetchLibraryPage, useLibrary } from "../components/library/useLibrary";

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
  servability: "public_domain",
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
    ).toThrow("library catalog response rejected");
    expect(() => parseBookSummary({ ...work, full_text: "nope" })).toThrow(
      "library catalog response rejected",
    );
    expect(() =>
      parseLibraryPage({
        works: [{ ...work, content: "x" }],
        total: 1,
        page: 1,
        page_size: 20,
      }),
    ).toThrow("library catalog response rejected");
    expect(() =>
      parseLibraryPage({
        works: [work],
        total: 1,
        page: 1,
        page_size: 20,
        debug: { payload: { raw_text: "nested leak" } },
      }),
    ).toThrow("library catalog response rejected");
  });

  it.each(["snippet", "abstract", "description", "payload", "unknown"])(
    "rejects unknown key %s with a value-free error",
    (key) => {
      expect(() => parseBookSummary({ ...work, [key]: "private-marker" })).toThrow(
        "library catalog response rejected",
      );
      try { parseBookSummary({ ...work, [key]: "private-marker" }); } catch (error) {
        expect(String(error)).not.toContain("private-marker");
      }
    },
  );

  it("rejects missing required fields without inventing", () => {
    expect(() => parseBookSummary({ title: "x" })).toThrow("library catalog response rejected");
    const { author: _author, ...withoutAuthor } = work;
    expect(() => parseBookSummary(withoutAuthor)).toThrow("library catalog response rejected");
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
    ).toThrow(/pagination metadata/);
  });

  it("rejects contradictory rights and takedown claims", () => {
    expect(() =>
      parseBookSummary({
        ...work,
        servability: "gated_metadata_only",
        servable_full_text: true,
      }),
    ).toThrow(/servable_full_text contradicts/);
    expect(() =>
      parseBookSummary({ ...work, servability: "taken_down" }),
    ).toThrow(/taken_down contradicts/);
    expect(() => parseBookSummary({ ...work, taken_down: true })).toThrow(
      /taken_down contradicts/,
    );
  });

  it("formatServability honesty", () => {
    expect(formatServability(parseBookSummary(work))).toMatch(/servable/i);
    expect(
      formatServability(
        parseBookSummary({
          ...work,
          servable_full_text: false,
          servability: "gated_metadata_only",
        }),
      ),
    ).toMatch(/gated/i);
    expect(
      formatServability(
        parseBookSummary({
          ...work,
          servability: "taken_down",
          servable_full_text: false,
          taken_down: true,
        }),
      ),
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
    await expect(fetchLibraryCatalog()).rejects.not.toThrow(/db down/);
  });

  it("rejects invalid request pagination before network I/O", async () => {
    await expect(fetchLibraryCatalog({ page: 0 })).rejects.toThrow(/page/);
    await expect(fetchLibraryCatalog({ page_size: 201 })).rejects.toThrow(
      /page_size/,
    );
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it("rejects incomplete, out-of-range, or mismatched pagination", async () => {
    for (const payload of [
      { works: [], total: 100, page: 1, page_size: 20 },
      { works: [work], total: 1, page: 2, page_size: 20 },
    ]) {
      mockFetch.mockResolvedValueOnce({
        ok: true,
        status: 200,
        json: async () => payload,
      } as Response);
      await expect(fetchLibraryCatalog()).rejects.toThrow(/page|pagination/);
    }

    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({
        works: [work],
        total: 1,
        page: 1,
        page_size: 20,
      }),
    } as Response);
    await expect(fetchLibraryCatalog({ page_size: 10 })).rejects.toThrow(
      /does not match request/,
    );
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
    await expect(fetchLibraryCatalog()).rejects.toThrow("library catalog response rejected");
  });
});

describe("production Library browse integration", () => {
  it("clears stale works while a superseding query is loading", async () => {
    const response = (title: string) =>
      ({
        ok: true,
        status: 200,
        json: async () => ({
          works: [{ ...work, title }],
          total: 1,
          page: 1,
          page_size: 20,
        }),
      }) as Response;
    mockFetch.mockResolvedValueOnce(response("First result"));
    let resolveSecond!: (response: Response) => void;
    const second = new Promise<Response>((resolve) => {
      resolveSecond = resolve;
    });
    mockFetch.mockReturnValueOnce(second);

    const { result, rerender } = renderHook(
      ({ search }) =>
        useLibrary({ filter: "all", search, page: 1, pageSize: 20 }),
      { initialProps: { search: "first" } },
    );
    await waitFor(() => expect(result.current.works).toHaveLength(1));

    rerender({ search: "second" });
    expect(result.current.loading).toBe(true);
    expect(result.current.works).toEqual([]);
    expect(result.current.total).toBe(0);

    await act(async () => resolveSecond(response("Second result")));
    await waitFor(() =>
      expect(result.current.works[0]?.title).toBe("Second result"),
    );
  });

  it("routes the existing LibraryView hook through the fail-closed parser", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        works: [{ ...work, body: "must not reach LibraryView" }],
        total: 1,
        page: 1,
        page_size: 20,
      }),
      text: async () => "",
    } as unknown as Response);

    await expect(
      fetchLibraryPage({ filter: "all", search: "", page: 1, pageSize: 20 }),
    ).rejects.toThrow("library catalog response rejected");
  });

  it("preserves the existing honest route-absent signal for a 404", async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      status: 404,
      text: async () => "not found",
      json: async () => ({}),
    } as unknown as Response);

    await expect(
      fetchLibraryPage({ filter: "all", search: "", page: 1, pageSize: 20 }),
    ).rejects.toThrow("library_route_absent");
  });
});
