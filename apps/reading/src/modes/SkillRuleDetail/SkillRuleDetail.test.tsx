import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SkillRuleDetailView, type SkillRuleDetailRecord } from "./index";

const rule: SkillRuleDetailRecord = {
  rule_id: "skill-1",
  rule_text: "Triangulate claims before assigning a date.",
  rule_kind: "source_tier_rule",
  domain: "Semiconductors",
  epsilon_budget_consumed: 0.0125,
  source_user_count: 8,
  confidence: "moderate",
  extracted_at: "2026-06-14T11:20:00Z",
};
const view = (
  props: Partial<React.ComponentProps<typeof SkillRuleDetailView>> = {},
) => {
  const retry = vi.fn();
  render(
    <MemoryRouter>
      <SkillRuleDetailView
        ruleId="skill-1"
        rule={rule}
        state="ready"
        onRetry={retry}
        {...props}
      />
    </MemoryRouter>,
  );
  return retry;
};
afterEach(cleanup);

describe("SkillRuleDetailView", () => {
  it("presents the rule as a promoted heuristic rather than universal truth", () => {
    view();
    expect(screen.getByText(/not a universal-truth certificate/i)).toBeTruthy();
    expect(screen.getByText(/universally true or optimal/i)).toBeTruthy();
  });
  it("bounds confidence, contributor support, and epsilon semantics", () => {
    view();
    expect(
      screen.getByText(/stored confidence label—not a probability/i),
    ).toBeTruthy();
    expect(screen.getByText(/privacy spend, not rule quality/i)).toBeTruthy();
    const metadata = screen
      .getByRole("heading", { name: "Measured metadata" })
      .closest("section")!;
    expect(within(metadata).getByText("8")).toBeTruthy();
    expect(within(metadata).getByText("ε 0.0125")).toBeTruthy();
  });
  it("states the privacy boundary without exposing contributor identity", () => {
    view();
    expect(screen.getByText(/Who contributed/)).toBeTruthy();
    expect(screen.getByText(/private source material contained/i)).toBeTruthy();
    expect(document.body.textContent).not.toContain("user_id");
  });
  it("preserves the content-addressed identifier and navigation", () => {
    view();
    expect(screen.getByText("skill-1")).toBeTruthy();
    expect(
      screen
        .getByRole("link", { name: /Skill Rule Conservatory/ })
        .getAttribute("href"),
    ).toBe("/skill-rules");
  });
  it.each([
    ["loading", "Opening the specimen record…"],
    ["not-found", "This promoted rule was not found"],
    ["error", "The specimen record could not be opened"],
  ] as const)("renders the %s state", (state, heading) => {
    view({ rule: null, state });
    expect(screen.getByRole("heading", { name: heading })).toBeTruthy();
  });
  it("retries only after a safe failure", () => {
    const retry = view({ rule: null, state: "error" });
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(retry).toHaveBeenCalledOnce();
  });
  it("bounds malformed records and measured fields", () => {
    view({ rule: {} as SkillRuleDetailRecord });
    expect(
      screen.getByRole("heading", { name: "Rule data is unavailable" }),
    ).toBeTruthy();
    cleanup();
    view({
      rule: {
        ...rule,
        source_user_count: -1,
        epsilon_budget_consumed: Number.NaN,
        extracted_at: "not-a-date",
      },
    });
    expect(screen.getAllByText("Not reported").length).toBeGreaterThanOrEqual(
      2,
    );
    expect(screen.getByText("Time not reported")).toBeTruthy();
    expect(document.body.textContent).not.toContain("NaN");
    expect(document.body.textContent).not.toContain("not-a-date");
  });
});
