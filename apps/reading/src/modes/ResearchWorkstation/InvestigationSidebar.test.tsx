import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

import type { InvestigationSummary } from "../../lib/api";
import InvestigationSidebar from "./InvestigationSidebar";

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
});
