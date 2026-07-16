/**
 * NotebooksIndex.test.tsx — living-TV brand densify + basic list smoke.
 *
 * Pins session brand chrome on the Notebooks door so product paths consume
 * Imagine session assets (not inventory-only).
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

const apiFetchMock = vi.hoisted(() => vi.fn());
vi.mock("../../lib/api", async (orig) => ({
  ...(await orig<typeof import("../../lib/api")>()),
  apiFetch: apiFetchMock,
}));

import NotebooksIndex from "./index";

afterEach(() => {
  cleanup();
  apiFetchMock.mockReset();
});

function renderIndex() {
  return render(
    <MemoryRouter>
      <NotebooksIndex />
    </MemoryRouter>,
  );
}

describe("NotebooksIndex — living-TV brand densify", () => {
  it("renders session thinking + living-TV brand chrome on the Notebooks door", async () => {
    apiFetchMock.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ count: 0, notebooks: [] }),
    });
    renderIndex();
    await waitFor(() => expect(screen.getByText("Notebooks")).toBeTruthy());
    expect(screen.getByTestId("notebooks-home-werner-brand")).toBeTruthy();
    const livingTv = screen.getByTestId(
      "notebooks-home-living-tv-art",
    ) as HTMLImageElement;
    expect(livingTv.getAttribute("src") ?? "").toMatch(
      /werner_living_tv_session_v1/,
    );
  });
});
