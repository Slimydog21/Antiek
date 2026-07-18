/**
 * BrainstormStation.brand.test.tsx — empty-state living-TV densify.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

vi.mock("../../lib/api", () => ({
  listWatchForLater: vi.fn(async () => ({ questions: [] })),
  launchParkedQuestion: vi.fn(),
}));

vi.mock("../../workspace/PanelHost", () => ({
  PanelHost: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="panel-host">{children}</div>
  ),
}));

import BrainstormStation from "./index";

afterEach(() => {
  cleanup();
});

describe("BrainstormStation — living-TV brand densify", () => {
  it("renders session thinking + living-TV brand chrome on empty state", async () => {
    render(
      <MemoryRouter>
        <BrainstormStation />
      </MemoryRouter>,
    );
    await waitFor(() =>
      expect(screen.getByText(/watch-for-later folder/i)).toBeTruthy(),
    );
    expect(screen.getByTestId("brainstorm-empty-werner-brand")).toBeTruthy();
    const livingTv = screen.getByTestId(
      "brainstorm-empty-living-tv-art",
    ) as HTMLImageElement;
    expect(livingTv.getAttribute("src") ?? "").toMatch(
      /werner_living_tv_session_v1/,
    );
  });
});
