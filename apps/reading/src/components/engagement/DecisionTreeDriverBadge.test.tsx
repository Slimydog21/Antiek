import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  budgetUsagePct,
  DecisionTreeDriverBadge,
} from "./DecisionTreeDriverBadge";

const fetchDecisionTreeSelection = vi.fn();
const fetchSettingsBudget = vi.fn();

vi.mock("../../api/settings", () => ({
  fetchDecisionTreeSelection: (...args: unknown[]) =>
    fetchDecisionTreeSelection(...args),
  fetchSettingsBudget: (...args: unknown[]) => fetchSettingsBudget(...args),
}));

describe("DecisionTreeDriverBadge residual cw/eq", () => {
  afterEach(() => cleanup());
  beforeEach(() => {
    fetchDecisionTreeSelection.mockReset();
    fetchSettingsBudget.mockReset();
    fetchSettingsBudget.mockResolvedValue({
      daily_cap_usd: 10,
      spent_usd: 2.5,
      remaining_usd: 7.5,
      spent_status: "known",
      cap_env: "ANTIEK_DAILY_BUDGET_USD",
      notes: [],
    });
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

  it("shows compact budget usage bar next to driver (eq)", async () => {
    fetchDecisionTreeSelection.mockResolvedValue({
      model_id: "claude-opus-4-8",
      provider_id: "anthropic",
      installed: true,
      notes: [],
      source: "test",
    });
    render(<DecisionTreeDriverBadge />);
    await waitFor(() => {
      expect(screen.getByTestId("decision-tree-budget-usage")).toBeTruthy();
    });
    expect(
      screen.getByTestId("decision-tree-budget-usage").getAttribute(
        "data-spent-status",
      ),
    ).toBe("known");
    expect(screen.getByTestId("decision-tree-budget-spent").textContent).toMatch(
      /\$2\.50/,
    );
    expect(screen.getByTestId("decision-tree-budget-cap").textContent).toMatch(
      /\$10\.00/,
    );
    expect(
      screen.getByTestId("decision-tree-budget-remaining").textContent,
    ).toMatch(/\$7\.50/);
    expect(screen.getByTestId("decision-tree-budget-bar-fill")).toBeTruthy();
    const track = screen.getByTestId("decision-tree-budget-bar-track");
    expect(track.getAttribute("aria-valuenow")).toBe("25");
  });

  it("budgetUsagePct is honest for unknown/no_cap", () => {
    expect(
      budgetUsagePct({
        daily_cap_usd: 10,
        spent_usd: null,
        remaining_usd: null,
        spent_status: "unknown",
        cap_env: null,
        notes: [],
      }),
    ).toBeNull();
    expect(
      budgetUsagePct({
        daily_cap_usd: 10,
        spent_usd: 5,
        remaining_usd: 5,
        spent_status: "known",
        cap_env: null,
        notes: [],
      }),
    ).toBe(50);
  });

  it("refresh re-fetches driver and budget (fd)", async () => {
    fetchDecisionTreeSelection
      .mockResolvedValueOnce({
        model_id: "glm-5.2",
        provider_id: "zai",
        installed: true,
        notes: [],
        source: "test",
      })
      .mockResolvedValueOnce({
        model_id: "claude-opus-4-8",
        provider_id: "anthropic",
        installed: true,
        notes: [],
        source: "test",
      });
    fetchSettingsBudget
      .mockResolvedValueOnce({
        daily_cap_usd: 10,
        spent_usd: 2.5,
        remaining_usd: 7.5,
        spent_status: "known",
        cap_env: null,
        notes: [],
      })
      .mockResolvedValueOnce({
        daily_cap_usd: 10,
        spent_usd: 4,
        remaining_usd: 6,
        spent_status: "known",
        cap_env: null,
        notes: [],
      });
    render(<DecisionTreeDriverBadge />);
    await waitFor(() => {
      expect(screen.getByTestId("decision-tree-driver-active").textContent).toMatch(
        /glm-5\.2/,
      );
    });
    expect(
      screen.getByTestId("decision-tree-driver-badge").getAttribute(
        "data-refresh-tick",
      ),
    ).toBe("0");
    fireEvent.click(screen.getByTestId("decision-tree-driver-refresh"));
    await waitFor(() => {
      expect(screen.getByTestId("decision-tree-driver-active").textContent).toMatch(
        /claude-opus-4-8/,
      );
    });
    expect(
      screen.getByTestId("decision-tree-driver-badge").getAttribute(
        "data-refresh-tick",
      ),
    ).toBe("1");
    expect(screen.getByTestId("decision-tree-budget-spent").textContent).toMatch(
      /\$4\.00/,
    );
    expect(fetchDecisionTreeSelection).toHaveBeenCalledTimes(2);
    expect(fetchSettingsBudget).toHaveBeenCalledTimes(2);
  });
});
