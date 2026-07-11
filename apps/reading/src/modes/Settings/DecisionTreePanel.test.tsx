/**
 * DecisionTreePanel — offline render + honesty of remaining / would_exceed.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import DecisionTreePanel from "./DecisionTreePanel";
import type { DecisionTreeRankResponse } from "../../api/modelDecision";

afterEach(() => {
  cleanup();
});

function makeResult(
  overrides: Partial<DecisionTreeRankResponse> = {},
): DecisionTreeRankResponse {
  return {
    task: "deep_research",
    authority: "advisory",
    recommended_model_id: "reasoning-default",
    remaining_usd: null,
    prompt_chars: 4000,
    notes: ["authority=advisory"],
    ranked: [
      {
        model_id: "reasoning-default",
        provider: "house",
        tier: "reasoning",
        score: 1,
        rationale: "static tier affinity",
        projected_cost_usd_low: 0.1,
        projected_cost_usd_high: 0.2,
        would_exceed: null,
      },
    ],
    ...overrides,
  };
}

describe("DecisionTreePanel", () => {
  it("shows remaining as unknown when empty (not $0)", () => {
    render(<DecisionTreePanel rankFn={async () => makeResult()} />);
    const rem = screen.getByTestId("decision-tree-remaining-display");
    expect(rem.textContent).toMatch(/unknown/i);
    expect(rem.textContent).not.toMatch(/\$0\.0000/);
  });

  it("ranks via injectable fn and shows would_exceed null as unknown", async () => {
    const rankFn = vi.fn(async () =>
      makeResult({
        remaining_usd: null,
        ranked: [
          {
            model_id: "m1",
            provider: "p",
            tier: "flash",
            score: 0.9,
            rationale: "x",
            projected_cost_usd_low: 0.01,
            projected_cost_usd_high: 0.02,
            would_exceed: null,
          },
        ],
      }),
    );
    render(<DecisionTreePanel rankFn={rankFn} />);
    fireEvent.click(screen.getByTestId("decision-tree-rank"));
    await waitFor(() => {
      expect(screen.getByTestId("decision-tree-result")).toBeTruthy();
    });
    expect(rankFn).toHaveBeenCalled();
    expect(screen.getByTestId("decision-tree-authority").textContent).toMatch(
      /advisory/i,
    );
    expect(screen.getByTestId("would-exceed-m1").textContent).toMatch(/unknown/i);
    expect(screen.getByTestId("decision-tree-result-remaining").textContent).toMatch(
      /unknown/i,
    );
  });

  it("renders would_exceed true when ranker says so", async () => {
    const rankFn = vi.fn(async () =>
      makeResult({
        remaining_usd: 0.01,
        ranked: [
          {
            model_id: "pricey",
            provider: "p",
            tier: "reasoning",
            score: 1,
            rationale: "high",
            projected_cost_usd_low: 1,
            projected_cost_usd_high: 2,
            would_exceed: true,
          },
        ],
        recommended_model_id: "pricey",
      }),
    );
    render(
      <DecisionTreePanel rankFn={rankFn} initialRemainingUsd={0.01} />,
    );
    fireEvent.click(screen.getByTestId("decision-tree-rank"));
    await waitFor(() => {
      expect(screen.getByTestId("would-exceed-pricey").textContent).toMatch(
        /exceed/i,
      );
    });
  });

  it("shows error when ranker throws", async () => {
    const rankFn = vi.fn(async () => {
      throw new Error("backend down");
    });
    render(<DecisionTreePanel rankFn={rankFn} />);
    fireEvent.click(screen.getByTestId("decision-tree-rank"));
    await waitFor(() => {
      expect(screen.getByTestId("decision-tree-error").textContent).toMatch(
        /backend down/,
      );
    });
  });
});
