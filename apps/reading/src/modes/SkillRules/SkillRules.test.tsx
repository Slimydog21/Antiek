import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }));

vi.mock("../../lib/api", async (orig) => ({
  ...(await orig<typeof import("../../lib/api")>()),
  apiFetch: apiFetchMock,
}));

import SkillRules from "./index";

function response(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as unknown as Response;
}

const CONFIDENCES = ["high", "moderate", "low"];

const rule = {
  rule_id: "rule-1",
  rule_text: "Prefer primary sources over press summaries",
  rule_kind: "source_preference",
  domain: "quantum",
  epsilon_budget_consumed: 0.25,
  source_user_count: 3,
  confidence: "high",
  extracted_at: null,
};

/** The count shown in a confidence tile (value sits above its label). */
function tileCount(confidence: string): string | null {
  return screen.getByText(`${confidence} confidence`).previousElementSibling?.textContent ?? null;
}

function renderRules() {
  render(
    <MemoryRouter>
      <SkillRules />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  apiFetchMock.mockReset();
});
afterEach(cleanup);

describe("SkillRules — a failed load is an unknown", () => {
  it("while the rules are loading, no tile states a count", () => {
    apiFetchMock.mockReturnValue(new Promise<Response>(() => {}));
    renderRules();
    for (const c of CONFIDENCES) expect(tileCount(c)).toBe("…");
    expect(screen.queryByText(/No promoted rules yet/)).toBeNull();
  });

  it("a failed load shows no counts and no 'no rules yet', and Try again loads the rules", async () => {
    // Rubric veto: three 0 tiles and "No promoted rules yet" under a raw
    // "GET /skill-rules failed: HTTP 404" banner.
    apiFetchMock
      .mockResolvedValueOnce(response({}, 404))
      .mockResolvedValueOnce(response({ rules: [rule] }));
    renderRules();

    const failure = await screen.findByText("Skill rules didn't load.");
    expect(failure.getAttribute("title")).toContain("HTTP 404");
    for (const c of CONFIDENCES) expect(tileCount(c)).toBe("—");
    expect(screen.queryByText(/No promoted rules yet/)).toBeNull();
    expect(document.body.textContent).not.toContain("HTTP 404");

    fireEvent.click(screen.getByRole("button", { name: "Try again" }));

    expect(await screen.findByText(rule.rule_text)).toBeTruthy();
    expect(tileCount("high")).toBe("1");
    expect(tileCount("low")).toBe("0");
    expect(screen.queryByText("Skill rules didn't load.")).toBeNull();
  });

  it("a failed reload after a filter change drops the previous rules and counts", async () => {
    apiFetchMock
      .mockResolvedValueOnce(response({ rules: [rule] }))
      .mockRejectedValueOnce(new TypeError("Failed to fetch"));
    renderRules();
    expect(await screen.findByText(rule.rule_text)).toBeTruthy();

    fireEvent.change(screen.getByRole("combobox"), { target: { value: "low" } });

    expect(await screen.findByText("Skill rules didn't load.")).toBeTruthy();
    for (const c of CONFIDENCES) expect(tileCount(c)).toBe("—");
    expect(screen.queryByText(rule.rule_text)).toBeNull();
    expect(screen.queryByText(/No promoted rules yet/)).toBeNull();
  });
});
