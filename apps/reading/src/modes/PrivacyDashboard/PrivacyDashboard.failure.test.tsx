/**
 * FFX SPR-03 (F-07): /privacy rendered "GET /trust-center failed: HTTP n"
 * (and the toggle/deletion actions rendered their raw strings in the same
 * banner). The deletion-ledger "unknown" state is kept exactly as it was.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import PrivacyDashboard from "./index";

const TRUST = {
  differential_privacy_epsilon_budgets: { skill_invocation_frequency: 2 },
  deletion_sla_days: 30,
  substrate_controls: ["encryption at rest"],
  compliance_frameworks: ["GDPR"],
  loop_3_unlock_status: {},
};
const SURFACES = {
  surfaces: [
    {
      surface_name: "skill_invocation_frequency",
      sensitivity: "low",
      epsilon_per_day: 2,
      opt_in_required: false,
      description: "Which skills fire.",
      enabled: true,
      default_enabled: true,
    },
  ],
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

function expectHonest(text: string) {
  expect(text).not.toMatch(/\b[45]\d\d\b/);
  expect(text).not.toMatch(/\/[a-z-]+/);
  expect(text).not.toContain("Failed to fetch");
  expect(text).not.toContain("HTTP");
  expect(text).not.toContain("API");
}

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status });

/** Route by path so Promise.all ordering does not matter. */
function routeFetch(trust: () => Promise<Response>) {
  fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.endsWith("/trust-center")) return trust();
    if (url.endsWith("/trust-center/deletion-requests")) return json({ requests: [] });
    if (url.endsWith("/settings/privacy")) return json(SURFACES);
    return json({ detail: "unexpected" }, 404);
  });
}

describe("PrivacyDashboard — honest failure", () => {
  it("a 503 on /trust-center shows plain copy and Try again reloads", async () => {
    let calls = 0;
    routeFetch(async () => (++calls === 1 ? json({ detail: "x" }, 503) : json(TRUST)));
    render(<PrivacyDashboard />);
    const alert = await screen.findByRole("alert");
    expectHonest(alert.textContent ?? "");
    expect(alert.textContent).toContain("Couldn't load your privacy settings.");
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText(/substrate-wide daily ε total/)).toBeTruthy();
    await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
    expect(calls).toBe(2);
  });

  it("a network TypeError never shows 'Failed to fetch'", async () => {
    routeFetch(async () => {
      throw new TypeError("Failed to fetch");
    });
    render(<PrivacyDashboard />);
    const alert = await screen.findByRole("alert");
    expectHonest(alert.textContent ?? "");
  });

  it("a failed toggle save shows plain copy, not the settings API status", async () => {
    routeFetch(async () => json(TRUST));
    const base = fetchMock.getMockImplementation()!;
    fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      if (String(input).endsWith("/settings/privacy") && init?.method === "PUT") {
        return json({ detail: "x" }, 500);
      }
      return base(input, init);
    });
    render(<PrivacyDashboard />);
    const toggle = await screen.findByRole("switch", { name: /skill invocation frequency/i });
    await userEvent.click(toggle);
    const alert = await screen.findByRole("alert");
    expectHonest(alert.textContent ?? "");
    expect(alert.textContent).toContain("Couldn't save that privacy setting.");
  });
});
