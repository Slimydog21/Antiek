import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import CollectivePackPanel from "./CollectivePackPanel";
import type { CollectivePackResult } from "../../api/twinCollective";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const sample: CollectivePackResult = {
  instruction: "synthesize",
  twin_ids: ["t1", "t2"],
  parent_asset_ids: ["p1", "p2"],
  pack_text: "### Twin 1: t1\ninsights:\n- a\n### Twin 2: t2\nquestions:\n- q?",
  insight_count: 1,
  question_count: 1,
  notes: [],
};

describe("CollectivePackPanel", () => {
  it("builds pack via injectable packFn", async () => {
    const packFn = vi.fn(async () => sample);
    render(
      <CollectivePackPanel
        packFn={packFn}
        initialTwinIds="t1, t2"
        initialInstruction="synthesize"
      />,
    );
    fireEvent.click(screen.getByTestId("collective-pack-build"));
    await waitFor(() => {
      expect(screen.getByTestId("collective-pack-result")).toBeTruthy();
    });
    expect(packFn).toHaveBeenCalledWith({
      twin_ids: ["t1", "t2"],
      instruction: "synthesize",
    });
    expect(screen.getByTestId("collective-pack-text").textContent).toMatch(
      /Twin 1/,
    );
    expect(screen.getByTestId("collective-pack-parents").textContent).toMatch(
      /2 parents/,
    );
    expect(screen.getByTestId("collective-pack-instruction-echo").textContent).toMatch(
      /synthesize/,
    );
  });

  it("surfaces errors without rendering a pack result", async () => {
    const packFn = vi.fn(async () => {
      throw new Error("twin missing");
    });
    render(
      <CollectivePackPanel packFn={packFn} initialTwinIds="missing" />,
    );
    fireEvent.click(screen.getByTestId("collective-pack-build"));
    await waitFor(() => {
      expect(screen.getByTestId("collective-pack-error").textContent).toMatch(
        /twin missing/,
      );
    });
    expect(screen.queryByTestId("collective-pack-result")).toBeNull();
  });

  it("does not render result when pack_text validation fails", async () => {
    const packFn = vi.fn(async () => {
      throw new Error(
        "collective pack response rejected: pack_text must be non-empty",
      );
    });
    render(<CollectivePackPanel packFn={packFn} initialTwinIds="t1" />);
    fireEvent.click(screen.getByTestId("collective-pack-build"));
    await waitFor(() => {
      expect(screen.getByTestId("collective-pack-error").textContent).toMatch(
        /pack_text/,
      );
    });
    expect(screen.queryByTestId("collective-pack-result")).toBeNull();
  });

  it("rejects injectable resolving empty pack_text without rendering success", async () => {
    const packFn = vi.fn(async () => ({
      ...sample,
      pack_text: "   ",
    }));
    render(<CollectivePackPanel packFn={packFn} initialTwinIds="t1" />);
    fireEvent.click(screen.getByTestId("collective-pack-build"));
    await waitFor(() => {
      expect(screen.getByTestId("collective-pack-error").textContent).toMatch(
        /pack_text/,
      );
    });
    expect(screen.queryByTestId("collective-pack-result")).toBeNull();
  });
});
