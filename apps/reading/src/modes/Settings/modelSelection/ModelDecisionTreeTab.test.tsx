import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { ModelDecisionTreeTab } from "./ModelDecisionTreeTab";

describe("ModelDecisionTreeTab", () => {
  afterEach(() => cleanup());

  it("renders advisory rankings and projects over-budget warning", () => {
    render(<ModelDecisionTreeTab />);
    expect(screen.getByTestId("model-decision-tree-tab")).toBeTruthy();
    expect(screen.getByTestId("model-decision-authority").textContent).toMatch(
      /advisory/,
    );
    expect(screen.getByTestId("model-decision-rankings").children.length).toBe(
      4,
    );

    // gpt-5.5 demo usage is 1800/2000 — large token estimate should exceed.
    fireEvent.click(screen.getByTestId("model-decision-pick-gpt-5.5"));
    const tokens = screen.getByTestId(
      "model-decision-tokens",
    ) as HTMLInputElement;
    // 200k tokens × 1.2¢/1k = 240¢; used 1800 + 240 = 2040 > limit 2000
    fireEvent.change(tokens, { target: { value: "200000" } });

    expect(screen.getByTestId("model-decision-would-exceed")).toBeTruthy();
    expect(screen.getByTestId("model-decision-budget-fill")).toBeTruthy();
  });

  it("shows unconfigured budget when limit is 0", () => {
    render(<ModelDecisionTreeTab />);
    fireEvent.click(screen.getByTestId("model-decision-pick-mimo-v2.5-pro"));
    expect(
      screen.getByTestId("model-decision-budget-unconfigured"),
    ).toBeTruthy();
  });

  it("hides NotDiamond chip when mode is disabled (default)", () => {
    render(<ModelDecisionTreeTab />);
    expect(screen.queryByTestId("model-decision-shadow-suggestion")).toBeNull();
  });

  it("shadow mode logs suggestion without Accept (no auto-binding)", () => {
    render(<ModelDecisionTreeTab notDiamondMode="shadow" />);
    const chip = screen.getByTestId("model-decision-shadow-suggestion");
    expect(chip.getAttribute("data-nd-mode")).toBe("shadow");
    expect(chip.getAttribute("data-shadow-model")).toBeTruthy();
    expect(screen.queryByTestId("model-decision-shadow-accept")).toBeNull();
  });

  it("advisory mode Accept pins selection without auto-binding", () => {
    render(<ModelDecisionTreeTab notDiamondMode="advisory" />);
    const chip = screen.getByTestId("model-decision-shadow-suggestion");
    expect(chip.getAttribute("data-shadow-model")).toBeTruthy();
    expect(screen.queryByTestId("model-decision-selected")).toBeNull();
    fireEvent.click(screen.getByTestId("model-decision-shadow-accept"));
    expect(screen.getByTestId("model-decision-selected").textContent).toMatch(
      /Selected driver/,
    );
  });
});
