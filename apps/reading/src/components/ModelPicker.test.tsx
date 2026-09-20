/**
 * ModelPicker — honest-state tests (plain vitest assertions; the repo does
 * not install jest-dom matchers).
 */

import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

afterEach(cleanup);

import ModelPicker from "./ModelPicker";
import type { ComposerCandidateView } from "../api/composerProjection";

const CANDIDATES: ComposerCandidateView[] = [
  {
    rank: 1,
    tier: "fast",
    provider: "deepseek",
    model: "deepseek-v4-flash",
    quality_score: 0.8,
    quality_basis: "measured",
    eligible: true,
    pricing_status: "known",
    estimated_usd_low: 0.02,
    estimated_usd_high: 0.05,
  },
  {
    rank: 2,
    tier: "deep",
    provider: "deepseek",
    model: "deepseek-v4-pro",
    quality_score: 0.92,
    quality_basis: "static_prior",
    eligible: true,
    pricing_status: "unknown",
    estimated_usd_low: null,
    estimated_usd_high: null,
  },
  {
    rank: 3,
    tier: "deep",
    provider: "hermes",
    model: "hermes-pro",
    quality_score: 0.9,
    quality_basis: "measured",
    eligible: false,
    pricing_status: "known",
    estimated_usd_low: 0.1,
    estimated_usd_high: 0.2,
  },
];

function triggerText(): string {
  const btn = screen.getByRole("button", { name: /choose model driver/i });
  return btn.textContent ?? "";
}

describe("ModelPicker", () => {
  it("renders the trigger with auto default and the advisory note", () => {
    render(<ModelPicker candidates={CANDIDATES} selected={null} onSelect={() => {}} />);
    expect(triggerText()).toContain("Auto (best available)");
    const note = screen.getByText(/advisory — the server re-validates/i);
    expect(note).toBeTruthy();
  });

  it("shows an explicit loading state", () => {
    render(<ModelPicker candidates={null} selected={null} onSelect={() => {}} loading />);
    expect(screen.getByRole("status").textContent).toContain("Loading model drivers");
  });

  it("shows an honest error state with the reason", () => {
    render(
      <ModelPicker candidates={null} selected={null} onSelect={() => {}} error="composer down" />,
    );
    expect(screen.getByRole("alert").textContent).toContain(
      "Model drivers unavailable · composer down",
    );
  });

  it("shows a named empty state when no candidates", () => {
    render(<ModelPicker candidates={[]} selected={null} onSelect={() => {}} />);
    expect(screen.getByText(/no model drivers available for this action/i)).toBeTruthy();
  });

  it("renders candidates with honest pricing (unknown for null, ineligible badge)", () => {
    render(<ModelPicker candidates={CANDIDATES} selected={null} onSelect={() => {}} />);
    fireEvent.click(screen.getByRole("button", { name: /choose model driver/i }));
    const flash = screen.getByRole("option", { name: /deepseek-v4-flash/i });
    expect(flash.textContent).toContain("measured");
    expect(flash.textContent).toContain("$0.02");
    const pro = screen.getByRole("option", { name: /deepseek-v4-pro/i });
    expect(pro.textContent).toContain("pricing unknown");
    const hermes = screen.getByRole("option", { name: /hermes-pro/i });
    expect(hermes.textContent).toContain("ineligible");
  });

  it("selects a candidate and reports it up", () => {
    const onSelect = vi.fn();
    render(<ModelPicker candidates={CANDIDATES} selected={null} onSelect={onSelect} />);
    fireEvent.click(screen.getByRole("button", { name: /choose model driver/i }));
    fireEvent.click(screen.getByRole("option", { name: /deepseek-v4-pro/i }));
    expect(onSelect).toHaveBeenCalledWith(CANDIDATES[1]);
    expect(screen.queryByRole("option")).toBeNull();
  });

  it("shows the selected candidate on the trigger", () => {
    render(
      <ModelPicker
        candidates={CANDIDATES}
        selected={{ provider: "deepseek", model: "deepseek-v4-flash" }}
        onSelect={() => {}}
      />,
    );
    expect(triggerText()).toContain("deepseek / deepseek-v4-flash");
    expect(triggerText()).toContain("$0.02");
  });
});
