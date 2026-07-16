/**
 * OperatorDashboard.brand.test.tsx — living-TV densify smoke.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

const apiFetchMock = vi.hoisted(() => vi.fn());
vi.mock("../../lib/api", async (orig) => ({
  ...(await orig<typeof import("../../lib/api")>()),
  apiFetch: apiFetchMock,
}));

import OperatorDashboard from "./index";

afterEach(() => {
  cleanup();
  apiFetchMock.mockReset();
});

describe("OperatorDashboard — living-TV brand densify", () => {
  it("renders session thinking + living-TV brand chrome", async () => {
    apiFetchMock.mockImplementation(async (path: string) => {
      if (String(path).includes("/publishers")) {
        return { ok: true, status: 200, json: async () => ({ publishers: [] }) };
      }
      return { ok: true, status: 200, json: async () => ({}) };
    });
    render(
      <MemoryRouter>
        <OperatorDashboard />
      </MemoryRouter>,
    );
    await waitFor(() =>
      expect(screen.getByText("Operator dashboard")).toBeTruthy(),
    );
    expect(screen.getByTestId("operator-dashboard-werner-brand")).toBeTruthy();
    const livingTv = screen.getByTestId(
      "operator-dashboard-living-tv-art",
    ) as HTMLImageElement;
    expect(livingTv.getAttribute("src") ?? "").toMatch(
      /werner_living_tv_session_v1/,
    );
  });
});
