import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

import type { InvestigationSummary } from "../../lib/api";
import InvestigationSidebar, { InvestigationSidebarTree } from "./InvestigationSidebar";
import { investigationSidebarStoryInvestigations } from "./InvestigationSidebar.stories";

const { listState } = vi.hoisted(() => ({
  listState: {
    current: {
      investigations: [] as InvestigationSummary[],
      loading: false,
      error: null as string | null,
      refetch: vi.fn(),
    },
  },
}));

vi.mock("../../hooks/useInvestigationList", () => ({
  useInvestigationList: () => listState.current,
}));

function inv(over: Partial<InvestigationSummary> & { investigation_id: string }): InvestigationSummary {
  const { investigation_id, ...rest } = over;
  return {
    investigation_id,
    question: "A question",
    status: "completed",
    started_at: null,
    completed_at: null,
    cost_usd_total: 0,
    parent_investigation_id: null,
    ...rest,
  };
}

function renderSidebar() {
  return render(
    <MemoryRouter>
      <InvestigationSidebar />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  listState.current = {
    investigations: [],
    loading: false,
    error: null,
    refetch: vi.fn(),
  };
});

afterEach(() => cleanup());

describe("InvestigationSidebar", () => {
  it("sanitizes malformed investigation costs", () => {
    listState.current.investigations = [
      inv({ investigation_id: "inv-valid", question: "Valid cost", cost_usd_total: 0.0123 }),
      inv({ investigation_id: "inv-nan", question: "Malformed cost A", cost_usd_total: Number.NaN }),
      inv({ investigation_id: "inv-inf", question: "Malformed cost B", cost_usd_total: Number.POSITIVE_INFINITY }),
      inv({ investigation_id: "inv-neg", question: "Malformed cost C", cost_usd_total: -1 }),
    ];

    renderSidebar();

    expect(screen.getByText("Valid cost")).toBeTruthy();
    expect(screen.getByText("$0.0123")).toBeTruthy();
    expect(screen.getAllByText("$0").length).toBeGreaterThanOrEqual(3);
    expect(document.body.textContent).not.toMatch(/NaN|Infinity|\$-/);
  });

  it("accepts numeric-string investigation costs", () => {
    listState.current.investigations = [
      inv({
        investigation_id: "inv-string",
        question: "String cost",
        cost_usd_total: "0.0123" as unknown as number,
      }),
    ];

    renderSidebar();

    expect(screen.getByText("String cost")).toBeTruthy();
    expect(screen.getByText("$0.0123")).toBeTruthy();
  });

  it("normalizes malformed row titles, statuses, and ids", () => {
    listState.current.investigations = [
      inv({
        investigation_id: " inv valid ",
        question: ["not text"] as unknown as string,
        status: "unexpected" as InvestigationSummary["status"],
      }),
      inv({
        investigation_id: " ",
        question: "Invisible broken row",
        status: "completed",
      }),
    ];

    renderSidebar();

    expect(screen.getByText("inv valid")).toBeTruthy();
    expect(screen.getByLabelText("unavailable")).toBeTruthy();
    expect(screen.queryByText("unexpected")).toBeNull();
    expect(screen.queryByText("Invisible broken row")).toBeNull();
    expect(screen.getByRole("link", { name: /inv valid/ }).getAttribute("href")).toBe(
      "/inv/inv%20valid",
    );
  });

  it("shows empty state when every summary id is invalid", () => {
    listState.current.investigations = [
      inv({
        investigation_id: " ",
        question: "Invisible broken row",
        status: "completed",
      }),
    ];

    renderSidebar();

    expect(screen.getByText(/No investigations yet/)).toBeTruthy();
    expect(screen.queryByText("Invisible broken row")).toBeNull();
  });
});

describe("InvestigationSidebar Storybook fixture", () => {
  it("renders deterministic nested investigations without the live list hook", () => {
    render(
      <MemoryRouter initialEntries={["/inv/inv-quote-grounding"]}>
        <InvestigationSidebarTree
          investigations={investigationSidebarStoryInvestigations}
          loading={false}
          error={null}
          refetch={vi.fn()}
          activeId="inv-quote-grounding"
        />
      </MemoryRouter>,
    );

    expect(screen.getByText(/book memory with live research/)).toBeTruthy();
    expect(screen.getByText(/retrieved quotes actually support/)).toBeTruthy();
    expect(screen.getByText(/strongest counterargument/)).toBeTruthy();
    expect(screen.getByRole("link", { name: /retrieved quotes actually support/ }).getAttribute("href")).toBe(
      "/inv/inv-quote-grounding",
    );
    expect(screen.queryByText(/No investigations yet/)).toBeNull();
  });
});
