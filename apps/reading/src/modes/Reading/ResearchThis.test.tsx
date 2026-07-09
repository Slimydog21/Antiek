import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

import ResearchThis from "./ResearchThis";

const launchFloatingDeepResearch = vi.fn();
const spinResearch = vi.fn();
const navigate = vi.fn();

vi.mock("./launchFloatingDeepResearch", () => ({
  launchFloatingDeepResearch: (...args: unknown[]) =>
    launchFloatingDeepResearch(...args),
}));

vi.mock("../../api/books", () => ({
  spinResearch: (...args: unknown[]) => spinResearch(...args),
}));

vi.mock("react-router-dom", async (importOriginal) => {
  const actual = await importOriginal<typeof import("react-router-dom")>();
  return {
    ...actual,
    useNavigate: () => navigate,
  };
});

vi.mock("../../lib/analytics", () => ({
  track: vi.fn(),
}));

describe("ResearchThis residual cc", () => {
  beforeEach(() => {
    launchFloatingDeepResearch.mockReset();
    spinResearch.mockReset();
    navigate.mockReset();
  });

  afterEach(() => cleanup());

  it("opens floating deep research window from passage", async () => {
    launchFloatingDeepResearch.mockResolvedValue({
      session_id: "fsess_1",
      spawn_id: "spn_1",
      investigation_id: "inv_1",
      parent_asset_id: "doc-1",
      window_id: "wdr_fsess_1",
      view_format: "html",
      view_mode: "floating",
      status: "reserved",
    });

    render(
      <MemoryRouter>
        <ResearchThis
          documentId="doc-1"
          pageIndex={0}
          passageText="Attention is content-addressable memory."
        />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByTestId("research-this-floating"));
    await waitFor(() => {
      expect(launchFloatingDeepResearch).toHaveBeenCalled();
    });
    const call = launchFloatingDeepResearch.mock.calls.at(-1)?.[0] as {
      asset_id: string;
      selection_text: string;
      view_mode: string;
    };
    expect(call.asset_id).toBe("doc-1");
    expect(call.selection_text).toMatch(/Attention/);
    expect(call.view_mode).toBe("floating");
    await waitFor(() => {
      expect(screen.getByTestId("research-this-window-id").textContent).toMatch(
        /wdr_fsess_1/,
      );
    });
  });

  it("full workstation path still navigates via spinResearch", async () => {
    spinResearch.mockResolvedValue({ investigation_id: "inv_full" });
    render(
      <MemoryRouter>
        <ResearchThis documentId="doc-1" pageIndex={0} passageText="hello world" />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByTestId("research-this-full"));
    await waitFor(() => {
      expect(spinResearch).toHaveBeenCalledWith("doc-1", 0, "hello world");
    });
    expect(navigate).toHaveBeenCalledWith("/inv/inv_full");
  });
});
