import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../lib/api", () => ({
  API_BASE: "",
  apiFetch: vi.fn(),
}));

import { apiFetch } from "../lib/api";
import {
  FreeCopyHttpError,
  formatFreeCopySummary,
  parseFreeCopyPreflightResult,
  postFreeCopyPreflight,
} from "./bookFreeCopy";

const mockFetch = apiFetch as unknown as ReturnType<typeof vi.fn>;

beforeEach(() => {
  mockFetch.mockReset();
});
afterEach(() => {
  vi.restoreAllMocks();
});

const foundBody = {
  freely_available: true,
  title: "Walden",
  author: "Thoreau",
  source: "gutenberg",
  rights_basis: "copyright=false",
  retrieved_at: "2026-07-11T00:00:00+00:00",
  candidate_kind: "PublicDomainWork",
  candidate_ref_withheld: true,
  outcomes: [],
  checked_at: "2026-07-11T00:00:00+00:00",
};

const notFoundBody = {
  freely_available: false,
  title: "Unknown",
  author: null,
  source: null,
  rights_basis: null,
  retrieved_at: null,
  candidate_kind: null,
  candidate_ref_withheld: true,
  outcomes: [
    {
      source: "gutenberg",
      found: false,
      query: "Unknown",
      timestamp: "2026-07-11T00:00:00+00:00",
      error: null,
    },
  ],
  checked_at: "2026-07-11T00:00:00+00:00",
};

describe("parseFreeCopyPreflightResult", () => {
  it("requires boolean freely_available (no invent)", () => {
    expect(() =>
      parseFreeCopyPreflightResult({ ...foundBody, freely_available: "yes" }),
    ).toThrow(/freely_available/);
    expect(() => {
      const { freely_available: _f, ...rest } = foundBody;
      parseFreeCopyPreflightResult(rest);
    }).toThrow(/freely_available/);
  });

  it("true requires source and rights_basis", () => {
    expect(() =>
      parseFreeCopyPreflightResult({ ...foundBody, source: null }),
    ).toThrow(/source/);
    expect(() =>
      parseFreeCopyPreflightResult({ ...foundBody, rights_basis: "" }),
    ).toThrow(/rights_basis/);
  });

  it("false must not name a source hit", () => {
    expect(() =>
      parseFreeCopyPreflightResult({
        ...notFoundBody,
        source: "gutenberg",
      }),
    ).toThrow(/source hit/);
  });

  it("parses found and not-found", () => {
    expect(parseFreeCopyPreflightResult(foundBody).freely_available).toBe(true);
    expect(parseFreeCopyPreflightResult(notFoundBody).freely_available).toBe(
      false,
    );
  });
});

describe("postFreeCopyPreflight", () => {
  it("POSTs and validates", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => foundBody,
      text: async () => "",
    } as unknown as Response);
    const r = await postFreeCopyPreflight({
      title: "Walden",
      author: "Thoreau",
    });
    expect(r.freely_available).toBe(true);
    expect(mockFetch).toHaveBeenCalledWith(
      "/books/free-copy/preflight",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("rejects empty title without network", async () => {
    await expect(postFreeCopyPreflight({ title: "  " })).rejects.toThrow(
      /title/,
    );
    expect(mockFetch).not.toHaveBeenCalled();
  });

  it("surfaces HTTP errors", async () => {
    mockFetch.mockResolvedValue({
      ok: false,
      status: 502,
      text: async () => "upstream",
      json: async () => ({}),
    } as unknown as Response);
    await expect(
      postFreeCopyPreflight({ title: "Walden" }),
    ).rejects.toBeInstanceOf(FreeCopyHttpError);
  });
});

describe("formatFreeCopySummary", () => {
  it("summarizes", () => {
    expect(formatFreeCopySummary(parseFreeCopyPreflightResult(foundBody))).toMatch(
      /Free copy found/,
    );
    expect(
      formatFreeCopySummary(parseFreeCopyPreflightResult(notFoundBody)),
    ).toMatch(/No free copy/);
  });
});
