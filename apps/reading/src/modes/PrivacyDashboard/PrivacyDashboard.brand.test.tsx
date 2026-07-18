/**
 * PrivacyDashboard.brand.test.tsx — living-TV densify smoke.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";

const apiFetchMock = vi.hoisted(() => vi.fn());
vi.mock("../../lib/api", async (orig) => ({
  ...(await orig<typeof import("../../lib/api")>()),
  apiFetch: apiFetchMock,
}));

import PrivacyDashboard from "./index";

afterEach(() => {
  cleanup();
  apiFetchMock.mockReset();
});

describe("PrivacyDashboard — living-TV brand densify", () => {
  it("renders session thinking + living-TV brand chrome", async () => {
    apiFetchMock.mockImplementation(async (path: string) => {
      if (String(path).includes("deletion")) {
        return { ok: true, status: 200, json: async () => ({ requests: [] }) };
      }
      return {
        ok: true,
        status: 200,
        json: async () => ({
          differential_privacy_epsilon_budgets: { product_analytics: 0.5 },
          deletion_sla_days: 30,
          substrate_controls: ["private graph isolation"],
          compliance_frameworks: [],
          loop_3_unlock_status: {},
        }),
      };
    });
    render(<PrivacyDashboard />);
    await waitFor(() =>
      expect(screen.getByText("Privacy dashboard")).toBeTruthy(),
    );
    expect(screen.getByTestId("privacy-dashboard-werner-brand")).toBeTruthy();
    const livingTv = screen.getByTestId(
      "privacy-dashboard-living-tv-art",
    ) as HTMLImageElement;
    expect(livingTv.getAttribute("src") ?? "").toMatch(
      /werner_living_tv_session_v1/,
    );
  });
});
