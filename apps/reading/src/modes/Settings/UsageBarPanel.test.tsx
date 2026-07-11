import { afterEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import UsageBarPanel from "./UsageBarPanel";
import type { UsageBarProjectResponse } from "../../api/usageBar";

afterEach(() => {
  cleanup();
});

function makeResult(
  overrides: Partial<UsageBarProjectResponse> = {},
): UsageBarProjectResponse {
  return {
    usage_bar: {
      daily_cap_usd: null,
      spent_usd: null,
      remaining_usd: null,
      over_budget: null,
      fraction_used: null,
      spend_basis: "reserved_estimate",
      notes: [],
    },
    ...overrides,
  };
}

describe("UsageBarPanel", () => {
  it("shows remaining as unknown when null (not $0)", async () => {
    const projectFn = vi.fn(async () => makeResult());
    render(<UsageBarPanel projectFn={projectFn} />);
    fireEvent.click(screen.getByTestId("usage-bar-project"));
    await waitFor(() => {
      expect(screen.getByTestId("usage-bar-remaining").textContent).toMatch(
        /unknown/i,
      );
    });
    expect(screen.getByTestId("usage-bar-remaining").textContent).not.toMatch(
      /\$0\.0000/,
    );
  });

  it("renders would_exceed true from projection", async () => {
    const projectFn = vi.fn(async () =>
      makeResult({
        usage_bar: {
          daily_cap_usd: 1,
          spent_usd: 0.5,
          remaining_usd: 0.5,
          over_budget: false,
          fraction_used: 0.5,
          spend_basis: "reserved_estimate",
          notes: [],
        },
        prompt_projection: {
          projected_cost_usd_low: 0.4,
          projected_cost_usd_high: 0.6,
          remaining_before_usd: 0.5,
          remaining_after_high_usd: -0.1,
          would_exceed: true,
          notes: [],
        },
      }),
    );
    render(
      <UsageBarPanel
        projectFn={projectFn}
        initialCap={1}
        initialSpent={0.5}
        initialProjectionHigh={0.6}
      />,
    );
    fireEvent.click(screen.getByTestId("usage-bar-project"));
    await waitFor(() => {
      expect(screen.getByTestId("usage-bar-would-exceed").textContent).toMatch(
        /exceed/i,
      );
    });
  });

  it("renders would_exceed null as unknown", async () => {
    const projectFn = vi.fn(async () =>
      makeResult({
        prompt_projection: {
          projected_cost_usd_low: 0.1,
          projected_cost_usd_high: 0.2,
          remaining_before_usd: null,
          remaining_after_high_usd: null,
          would_exceed: null,
          notes: [],
        },
      }),
    );
    render(<UsageBarPanel projectFn={projectFn} />);
    fireEvent.click(screen.getByTestId("usage-bar-project"));
    await waitFor(() => {
      expect(screen.getByTestId("usage-bar-would-exceed").textContent).toMatch(
        /unknown/i,
      );
    });
  });

  it("shows error when projectFn throws", async () => {
    const projectFn = vi.fn(async () => {
      throw new Error("backend down");
    });
    render(<UsageBarPanel projectFn={projectFn} />);
    fireEvent.click(screen.getByTestId("usage-bar-project"));
    await waitFor(() => {
      expect(screen.getByTestId("usage-bar-error").textContent).toMatch(
        /backend down/,
      );
    });
  });
});
