/**
 * ResearchThis — living-TV deep_research_start on successful spin.
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { spinResearchMock, navigateMock, notifyResearchStartedMock } = vi.hoisted(
  () => ({
    spinResearchMock: vi.fn(),
    navigateMock: vi.fn(),
    notifyResearchStartedMock: vi.fn(),
  }),
);

vi.mock("react-router-dom", async (orig) => ({
  ...(await orig<typeof import("react-router-dom")>()),
  useNavigate: () => navigateMock,
}));

vi.mock("../../api/books", async (orig) => ({
  ...(await orig<typeof import("../../api/books")>()),
  spinResearch: spinResearchMock,
}));

vi.mock("../../lib/analytics", () => ({
  track: vi.fn(),
}));

vi.mock("../../werner", () => ({
  notifyResearchStarted: notifyResearchStartedMock,
}));

import ResearchThis from "./ResearchThis";

beforeEach(() => {
  spinResearchMock.mockReset();
  navigateMock.mockReset();
  notifyResearchStartedMock.mockReset();
});
afterEach(() => cleanup());

describe("ResearchThis living-TV", () => {
  it("notifies Werner deep research start after a successful spin", async () => {
    spinResearchMock.mockResolvedValue({ investigation_id: "inv-spun-1" });
    render(
      <ResearchThis documentId="doc-1" pageIndex={2} passageText="a passage" />,
    );
    fireEvent.click(
      screen.getByRole("button", { name: /research this page/i }),
    );
    await waitFor(() =>
      expect(notifyResearchStartedMock).toHaveBeenCalledWith("inv-spun-1"),
    );
    expect(navigateMock).toHaveBeenCalledWith("/inv/inv-spun-1");
  });

  it("does not notify Werner when spin fails", async () => {
    spinResearchMock.mockRejectedValue(new Error("gate denied"));
    render(<ResearchThis documentId="doc-1" pageIndex={0} />);
    fireEvent.click(
      screen.getByRole("button", { name: /research this page/i }),
    );
    await waitFor(() =>
      expect(screen.getByRole("alert").textContent).toMatch(/gate denied/),
    );
    expect(notifyResearchStartedMock).not.toHaveBeenCalled();
    expect(navigateMock).not.toHaveBeenCalled();
  });
});
