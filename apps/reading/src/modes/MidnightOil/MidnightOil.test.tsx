import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import MidnightOil from "./index";
import { preflightMidnightOil } from "../../api/midnightOil";

vi.mock("../../api/midnightOil", () => ({
  preflightMidnightOil: vi.fn(async () => ({
    accepted: true,
    denial_reason: null,
    run_id: "midnight-oil-test",
    goal: "Explain widebody engine bottlenecks.",
    work_minutes: 90,
    price_ceiling_usd: 12,
    route_mode: "auto_cost",
    source_policy: ["arxiv", "substack", "operator_corpus"],
    deliverable: "html_research_asset",
    role_plans: [
      {
        role: "planner",
        budget_usd: 1.8,
        max_minutes: 13,
        route_mode: "auto_cost",
        route_receipt_required: true,
        source_receipts_required: true,
        planned_route_receipt_id: "midnight-oil-test-planner-route-receipt",
      },
      {
        role: "gatherer",
        budget_usd: 5.4,
        max_minutes: 45,
        route_mode: "auto_cost",
        route_receipt_required: true,
        source_receipts_required: true,
        planned_route_receipt_id: "midnight-oil-test-gatherer-route-receipt",
      },
    ],
    artifact_contract: {
      final_format: "html",
      pdf_allowed: false,
      antiek_information_asset: true,
      twin_note_document_required: true,
      route_receipt_links_required: true,
      source_receipt_links_required: true,
    },
    notes: ["preflight only: no agents launched, no budget reserved, no retrieval performed"],
  })),
}));

describe("MidnightOil", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => cleanup());

  it("submits a no-launch autonomous research preflight and renders the contract", async () => {
    const user = userEvent.setup();
    render(<MidnightOil />);

    await user.type(
      screen.getByRole("textbox", { name: /goal/i }),
      "Explain widebody engine bottlenecks.",
    );
    fireEvent.change(screen.getByLabelText(/work minutes/i), { target: { value: "90" } });
    fireEvent.change(screen.getByLabelText(/price ceiling usd/i), { target: { value: "12" } });
    await user.selectOptions(screen.getByLabelText(/route mode/i), "auto_cost");
    await user.click(screen.getByRole("checkbox", { name: "Web" }));
    await user.click(screen.getByLabelText(/I approve this ceiling/i));
    await user.click(screen.getByRole("button", { name: "Preflight" }));

    await waitFor(() => expect(preflightMidnightOil).toHaveBeenCalled());
    expect(preflightMidnightOil).toHaveBeenCalledWith({
      goal: "Explain widebody engine bottlenecks.",
      work_minutes: 90,
      price_ceiling_usd: 12,
      route_mode: "auto_cost",
      source_policy: ["arxiv", "substack", "operator_corpus", "web"],
      deliverable: "html_research_asset",
      operator_acknowledged_spend: true,
    });

    expect(screen.getByText("midnight-oil-test")).toBeTruthy();
    expect(screen.getByText("$7.20")).toBeTruthy();
    expect(screen.getByText("html")).toBeTruthy();
    expect(screen.getByText("Twin notes")).toBeTruthy();
    expect(screen.getByText(/no agents launched/i)).toBeTruthy();
  });
});
