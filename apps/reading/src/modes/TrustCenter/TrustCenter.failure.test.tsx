/**
 * FFX SPR-03 (P-01 client half, F-07): a failed /trust-center read must never
 * put a status, a path or "Failed to fetch" on the page. The public /trust
 * page showed a raw "Failed to fetch" to every logged-out visitor.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";

import TrustCenter from "./index";

const TRUST = {
  differential_privacy_epsilon_budgets: { skill_invocation_frequency: 2 },
  deletion_sla_days: 30,
  substrate_controls: ["encryption at rest"],
  compliance_frameworks: ["GDPR"],
  loop_3_unlock_status: {},
};

const fetchMock = vi.fn();

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

/** The `what` passed to describeFailure is plain words, so the title is
 *  "Couldn't <what>." and not the "That didn't work." fallback (#3538). */
function expectPlainTitle(text: string) {
  expect(text).toMatch(/^Couldn't [a-z][a-z ']*\./i);
}

function expectHonest(text: string) {
  expect(text).not.toMatch(/\b[45]\d\d\b/);
  expect(text).not.toMatch(/\/[a-z-]+/);
  expect(text).not.toContain("Failed to fetch");
  expect(text).not.toContain("HTTP");
}

function renderPage() {
  return render(
    <MemoryRouter>
      <TrustCenter />
    </MemoryRouter>,
  );
}

describe("TrustCenter — honest failure", () => {
  it("a 503 shows plain copy, no status and no path, and Try again reloads", async () => {
    fetchMock
      .mockResolvedValueOnce(new Response(JSON.stringify({ detail: "x" }), { status: 503 }))
      .mockResolvedValueOnce(new Response(JSON.stringify(TRUST), { status: 200 }));
    renderPage();
    const alert = await screen.findByRole("alert");
    expectHonest(alert.textContent ?? "");
    expectPlainTitle(alert.textContent ?? "");
    expect(alert.textContent).toContain("Couldn't load the Trust Center.");
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(String(fetchMock.mock.calls[1][0])).toBe(String(fetchMock.mock.calls[0][0]));
    expect(await screen.findByText("GDPR")).toBeTruthy();
  });

  it("a network TypeError (the logged-out CORS case) never shows 'Failed to fetch'", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
    renderPage();
    const alert = await screen.findByRole("alert");
    expectHonest(alert.textContent ?? "");
    expectPlainTitle(alert.textContent ?? "");
    expectHonest(document.body.textContent ?? "");
    expect(screen.getByRole("button", { name: "Try again" })).toBeTruthy();
  });
});
