import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../lib/api", () => ({
  API_BASE: "",
  apiFetch: vi.fn(),
}));

import { apiFetch } from "../lib/api";
import { decideViewPreference, formatViewMode } from "./htmlPreference";

const mockFetch = apiFetch as unknown as ReturnType<typeof vi.fn>;

beforeEach(() => {
  mockFetch.mockReset();
});
afterEach(() => {
  vi.restoreAllMocks();
});

describe("formatViewMode", () => {
  it("labels html as preferred", () => {
    expect(formatViewMode("html")).toMatch(/HTML/i);
    expect(formatViewMode("html")).toMatch(/preferred/i);
  });

  it("labels metadata_only as policy block", () => {
    expect(formatViewMode("metadata_only")).toMatch(/metadata/i);
    expect(formatViewMode("metadata_only")).toMatch(/blocked/i);
  });
});

describe("decideViewPreference", () => {
  it("POSTs decide and returns body", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        mode: "html",
        preferred: true,
        reason: "html_ready",
        notes: [],
      }),
      text: async () => "",
    } as unknown as Response);

    const body = await decideViewPreference({
      html_ready: true,
      pdf_available: true,
      require_html: true,
      asset_id: "doc-1",
    });
    expect(body.mode).toBe("html");
    expect(body.preferred).toBe(true);
    const [url, init] = mockFetch.mock.calls[0];
    expect(url).toBe("/assets/view-preference/decide");
    expect(init?.method).toBe("POST");
    const payload = JSON.parse(init?.body as string);
    expect(payload.html_ready).toBe(true);
    expect(payload.require_html).toBe(true);
  });
});
