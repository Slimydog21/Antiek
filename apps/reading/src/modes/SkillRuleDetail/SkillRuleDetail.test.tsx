import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import SkillRuleDetail from "./index";

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
    status: 200,
    json: async () => ({
      rule_id: "rule-bad",
      rule_text: "Malformed detail rule",
      rule_kind: "routing",
      domain: "research",
      epsilon_budget_consumed: Number.POSITIVE_INFINITY,
      source_user_count: Number.NaN,
      confidence: "high",
      extracted_at: null,
    }),
  });
});

afterEach(() => cleanup());

describe("SkillRuleDetail", () => {
  it("sanitizes malformed epsilon and contributor counts", async () => {
    render(
      <MemoryRouter initialEntries={["/skill-rules/rule-bad"]}>
        <Routes>
          <Route path="/skill-rules/:ruleId" element={<SkillRuleDetail />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByText("Malformed detail rule")).toBeTruthy();
    expect(document.body.textContent).not.toMatch(/NaN|Infinity/);
    expect(screen.getByText("0")).toBeTruthy();
    expect(screen.getByText("0.0000")).toBeTruthy();
  });
});
