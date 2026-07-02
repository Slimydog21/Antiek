import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";

import SkillRules from "./index";

const apiFetchMock = vi.hoisted(() => vi.fn());

vi.mock("../../lib/api", async (orig) => {
  const actual = await orig<typeof import("../../lib/api")>();
  return {
    ...actual,
    apiFetch: apiFetchMock,
  };
});

beforeEach(() => {
  apiFetchMock.mockReset();
  apiFetchMock.mockResolvedValue({
    ok: true,
    json: async () => ({
      rules: [
        {
          rule_id: " rule-bad ",
          rule_text: " Malformed budget rule ",
          rule_kind: " routing ",
          domain: " research ",
          epsilon_budget_consumed: Number.POSITIVE_INFINITY,
          source_user_count: Number.NaN,
          confidence: "unexpected",
          extracted_at: " 2026-06-01 ",
        },
        {
          rule_id: "rule-good",
          rule_text: "Measured budget rule",
          rule_kind: "writing",
          domain: "analysis",
          epsilon_budget_consumed: "1.23456",
          source_user_count: "4.7",
          confidence: "moderate",
          extracted_at: null,
        },
        {
          rule_id: " ",
          rule_text: "Skipped rule",
          confidence: "high",
        },
      ],
    }),
  });
});

afterEach(() => cleanup());

describe("SkillRules", () => {
  it("sanitizes malformed epsilon and contributor counts", async () => {
    render(
      <MemoryRouter>
        <SkillRules />
      </MemoryRouter>,
    );

    expect(await screen.findByText("Malformed budget rule")).toBeTruthy();
    expect(screen.getByText("Measured budget rule")).toBeTruthy();
    expect(document.body.textContent).not.toMatch(/NaN|Infinity|Skipped rule/);
    expect(screen.getByText(/research · routing · users=0 · ε=0\.0000/)).toBeTruthy();
    expect(screen.getByText(/users=4 · ε=1\.2346/)).toBeTruthy();
    expect(screen.getByText(/ε=0\.0000 · 2026-06-01/)).toBeTruthy();
    expect(screen.getAllByText("low").length).toBeGreaterThan(0);
  });
});
