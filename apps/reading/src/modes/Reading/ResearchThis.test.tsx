import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

const { spinResearchMock, navigateMock, trackMock } = vi.hoisted(() => ({
  spinResearchMock: vi.fn(),
  navigateMock: vi.fn(),
  trackMock: vi.fn(),
}));

vi.mock("../../api/books", async (orig) => ({
  ...(await orig<typeof import("../../api/books")>()),
  spinResearch: spinResearchMock,
}));

vi.mock("../../lib/analytics", () => ({
  track: trackMock,
}));

vi.mock("react-router-dom", async (orig) => ({
  ...(await orig<typeof import("react-router-dom")>()),
  useNavigate: () => navigateMock,
}));

import ResearchThis from "./ResearchThis";

describe("ResearchThis", () => {
  beforeEach(() => {
    spinResearchMock.mockReset();
    navigateMock.mockReset();
    trackMock.mockReset();
  });

  afterEach(cleanup);

  it("sends the page research request and hands off to the child investigation", async () => {
    spinResearchMock.mockResolvedValue({
      investigation_id: " inv-child ",
      document_id: "doc-1",
      page_index: 4,
      gated: false,
      servability: "public_domain",
      seed_preview: "seed",
    });

    render(
      <ResearchThis
        documentId="doc-1"
        pageIndex={4}
        passageText="selected passage"
      />,
    );

    await userEvent.click(screen.getByRole("button", { name: "Research this page" }));

    await waitFor(() =>
      expect(spinResearchMock).toHaveBeenCalledWith("doc-1", 4, "selected passage"),
    );
    expect(trackMock).toHaveBeenCalledWith("reading_research_spun", {
      document_id: "doc-1",
      page_index: 4,
      has_passage: true,
    });
    expect(navigateMock).toHaveBeenCalledWith("/inv/inv-child");
  });

  it("surfaces malformed spun investigation ids instead of navigating", async () => {
    spinResearchMock.mockResolvedValue({
      investigation_id: " ",
      document_id: "doc-1",
      page_index: 4,
      gated: false,
      servability: "public_domain",
      seed_preview: "seed",
    });

    render(<ResearchThis documentId="doc-1" pageIndex={4} passageText="selected passage" />);

    await userEvent.click(screen.getByRole("button", { name: "Research this page" }));

    expect(await screen.findByText(/Couldn’t start page research/i)).toBeTruthy();
    expect(screen.getByText(/Engine: investigation_id must be a non-empty string/i)).toBeTruthy();
    expect(navigateMock).not.toHaveBeenCalled();
    expect(trackMock).not.toHaveBeenCalled();
  });

  it("surfaces a missing book without navigating to a dead research", async () => {
    spinResearchMock.mockRejectedValue(new Error("book_not_found"));

    render(<ResearchThis documentId="missing-doc" pageIndex={0} />);

    await userEvent.click(screen.getByRole("button", { name: "Research this page" }));

    expect((await screen.findByRole("alert")).textContent).toBe("Book not found.");
    expect(navigateMock).not.toHaveBeenCalled();
    expect(trackMock).not.toHaveBeenCalled();
  });

  it("frames spin failures as retryable engine failures, not raw text", async () => {
    spinResearchMock.mockRejectedValue(new Error("Spin research isn’t available right now."));

    render(<ResearchThis documentId="doc-1" pageIndex={2} passageText="selected passage" />);

    await userEvent.click(screen.getByRole("button", { name: "Research this page" }));

    expect(await screen.findByText(/Couldn’t start page research/i)).toBeTruthy();
    expect(screen.getByText(/Engine: Spin research isn’t available right now/i)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Try again" })).toBeTruthy();
    expect(navigateMock).not.toHaveBeenCalled();
    expect(trackMock).not.toHaveBeenCalled();
  });
});
