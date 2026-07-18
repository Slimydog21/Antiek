/**
 * CostMeter.test.tsx — living-TV densify + pure budget beat policy.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

import type { SessionCost } from "../../api/research";
import CostMeter, { costMeterWernerBeat } from "./CostMeter";

afterEach(() => {
  cleanup();
});

function cost(over: Partial<SessionCost> = {}): SessionCost {
  return {
    per_research: {},
    session_total_usd: 1.25,
    aggregate_spent_usd: 1.25,
    aggregate_cap_usd: 10,
    ...over,
  };
}

describe("costMeterWernerBeat", () => {
  it("returns fail at/over cap, highlight near warn fraction, else null", () => {
    expect(costMeterWernerBeat({ spent: 5, cap: 5 })).toBe("fail");
    expect(costMeterWernerBeat({ spent: 6, cap: 5 })).toBe("fail");
    expect(costMeterWernerBeat({ spent: 4, cap: 5 })).toBe("highlight");
    expect(costMeterWernerBeat({ spent: 1, cap: 5 })).toBeNull();
    expect(costMeterWernerBeat({ spent: 1, cap: 0 })).toBeNull();
  });
});

describe("CostMeter brand densify", () => {
  it("renders session thinking brand on awaiting and active meter", () => {
    const { rerender } = render(<CostMeter cost={null} />);
    expect(screen.getByTestId("cost-meter-werner-brand")).toBeTruthy();
    expect(screen.getByTestId("cost-meter-awaiting")).toBeTruthy();

    rerender(<CostMeter cost={cost()} />);
    expect(screen.getByTestId("cost-meter")).toBeTruthy();
    expect(screen.getByTestId("cost-meter-werner-brand")).toBeTruthy();
    expect(screen.getByTestId("cost-meter").getAttribute("data-at-cap")).toBe(
      "false",
    );
  });

  it("marks data-at-cap when spend hits the ceiling", () => {
    render(
      <CostMeter
        cost={cost({ aggregate_spent_usd: 10, aggregate_cap_usd: 10 })}
      />,
    );
    expect(screen.getByTestId("cost-meter").getAttribute("data-at-cap")).toBe(
      "true",
    );
  });
});
