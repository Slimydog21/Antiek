import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";

const composeMock = vi.hoisted(() => vi.fn());
vi.mock("../../api/research", async (orig) => {
  const actual = await orig<typeof import("../../api/research")>();
  return { ...actual, composeResearchArtifacts: composeMock };
});

import ResearchCompositionReview from "./ResearchCompositionReview";

afterEach(() => {
  cleanup();
  composeMock.mockReset();
});

describe("ResearchCompositionReview", () => {
  it("revalidates IDs and renders the ordered server index with honest copy", async () => {
    composeMock.mockResolvedValue({
      kind: "artifact_index",
      members: [
        { investigation_id: "b", question: "Second chosen", content_hash: "abcdef1234567890", blocks: [{ node_id: "n1", kind: "insight", label: "A block", investigation_id: "b" }] },
        { investigation_id: "a", question: "First chosen", content_hash: "123456abcdef7890", blocks: [] },
      ],
      conflicts: [{ first_investigation_id: "b", second_investigation_id: "a", content_hash: "abcdef1234567890" }],
    });
    render(<ResearchCompositionReview investigationIds={["b", "a"]} />);

    expect(screen.getByText("Collected research — not yet synthesized.")).toBeTruthy();
    await waitFor(() => expect(composeMock).toHaveBeenCalledWith(["b", "a"]));
    const items = screen.getAllByRole("listitem");
    expect(items[0].textContent).toContain("Second chosen");
    expect(screen.getByText(/share hash abcdef123456/)).toBeTruthy();
  });

  it("does not call transport for a stale malformed payload", () => {
    render(<ResearchCompositionReview investigationIds={["same", "same"]} />);
    expect(screen.getByRole("alert").textContent).toContain("no longer valid");
    expect(composeMock).not.toHaveBeenCalled();
  });
});
