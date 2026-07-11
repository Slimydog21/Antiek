import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ArtifactOutlineShelf from "./ArtifactOutlineShelf";

const mocks = vi.hoisted(() => ({
  exportResearchArtifact: vi.fn(),
  getResearchArtifactBlocks: vi.fn(),
  openWindow: vi.fn(),
}));

vi.mock("../../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../lib/api")>();
  return {
    ...actual,
    exportResearchArtifact: mocks.exportResearchArtifact,
    getResearchArtifactBlocks: mocks.getResearchArtifactBlocks,
  };
});

vi.mock("../../components/windows/openWindow", () => ({
  openWindow: mocks.openWindow,
}));

describe("ArtifactOutlineShelf export window", () => {
  afterEach(cleanup);

  beforeEach(() => {
    vi.clearAllMocks();
    mocks.getResearchArtifactBlocks.mockResolvedValue({
      investigation_id: "inv-one",
      blocks: [],
    });
    mocks.exportResearchArtifact.mockResolvedValue({
      investigation_id: "inv-one",
      path: "/private/inv-one.html",
      view_url: "/research/inv-one/artifact/view",
      content_hash: "a".repeat(64),
      size_bytes: 42,
      event_id: null,
    });
  });

  it("opens the exported artifact in one stable per-investigation window", async () => {
    render(<ArtifactOutlineShelf investigationId="inv-one" />);
    fireEvent.click(await screen.findByRole("button", { name: /export research html/i }));

    await waitFor(() => expect(mocks.openWindow).toHaveBeenCalledTimes(1));
    expect(mocks.openWindow).toHaveBeenCalledWith(
      "research_artifact",
      {
        investigation_id: "inv-one",
        content_hash: "a".repeat(64),
        view_url: "/research/inv-one/artifact/view",
      },
      {
        id: "win:research_artifact:inv-one",
        title: "Research artifact",
      },
    );
    expect(screen.getByText("/private/inv-one.html")).toBeTruthy();
  });

  it("does not open a window when export fails", async () => {
    mocks.exportResearchArtifact.mockRejectedValue(new Error("export failed"));
    render(<ArtifactOutlineShelf investigationId="inv-one" />);
    fireEvent.click(await screen.findByRole("button", { name: /export research html/i }));

    expect(await screen.findByText("export failed")).toBeTruthy();
    expect(mocks.openWindow).not.toHaveBeenCalled();
  });
});
