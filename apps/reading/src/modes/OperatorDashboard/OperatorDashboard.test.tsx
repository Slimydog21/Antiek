import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }));

vi.mock("../../lib/api", async (orig) => ({
  ...(await orig<typeof import("../../lib/api")>()),
  apiFetch: apiFetchMock,
}));

import OperatorDashboard from "./index";

function response(body: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as unknown as Response;
}

type Route = "/publishers" | "/stats" | "/trust-center/deletion-requests" | "/payouts/transfers";
type Answer = () => Promise<Response>;

/** Answer each dashboard request by path; anything unrouted rejects. */
function routeFetch(answers: Partial<Record<Route, Answer>>) {
  apiFetchMock.mockImplementation((input: RequestInfo | URL) => {
    const path = String(input).split("?")[0] as Route;
    const answer = answers[path];
    return answer ? answer() : Promise.reject(new TypeError("Failed to fetch"));
  });
}

const ok = (body: unknown): Answer => () => Promise.resolve(response(body));
const status = (code: number): Answer => () => Promise.resolve(response({}, code));
const offline: Answer = () => Promise.reject(new TypeError("Failed to fetch"));

const publisher = {
  ip_holder_id: "iph-mit",
  display_name: "MIT Press",
  legal_contact_email: null,
  status: "pre_onboarded",
  escrow_balance_usd: "12.00",
  notification_sent_at: null,
  claimed_at: null,
  opted_out_at: null,
};

const STAT_LABELS = ["Investigations", "Notebooks", "Outcomes", "Skill rules", "Payouts", "IP holders"];

/** The number shown in a substrate-snapshot tile (value sits above its label). */
function statTile(label: string): string | null {
  return screen.getByText(label).previousElementSibling?.textContent ?? null;
}

/** The value shown in the pending-deletions tile (value sits below its label). */
function deletionsTile(): string | null {
  return screen.getByText("Pending deletion requests").nextElementSibling?.textContent ?? null;
}

function renderDashboard() {
  render(
    <MemoryRouter>
      <OperatorDashboard />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  apiFetchMock.mockReset();
});
afterEach(cleanup);

describe("OperatorDashboard — a failed request is an unknown", () => {
  it("while requests are pending, no tile states a count and no list is called empty", () => {
    apiFetchMock.mockReturnValue(new Promise<Response>(() => {}));
    renderDashboard();
    expect(deletionsTile()).toBe("…");
    for (const label of STAT_LABELS) expect(statTile(label)).toBe("…");
    expect(screen.queryByText("No transfers yet.")).toBeNull();
    expect(screen.queryByText("No publishers in this bucket.")).toBeNull();
  });

  it("failed snapshot requests show no zeros and no empty payouts; loaded publishers still show", async () => {
    // Rubric veto: the page printed "Pending deletion requests 0", six 0
    // tiles and "No transfers yet." after these requests had failed.
    routeFetch({
      "/publishers": ok({ publishers: [publisher] }),
      "/stats": offline,
      "/trust-center/deletion-requests": status(502),
      "/payouts/transfers": status(503),
    });
    renderDashboard();

    expect(await screen.findByText("Transfers didn't load.")).toBeTruthy();
    expect(screen.queryByText("No transfers yet.")).toBeNull();

    expect(deletionsTile()).toBe("—");
    expect(screen.getByText("Deletion requests didn't load.")).toBeTruthy();

    for (const label of STAT_LABELS) expect(statTile(label)).toBe("—");
    expect(screen.getByText("Substrate counts didn't load.")).toBeTruthy();

    // The request that answered is not blanked by the ones that failed.
    expect(screen.getByText("MIT Press")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Mark notified" })).toBeTruthy();

    expect(screen.getByText("Part of this dashboard didn't load.")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Try again" })).toBeTruthy();
    expect(document.body.textContent).not.toMatch(/Failed to fetch|HTTP \d/);
  });

  it("a failed publishers request claims no empty buckets and blanks nothing else", async () => {
    routeFetch({
      "/publishers": offline,
      "/stats": ok({ counts: { investigations: 7, notebooks: 3 }, warnings: [] }),
      "/trust-center/deletion-requests": ok({
        requests: [
          { request_id: "d1", status: "pending", requested_at: "2026-09-01" },
          { request_id: "d2", status: "pending", requested_at: "2026-09-02" },
          { request_id: "d3", status: "completed", requested_at: "2026-09-03" },
        ],
      }),
      "/payouts/transfers": ok({
        transfers: [{ status: "skipped_escrow", amount_usd_cents: 1234, initiated_at: null }],
      }),
    });
    renderDashboard();

    expect(await screen.findByText("Publishers didn't load.")).toBeTruthy();
    expect(screen.queryByText("No publishers in this bucket.")).toBeNull();

    expect(statTile("Investigations")).toBe("7");
    expect(statTile("Notebooks")).toBe("3");
    // /stats answered but did not report this table: unknown, not zero.
    expect(statTile("Outcomes")).toBe("—");
    expect(deletionsTile()).toContain("2");
    expect(screen.getByText("$12.34")).toBeTruthy();
    expect(screen.queryByText("Transfers didn't load.")).toBeNull();
  });

  it("Try again reloads every request and shows what answered", async () => {
    routeFetch({});
    renderDashboard();
    expect(await screen.findByText("Transfers didn't load.")).toBeTruthy();

    routeFetch({
      "/publishers": ok({ publishers: [] }),
      "/stats": ok({ counts: { investigations: 0 }, warnings: [] }),
      "/trust-center/deletion-requests": ok({ requests: [] }),
      "/payouts/transfers": ok({ transfers: [] }),
    });
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));

    // Now the empties and zeros are real answers, so they may be stated.
    expect(await screen.findByText("No transfers yet.")).toBeTruthy();
    expect(deletionsTile()).toBe("0");
    expect(statTile("Investigations")).toBe("0");
    expect(screen.getAllByText("No publishers in this bucket.")).toHaveLength(4);
    expect(screen.queryByText("Part of this dashboard didn't load.")).toBeNull();
  });
});
