import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import AdvertiserConsole from "./index";

const apiFetchMock = vi.hoisted(() => vi.fn());

vi.mock("../../lib/api", async (orig) => {
  const actual = await orig<typeof import("../../lib/api")>();
  return {
    ...actual,
    apiFetch: apiFetchMock,
  };
});

beforeEach(() => {
  apiFetchMock.mockReset();
  apiFetchMock.mockResolvedValue({
    ok: true,
    json: async () => ({
      campaigns: [
        {
          campaign_id: " camp-bad ",
          advertiser_name: " Malformed SaaS ",
          sector: " saas ",
          intent: " buying ",
          creative_headline: " Bad stats ",
          creative_url: "javascript:alert(1)",
          daily_budget_cents: Number.NaN,
          status: "active",
          impressions: Number.POSITIVE_INFINITY,
          clicks: Number.NaN,
          spend_cents: Number.NaN,
        },
        {
          campaign_id: "camp-good",
          advertiser_name: "Measured SaaS",
          sector: "saas",
          intent: "research",
          creative_headline: "Good stats",
          creative_url: " https://example.org/path ",
          daily_budget_cents: "5000.9",
          status: "paused",
          impressions: "1000.9",
          clicks: "25.9",
          spend_cents: "1234.9",
        },
        {
          campaign_id: " ",
          advertiser_name: "Skipped advertiser",
          creative_headline: "Skipped creative",
        },
      ],
    }),
  });
});

afterEach(() => cleanup());

describe("AdvertiserConsole", () => {
  it("sanitizes malformed campaign metrics before rendering", async () => {
    render(<AdvertiserConsole />);

    expect(await screen.findByText("Malformed SaaS")).toBeTruthy();
    expect(screen.getByText("Measured SaaS")).toBeTruthy();
    expect(document.body.textContent).not.toMatch(
      /NaN|Infinity|\$-|Skipped advertiser|javascript/,
    );
    expect(screen.getAllByText("$12.34")).toHaveLength(2);
    expect(screen.getByText("2.50%")).toBeTruthy();
    expect(screen.getByText("(#)").getAttribute("href")).toBe("#");
    expect(screen.getByText("(https://example.org/path)").getAttribute("href")).toBe(
      "https://example.org/path",
    );
  });
});
