/**
 * DocumentsIndex.test.tsx — living-TV brand densify smoke.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

const apiFetchMock = vi.hoisted(() => vi.fn());
vi.mock("../../lib/api", async (orig) => ({
  ...(await orig<typeof import("../../lib/api")>()),
  apiFetch: apiFetchMock,
}));

import DocumentsIndex from "./index";

afterEach(() => {
  cleanup();
  apiFetchMock.mockReset();
});

describe("DocumentsIndex — living-TV brand densify", () => {
  it("renders session thinking + living-TV brand chrome on the Documents door", async () => {
    apiFetchMock.mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ documents: [] }),
    });
    render(
      <MemoryRouter>
        <DocumentsIndex />
      </MemoryRouter>,
    );
    await waitFor(() => expect(screen.getByText("Documents")).toBeTruthy());
    expect(screen.getByTestId("documents-home-werner-brand")).toBeTruthy();
    const livingTv = screen.getByTestId(
      "documents-home-living-tv-art",
    ) as HTMLImageElement;
    expect(livingTv.getAttribute("src") ?? "").toMatch(
      /werner_living_tv_session_v1/,
    );
  });
});
