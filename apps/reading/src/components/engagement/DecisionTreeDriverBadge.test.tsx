import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DecisionTreeDriverBadge } from "./DecisionTreeDriverBadge";

const fetchDecisionTreeSelection = vi.fn();

vi.mock("../../api/settings", () => ({
  fetchDecisionTreeSelection: (...args: unknown[]) =>
    fetchDecisionTreeSelection(...args),
}));

describe("DecisionTreeDriverBadge residual cw", () => {
  afterEach(() => cleanup());
  beforeEach(() => {
    fetchDecisionTreeSelection.mockReset();
  });

  it("shows installed driver", async () => {
    fetchDecisionTreeSelection.mockResolvedValue({
      model_id: "glm-5.2",
      provider_id: "zai",
      installed: true,
      notes: [],
      source: "test",
    });
    render(<DecisionTreeDriverBadge />);
    await waitFor(() => {
      expect(screen.getByTestId("decision-tree-driver-active").textContent).toMatch(
        /zai\s*\/\s*glm-5\.2/,
      );
    });
  });

  it("shows none when not installed", async () => {
    fetchDecisionTreeSelection.mockResolvedValue({
      model_id: null,
      provider_id: null,
      installed: false,
      notes: [],
      source: "test",
    });
    render(<DecisionTreeDriverBadge />);
    await waitFor(() => {
      expect(screen.getByTestId("decision-tree-driver-none").textContent).toMatch(
        /none/,
      );
    });
  });
});
