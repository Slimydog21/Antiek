import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import ResearchThis from "./ResearchThis";

const { navigateMock, openWindowMock, spinResearchMock } = vi.hoisted(() => ({
  navigateMock: vi.fn(),
  openWindowMock: vi.fn(),
  spinResearchMock: vi.fn(),
}));

vi.mock("react-router-dom", async (orig) => {
  const actual = await orig<typeof import("react-router-dom")>();
  return { ...actual, useNavigate: () => navigateMock };
});

vi.mock("../../components/windows/openWindow", () => ({
  openWindow: openWindowMock,
}));

vi.mock("../../api/books", () => ({
  spinResearch: spinResearchMock,
}));

vi.mock("../../lib/analytics", () => ({
  track: vi.fn(),
}));

describe("ResearchThis", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("requests an exported artifact and opens a receipt window before handoff", async () => {
    spinResearchMock.mockResolvedValue({
      investigation_id: "inv-child-1",
      document_id: "doc-1",
      page_index: 4,
      gated: false,
      servability: "public_domain",
      seed_preview: "seed",
      artifact_path: "/tmp/antiek/research/inv-child-1.html",
      twin_notes_path: "/tmp/antiek/research/inv-child-1.notes.html",
    });

    render(
      <MemoryRouter>
        <ResearchThis documentId="doc-1" pageIndex={4} passageText="wing loading" />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole("button", { name: /Research this page/i }));

    await waitFor(() =>
      expect(spinResearchMock).toHaveBeenCalledWith("doc-1", 4, "wing loading", true),
    );
    expect(openWindowMock).toHaveBeenCalledWith(
      "researchArtifactReceipt",
      expect.objectContaining({
        investigationId: "inv-child-1",
        artifactPath: "/tmp/antiek/research/inv-child-1.html",
        twinNotesPath: "/tmp/antiek/research/inv-child-1.notes.html",
        documentId: "doc-1",
        pageIndex: 4,
      }),
      expect.objectContaining({ id: "win:research-artifact:inv-child-1" }),
    );
    expect(navigateMock).toHaveBeenCalledWith("/inv/inv-child-1");
  });

  it("still hands off when the backend does not return artifact paths", async () => {
    spinResearchMock.mockResolvedValue({
      investigation_id: "inv-child-2",
      document_id: "doc-1",
      page_index: 0,
      gated: true,
      servability: "gated_metadata_only",
      seed_preview: "metadata",
      artifact_path: null,
      twin_notes_path: null,
    });

    render(
      <MemoryRouter>
        <ResearchThis documentId="doc-1" pageIndex={0} />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole("button", { name: /Research this page/i }));

    await waitFor(() => expect(navigateMock).toHaveBeenCalledWith("/inv/inv-child-2"));
    expect(openWindowMock).not.toHaveBeenCalled();
  });
});
