import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import {
  calculateExpeditionPlan,
  ExpeditionCostPlanner,
  sanitizeNonNegative,
} from "./index";

afterEach(cleanup);

describe("Expedition Cost Planner", () => {
  it("sanitizes non-finite and negative inputs without inventing value", () => {
    expect(sanitizeNonNegative(-1)).toBe(0);
    expect(sanitizeNonNegative(Number.NaN)).toBe(0);
    expect(sanitizeNonNegative(Number.POSITIVE_INFINITY)).toBe(0);
    expect(sanitizeNonNegative(2.5)).toBe(2.5);
  });

  it("applies the independent policy-example arithmetic above the allowance", () => {
    const plan = calculateExpeditionPlan(2_000_000, 8_000_000, 10);
    expect(plan.publicTokensWithinAllowance).toBe(5_000_000);
    expect(plan.publicTokensAboveAllowance).toBe(3_000_000);
    expect(plan.privateRaw).toBe(20);
    expect(plan.privateMargin).toBe(10);
    expect(plan.publicRaw).toBe(30);
    expect(plan.publicMargin).toBe(3);
    expect(plan.estimatedTotal).toBe(63);
  });

  it("charges no illustrative public cost below or exactly at the allowance", () => {
    expect(calculateExpeditionPlan(0, 4_999_999, 100).estimatedTotal).toBe(0);
    expect(calculateExpeditionPlan(0, 5_000_000, 100).estimatedTotal).toBe(0);
  });

  it("clamps huge finite inputs instead of overflowing and displaying false zero", () => {
    const plan = calculateExpeditionPlan(
      Number.MAX_VALUE,
      Number.MAX_VALUE,
      Number.MAX_VALUE,
    );
    expect(plan.privateTokens).toBe(50_000_000);
    expect(plan.publicTokens).toBe(50_000_000);
    expect(plan.assumedRatePerMillion).toBe(100);
    expect(Number.isFinite(plan.estimatedTotal)).toBe(true);
    expect(plan.estimatedTotal).toBeGreaterThan(0);
  });

  it("uses labelled native controls and recomputes from the operator's assumed rate", () => {
    render(
      <ExpeditionCostPlanner
        initialPrivateTokens={1_000_000}
        initialRatePerMillion={5}
      />,
    );
    expect(screen.getByText("$7.50")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Your assumed provider rate"), {
      target: { value: "12" },
    });
    expect(screen.getByText("$18.00")).toBeTruthy();
    const status = screen.getByRole("status");
    expect(status.getAttribute("aria-atomic")).toBe("true");
    expect(status.textContent).toMatch(/Estimated planning total\$18\.00/);
    expect(status.textContent).not.toMatch(/Private raw cost|fineprint/i);
  });

  it("keeps policy, estimate, and absent live authority explicit", () => {
    const { container } = render(<ExpeditionCostPlanner />);
    const copy = container.textContent ?? "";
    expect(copy).toMatch(/Policy example, not active billing/i);
    expect(copy).toMatch(/Illustrative monthly estimate/i);
    expect(copy).toMatch(/not a quote or an invoice/i);
    expect(copy).not.toMatch(
      /DeepSeek|Claude|Opus|auto-converts|master-spec|checkout|due now/i,
    );
  });

  it("composes under the shell's main without nesting another main", () => {
    const { container } = render(
      <main>
        <ExpeditionCostPlanner />
      </main>,
    );
    expect(container.querySelectorAll("main")).toHaveLength(1);
    expect(container.querySelector("main > .expedition-planner")?.tagName).toBe(
      "DIV",
    );
  });

  it("keeps the generated environment decorative and pointer-inert", () => {
    const { container } = render(<ExpeditionCostPlanner />);
    const image = container.querySelector("img")!;
    expect(image.getAttribute("alt")).toBe("");
    expect(image.getAttribute("aria-hidden")).toBe("true");
    expect(image.getAttribute("draggable")).toBe("false");
  });
});
