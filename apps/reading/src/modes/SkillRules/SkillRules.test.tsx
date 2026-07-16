import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { SkillRulesView, type SkillRule, type SkillRuleFilters } from "./index";

const rule: SkillRule = {
  rule_id: "skill-1",
  rule_text: "Triangulate claims before assigning a date.",
  rule_kind: "source_tier_rule",
  domain: "Semiconductors",
  epsilon_budget_consumed: 0.0125,
  source_user_count: 8,
  confidence: "high",
  extracted_at: "2026-06-14T11:20:00Z",
};
const filters: SkillRuleFilters = { query: "", domain: "", confidence: "" };
const renderView = (
  props: Partial<React.ComponentProps<typeof SkillRulesView>> = {},
) => {
  const handlers = {
    onFiltersChange: vi.fn(),
    onApply: vi.fn(),
    onClear: vi.fn(),
    onRetry: vi.fn(),
  };
  render(
    <MemoryRouter>
      <SkillRulesView
        rules={[rule]}
        filters={filters}
        {...handlers}
        {...props}
      />
    </MemoryRouter>,
  );
  return handlers;
};
afterEach(cleanup);

describe("SkillRulesView", () => {
  it("states the limits of confidence, contributor count, and epsilon", () => {
    renderView();
    expect(screen.getByText(/not a probability/i)).toBeTruthy();
    expect(screen.getByText(/not a quality score/i)).toBeTruthy();
  });
  it("labels summary counts as current-query results rather than substrate totals", () => {
    renderView();
    const summary = screen
      .getByRole("heading", { name: "Visible promoted rules" })
      .closest("section")!;
    expect(within(summary).getByText(/current server query/i)).toBeTruthy();
    expect(
      within(summary).getByText(/not totals for the whole substrate/i),
    ).toBeTruthy();
  });
  it("renders rule provenance semantically and keeps links addressable", () => {
    renderView();
    expect(
      screen
        .getByRole("link", { name: /Triangulate claims/ })
        .getAttribute("href"),
    ).toBe("/skill-rules/skill-1");
    expect(screen.getByText("8")).toBeTruthy();
    expect(screen.getByText("ε 0.0125")).toBeTruthy();
    expect(screen.getByText("source tier rule")).toBeTruthy();
  });
  it("distinguishes no promotions from no filtered matches", () => {
    const { rerender } = render(
      <MemoryRouter>
        <SkillRulesView
          rules={[]}
          filters={filters}
          onFiltersChange={() => undefined}
          onApply={() => undefined}
          onClear={() => undefined}
        />
      </MemoryRouter>,
    );
    expect(
      screen.getByRole("heading", {
        name: "No rules have cleared promotion yet",
      }),
    ).toBeTruthy();
    rerender(
      <MemoryRouter>
        <SkillRulesView
          rules={[]}
          filters={{ ...filters, query: "x" }}
          filtersApplied
          onFiltersChange={() => undefined}
          onApply={() => undefined}
          onClear={() => undefined}
        />
      </MemoryRouter>,
    );
    expect(
      screen.getByRole("heading", {
        name: "No promoted rules match this query",
      }),
    ).toBeTruthy();
    expect(
      screen.getByText(/does not mean the substrate has no promoted rules/i),
    ).toBeTruthy();
  });
  it("submits filters explicitly instead of treating keystrokes as completed queries", () => {
    const handlers = renderView();
    fireEvent.change(screen.getByLabelText("Search rule text"), {
      target: { value: "triangulate" },
    });
    expect(handlers.onFiltersChange).toHaveBeenCalledWith({
      ...filters,
      query: "triangulate",
    });
    expect(handlers.onApply).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: /Apply query/ }));
    expect(handlers.onApply).toHaveBeenCalledOnce();
  });
  it("exposes clear only for applied filters", () => {
    const handlers = renderView({ filtersApplied: true });
    fireEvent.click(screen.getByRole("button", { name: "Clear filters" }));
    expect(handlers.onClear).toHaveBeenCalledOnce();
  });
  it.each([
    ["loading", "Checking the shared substrate…"],
    ["error", "The conservatory could not be opened"],
  ] as const)("renders the %s state", (state, heading) => {
    renderView({ rules: [], state });
    expect(screen.getByRole("heading", { name: heading })).toBeTruthy();
  });
  it("offers bounded fallbacks for non-finite measured metadata", () => {
    renderView({
      rules: [
        {
          ...rule,
          source_user_count: Number.NaN,
          epsilon_budget_consumed: Number.NaN,
        },
      ],
    });
    expect(screen.getAllByText("Not reported").length).toBeGreaterThanOrEqual(
      2,
    );
    expect(document.body.textContent).not.toContain("NaN");
  });
  it("rejects negative measurements and malformed timestamps", () => {
    renderView({
      rules: [
        {
          ...rule,
          source_user_count: -2,
          epsilon_budget_consumed: -0.1,
          extracted_at: "not-a-date",
        },
      ],
    });
    expect(screen.getAllByText("Not reported").length).toBeGreaterThanOrEqual(
      2,
    );
    expect(screen.getByText("Time not reported")).toBeTruthy();
    expect(document.body.textContent).not.toContain("not-a-date");
  });
  it("drops malformed array members instead of dereferencing them", () => {
    renderView({ rules: [null, {}, rule] as unknown as SkillRule[] });
    expect(
      screen.getByRole("link", { name: /Triangulate claims/ }),
    ).toBeTruthy();
    expect(
      screen.getByRole("heading", { name: "Visible promoted rules" })
        .parentElement?.parentElement?.textContent,
    ).toContain("1");
  });
});
