import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import PriceCeilingPanel from "./PriceCeilingPanel";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("PriceCeilingPanel", () => {
  it("recommends via injectable recommendFn and shows advisory authority", () => {
    const recommendFn = vi.fn(() => ({
      hours: 2,
      goal_count: 2,
      recommended_ceiling_usd: 5.5,
      low_usd: 3,
      high_usd: 7,
      authority: "advisory" as const,
      notes: ["authority=advisory"],
    }));
    render(
      <PriceCeilingPanel
        recommendFn={recommendFn}
        initialHours={2}
        initialGoals="g1,g2"
      />,
    );
    fireEvent.click(screen.getByTestId("price-ceiling-recommend"));
    expect(recommendFn).toHaveBeenCalledWith({
      hours: 2,
      goals: ["g1", "g2"],
    });
    expect(screen.getByTestId("price-ceiling-authority").textContent).toMatch(
      /advisory/i,
    );
    expect(screen.getByTestId("price-ceiling-recommended").textContent).toMatch(
      /\$5\.5000/,
    );
  });

  it("surfaces recommend errors", () => {
    const recommendFn = vi.fn(() => {
      throw new Error("hours must be > 0");
    });
    render(<PriceCeilingPanel recommendFn={recommendFn} initialHours={0} />);
    fireEvent.click(screen.getByTestId("price-ceiling-recommend"));
    expect(screen.getByTestId("price-ceiling-error").textContent).toMatch(
      /hours must be > 0/,
    );
    expect(screen.queryByTestId("price-ceiling-result")).toBeNull();
  });
});
