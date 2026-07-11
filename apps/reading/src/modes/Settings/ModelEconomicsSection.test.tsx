import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

// Stub heavy child panels so this suite tests composition only.
vi.mock("./DecisionTreePanel", () => ({
  default: () => <div data-testid="decision-tree-panel">DecisionTree</div>,
}));
vi.mock("./UsageBarPanel", () => ({
  default: () => <div data-testid="usage-bar-panel">UsageBar</div>,
}));
vi.mock("./AntiekBenchPanel", () => ({
  default: () => <div data-testid="antiek-bench-panel">AntiekBench</div>,
}));

import ModelEconomicsSection from "./ModelEconomicsSection";

afterEach(() => {
  cleanup();
});

describe("ModelEconomicsSection", () => {
  it("renders all three child panels by default", () => {
    render(<ModelEconomicsSection />);
    expect(screen.getByTestId("model-economics-section")).toBeTruthy();
    expect(screen.getByTestId("model-economics-decision-tree-slot")).toBeTruthy();
    expect(screen.getByTestId("model-economics-usage-bar-slot")).toBeTruthy();
    expect(screen.getByTestId("model-economics-bench-slot")).toBeTruthy();
    expect(screen.getByTestId("decision-tree-panel")).toBeTruthy();
    expect(screen.getByTestId("usage-bar-panel")).toBeTruthy();
    expect(screen.getByTestId("antiek-bench-panel")).toBeTruthy();
    expect(screen.getByTestId("model-economics-blurb").textContent).toMatch(
      /advisory/i,
    );
  });

  it("can hide individual panels", () => {
    render(
      <ModelEconomicsSection
        showDecisionTree={false}
        showUsageBar={true}
        showAntiekBench={false}
      />,
    );
    expect(screen.queryByTestId("model-economics-decision-tree-slot")).toBeNull();
    expect(screen.getByTestId("model-economics-usage-bar-slot")).toBeTruthy();
    expect(screen.queryByTestId("model-economics-bench-slot")).toBeNull();
  });

  it("respects custom title", () => {
    render(<ModelEconomicsSection title="My economics" />);
    expect(screen.getByTestId("model-economics-header").textContent).toMatch(
      /My economics/,
    );
  });
});
