/**
 * FFX SPR-03 (F-09): the three snapshot reads were `.catch(() => null)` and
 * rendered as 0 counts, "0" pending deletion requests and "No transfers
 * yet." A failed read must say it failed and show "—", never a zero.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";

import OperatorDashboard from "./index";

const STATS = {
  counts: { investigations: 7, notebooks: 3, outcomes: 2, skill_rules: 1, payout_transfers: 4, ip_holders: 5 },
  warnings: [],
};
const DELETIONS = { requests: [{ request_id: "dr-1", status: "pending", requested_at: "2026-09-27" }] };
const PAYOUTS = { transfers: [{ status: "held_in_escrow", amount_usd_cents: 1234, initiated_at: null }] };
const PUBLISHERS = { publishers: [] };

type Outcome = "ok" | 503 | "network";
const fetchMock = vi.fn();

function route(o: { stats?: Outcome; deletions?: Outcome; payouts?: Outcome; publishers?: Outcome }) {
  const answer = (outcome: Outcome | undefined, body: unknown) => {
    if (outcome === "network") throw new TypeError("Failed to fetch");
    if (outcome === 503) return new Response(JSON.stringify({ detail: "x" }), { status: 503 });
    return new Response(JSON.stringify(body), { status: 200 });
  };
  fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
    const url = String(input);
    if (url.endsWith("/stats")) return answer(o.stats, STATS);
    if (url.endsWith("/trust-center/deletion-requests")) return answer(o.deletions, DELETIONS);
    if (url.includes("/payouts/transfers")) return answer(o.payouts, PAYOUTS);
    if (url.endsWith("/publishers")) return answer(o.publishers, PUBLISHERS);
    return new Response("{}", { status: 404 });
  });
}

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
}

function renderPage() {
  return render(
    <MemoryRouter>
      <OperatorDashboard />
    </MemoryRouter>,
  );
}

async function snapshotSection() {
  const heading = await screen.findByRole("heading", { name: "Substrate snapshot" });
  await waitFor(() => expect(screen.queryByText("Loading publishers…")).toBeNull());
  return heading.closest("section") as HTMLElement;
}

describe("OperatorDashboard — three-state reads", () => {
  it("/stats 503 alone: counts show — and the failure title; transfers and deletions still render", async () => {
    route({ stats: 503 });
    renderPage();
    const snap = await snapshotSection();
    expect(within(snap).queryAllByText("—")).toHaveLength(6);
    expect(within(snap).getByText("Couldn't load substrate counts.")).toBeTruthy();
    expect(within(snap).getByText("held in escrow")).toBeTruthy();
    expect(within(snap).getByText("$12.34")).toBeTruthy();
    expect(within(snap).getByText("1")).toBeTruthy();
    expectHonest(document.body.textContent ?? "");
  });

  it("all three 503: no 0 anywhere in the snapshot, no false 'No transfers yet', review link kept", async () => {
    route({ stats: 503, deletions: 503, payouts: 503 });
    renderPage();
    const snap = await snapshotSection();
    expect(snap.textContent).not.toMatch(/0/);
    expect(document.body.textContent).not.toContain("No transfers yet.");
    expect(within(snap).getByText("Couldn't load deletion requests.")).toBeTruthy();
    expect(within(snap).getByText("Couldn't load transfers.")).toBeTruthy();
    expect(within(snap).getByText("Couldn't load substrate counts.")).toBeTruthy();
    expect(within(snap).getByRole("link", { name: /review/ }).getAttribute("href")).toBe("/privacy");
    expectHonest(document.body.textContent ?? "");
  });

  it("a network TypeError on every read never shows 'Failed to fetch' and Try again reloads", async () => {
    route({ stats: "network", deletions: "network", payouts: "network", publishers: "network" });
    renderPage();
    const snap = await snapshotSection();
    await within(snap).findByText("Couldn't load transfers.");
    expectHonest(document.body.textContent ?? "");
    route({});
    await userEvent.click(screen.getAllByRole("button", { name: "Try again" })[0]);
    await waitFor(() => expect(within(snap).getByText("7")).toBeTruthy());
    expect(screen.queryByText("Couldn't load transfers.")).toBeNull();
  });

  it("a /publishers 503 is plain copy and does not blank the snapshot", async () => {
    route({ publishers: 503 });
    renderPage();
    const alert = await screen.findByRole("alert");
    expectHonest(alert.textContent ?? "");
    expect(alert.textContent).toContain("Couldn't load publishers.");
    const snap = await snapshotSection();
    await within(snap).findByText("7");
  });
});
