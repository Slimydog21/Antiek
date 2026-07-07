import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";

import Multimedia from "./index";

afterEach(cleanup);

function reviewPlan() {
  render(<Multimedia />);
  fireEvent.click(screen.getByRole("button", { name: "Review plan" }));
}

describe("Multimedia workstation", () => {
  it("updates the estimated cost when the operator selects the cheapest route", () => {
    render(<Multimedia />);
    expect(screen.getByTestId("multimedia-estimated-cost").textContent).toBe("$40.50");

    fireEvent.click(screen.getByRole("button", { name: /Cheapest/ }));

    expect(screen.getByTestId("multimedia-estimated-cost").textContent).toBe("$22.28");
    expect(screen.getByText(/Local placeholders first/)).toBeTruthy();
  });

  it("reviews a plan before render approval and then opens playback", async () => {
    reviewPlan();

    expect(screen.getByTestId("multimedia-suggestions")).toBeTruthy();
    expect(screen.getByText(/Unsourced claim guard/)).toBeTruthy();
    expect(screen.queryByTestId("multimedia-player")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Approve render" }));

    expect(await screen.findByTestId("multimedia-player")).toBeTruthy();
    expect(screen.getByRole("status").textContent).toContain("Rendering dry-run package");
  });

  it("surfaces provider unavailable and lets the operator downgrade safely", () => {
    reviewPlan();
    fireEvent.click(screen.getByRole("button", { name: "Approve render" }));

    fireEvent.click(screen.getByRole("button", { name: "Sim provider down" }));

    expect(screen.getByRole("status").textContent).toContain("Krea provider unavailable");

    fireEvent.click(screen.getByRole("button", { name: "Use cheapest fallback" }));

    expect(screen.getByRole("status").textContent).toContain("Partial render available");
    expect(screen.getByTestId("multimedia-estimated-cost").textContent).toBe("$22.28");
  });

  it("surfaces an over-budget state with the same downgrade path", () => {
    reviewPlan();
    fireEvent.click(screen.getByRole("button", { name: "Approve render" }));

    fireEvent.click(screen.getByRole("button", { name: "Sim over budget" }));

    expect(screen.getByRole("status").textContent).toContain("Over budget");
    fireEvent.click(screen.getByRole("button", { name: "Use cheapest fallback" }));
    expect(screen.getByRole("status").textContent).toContain("Partial render available");
  });

  it("highlights the current transcript segment and source card when a chapter is inspected", () => {
    reviewPlan();
    fireEvent.click(screen.getByRole("button", { name: "Approve render" }));

    fireEvent.click(screen.getByRole("button", { name: /The engineering constraint stack/ }));

    const transcript = screen.getByTestId("multimedia-transcript");
    expect(within(transcript).getByText(/engines, wing structure, and fatigue testing/)).toBeTruthy();
    expect(screen.getByTestId("multimedia-source-detail").textContent).toContain(
      "engine and fatigue-testing sequence",
    );
  });
});
