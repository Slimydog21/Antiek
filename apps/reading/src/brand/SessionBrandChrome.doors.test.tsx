/**
 * SessionBrandChrome.doors.test.tsx — residual doors using shared chrome.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { SESSION_LIVING_TV_ASSET_HINT } from "./SessionBrandChrome";
import TrustCenter from "../modes/TrustCenter";
import PricingPage from "../modes/Pricing";
import Map from "../modes/Map";

const apiFetchMock = vi.hoisted(() => vi.fn());
vi.mock("../lib/api", async (orig) => ({
  ...(await orig<typeof import("../lib/api")>()),
  apiFetch: apiFetchMock,
}));

afterEach(() => {
  cleanup();
  apiFetchMock.mockReset();
});

function expectBrand(prefix: string) {
  expect(screen.getByTestId(`${prefix}-werner-brand`)).toBeTruthy();
  const art = screen.getByTestId(`${prefix}-living-tv-art`) as HTMLImageElement;
  expect(art.getAttribute("src") ?? "").toMatch(SESSION_LIVING_TV_ASSET_HINT);
}

describe("SessionBrandChrome residual doors", () => {
  it("Trust Center densify", async () => {
    apiFetchMock.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        differential_privacy_epsilon_budgets: {},
        deletion_sla_days: 30,
        substrate_controls: [],
        compliance_frameworks: [],
        loop_3_unlock_status: {},
      }),
    });
    render(<TrustCenter />);
    await waitFor(() => expect(screen.getByText("Trust Center")).toBeTruthy());
    expectBrand("trust-center");
  });

  it("Pricing densify", () => {
    render(<PricingPage />);
    expect(screen.getByText("Pricing")).toBeTruthy();
    expectBrand("pricing-home");
  });

  it("Application map densify", () => {
    render(
      <MemoryRouter>
        <Map />
      </MemoryRouter>,
    );
    expect(screen.getByText("Application map")).toBeTruthy();
    expectBrand("map-home");
  });
});
