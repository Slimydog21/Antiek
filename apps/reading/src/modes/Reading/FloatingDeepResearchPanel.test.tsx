import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import FloatingDeepResearchPanel from "./FloatingDeepResearchPanel";

afterEach(() => {
  cleanup();
});

describe("FloatingDeepResearchPanel", () => {
  it("spawns instance and shows honesty flags", async () => {
    render(
      <FloatingDeepResearchPanel
        gated={false}
        initialParentAssetId="asset-1"
        initialHighlight="interesting claim"
      />,
    );
    fireEvent.click(screen.getByTestId("fdr-spawn"));
    await waitFor(() => {
      expect(screen.getByTestId("fdr-instances").textContent).toMatch(
        /live_dispatched=false/,
      );
    });
  });

  it("fails closed when gated", async () => {
    render(
      <FloatingDeepResearchPanel
        gated={true}
        initialParentAssetId="asset-1"
        initialHighlight="secret"
      />,
    );
    fireEvent.click(screen.getByTestId("fdr-spawn"));
    await waitFor(() => {
      expect(screen.getByTestId("fdr-error").textContent).toMatch(/gated/);
    });
  });

  it("draft merge intent never executes", async () => {
    render(
      <FloatingDeepResearchPanel
        gated={false}
        initialParentAssetId="asset-1"
        initialHighlight="claim A"
      />,
    );
    fireEvent.click(screen.getByTestId("fdr-spawn"));
    await waitFor(() => {
      expect(screen.getByTestId("fdr-instances").textContent).toMatch(/fdr_/);
    });
    const draftBtns = screen.getAllByText(/Draft merge intent/);
    fireEvent.click(draftBtns[0]);
    await waitFor(() => {
      expect(screen.getByTestId("fdr-merge-intent").textContent).toMatch(
        /draft_merge/,
      );
      expect(screen.getByTestId("fdr-merge-intent").textContent).toMatch(
        /executed=false/,
      );
    });
  });

  it("collective pack from two selections", async () => {
    render(
      <FloatingDeepResearchPanel
        gated={false}
        initialParentAssetId="asset-1"
        initialHighlight="first"
      />,
    );
    fireEvent.click(screen.getByTestId("fdr-spawn"));
    fireEvent.change(screen.getByTestId("fdr-highlight"), {
      target: { value: "second distinct" },
    });
    fireEvent.click(screen.getByTestId("fdr-spawn"));
    await waitFor(() => {
      const boxes = screen.getAllByRole("checkbox");
      expect(boxes.length).toBeGreaterThanOrEqual(2);
    });
    const boxes = screen.getAllByRole("checkbox");
    fireEvent.click(boxes[0]);
    fireEvent.click(boxes[1]);
    // mark completed so pack accepts open|completed
    const completeBtns = screen.getAllByText(/Mark completed/);
    fireEvent.click(completeBtns[0]);
    fireEvent.click(completeBtns[1]);
    fireEvent.click(screen.getByTestId("fdr-collective"));
    await waitFor(() => {
      expect(screen.getByTestId("fdr-pack-intent").textContent).toMatch(
        /collective_pack/,
      );
      expect(screen.getByTestId("fdr-pack-intent").textContent).toMatch(
        /dispatched=false/,
      );
    });
  });
});
