/**
 * WrestleApp.brand.test.tsx — empty-state living-TV densify.
 *
 * The wrestle empty state is a product door (load PDF to begin). Session
 * brand marks must appear so wait/load is home of the penguin.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";

vi.mock("../../hooks/useEventStream", () => ({
  useEventStream: () => ({
    events: [],
    status: "idle",
    reconnects: 0,
  }),
}));

vi.mock("../../workspace/PanelHost", () => ({
  PanelHost: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="panel-host">{children}</div>
  ),
}));

import WrestleApp from "./index";

afterEach(() => {
  cleanup();
});

function renderEmpty() {
  return render(
    <MemoryRouter initialEntries={["/wrestle"]}>
      <Routes>
        <Route path="/wrestle" element={<WrestleApp />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("WrestleApp empty-state brand densify", () => {
  it("renders session thinking + living-TV brand chrome before a PDF is loaded", () => {
    renderEmpty();
    expect(screen.getByText(/Load a PDF to wrestle/i)).toBeTruthy();
    expect(screen.getByTestId("wrestle-empty-werner-brand")).toBeTruthy();
    const livingTv = screen.getByTestId(
      "wrestle-empty-living-tv-art",
    ) as HTMLImageElement;
    expect(livingTv.getAttribute("src") ?? "").toMatch(
      /werner_living_tv_session_v1/,
    );
  });
});
