import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { StrictMode } from "react";
import {
  cleanup,
  fireEvent,
  render as rtlRender,
  screen,
  waitFor,
} from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import OperatorDashboard from "./index";
import type { PublisherSummary } from "./index";

const { apiFetchMock } = vi.hoisted(() => ({ apiFetchMock: vi.fn() }));
vi.mock("../../lib/api", async (orig) => ({
  ...(await orig<typeof import("../../lib/api")>()),
  apiFetch: apiFetchMock,
}));
beforeEach(() => apiFetchMock.mockReset());
afterEach(cleanup);

function render(ui: React.ReactNode) {
  return rtlRender(<MemoryRouter>{ui}</MemoryRouter>);
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((r) => {
    resolve = r;
  });
  return { promise, resolve };
}
function response(body: unknown, ok = true) {
  return { ok, json: async () => body } as Response;
}

const PUBLISHERS: PublisherSummary[] = [
  {
    ip_holder_id: "ip-mit",
    display_name: "MIT Press",
    legal_contact_email: "permissions@mit.edu",
    status: "pre_onboarded",
    escrow_balance_usd: "0.00",
    notification_sent_at: null,
    claimed_at: null,
    opted_out_at: null,
  },
  {
    ip_holder_id: "ip-penguin",
    display_name: "Penguin",
    legal_contact_email: null,
    status: "invited",
    escrow_balance_usd: "87.60",
    notification_sent_at: "2026-06-01",
    claimed_at: null,
    opted_out_at: null,
  },
  {
    ip_holder_id: "ip-cambridge",
    display_name: "Cambridge University Press",
    legal_contact_email: null,
    status: "claimed",
    escrow_balance_usd: "22.00",
    notification_sent_at: "2026-05-15",
    claimed_at: "2026-06-10",
    opted_out_at: null,
  },
  {
    ip_holder_id: "ip-oup",
    display_name: "Oxford University Press",
    legal_contact_email: null,
    status: "opted_out",
    escrow_balance_usd: "0.00",
    notification_sent_at: "2026-05-20",
    claimed_at: null,
    opted_out_at: "2026-07-01",
  },
];

const STATS = {
  counts: { investigations: 100, notebooks: 10, outcomes: 5 },
  warnings: [],
};

function mockAll() {
  apiFetchMock.mockImplementation((url: string) => {
    if (url === "/publishers")
      return Promise.resolve(response({ publishers: PUBLISHERS }));
    if (url === "/stats") return Promise.resolve(response(STATS));
    if (url === "/trust-center/deletion-requests")
      return Promise.resolve(
        response({ requests: [{ status: "pending" }, { status: "resolved" }] }),
      );
    if (url === "/payouts/transfers?limit=5")
      return Promise.resolve(
        response({
          transfers: [
            { status: "completed", amount_usd_cents: 1240, initiated_at: "2026-07-01" },
          ],
        }),
      );
    return Promise.resolve(response({}, false));
  });
}

/* ── M1 · typed state ──────────────────────────────────────────── */

describe("Operator Watch Room · M1 typed state", () => {
  it("renders Unknown for missing and non-finite stat keys", () => {
    render(
      <OperatorDashboard
        executionEnabled={false}
        initialPublishers={[]}
        initialSnapshot={{
          stats: {
            counts: { investigations: 99, documents: -1, chunks: Number.NaN },
            warnings: [],
          },
          pendingDeletions: 0,
          recentPayouts: [],
        }}
      />,
    );
    expect(screen.getByText("99")).toBeTruthy();
    expect(screen.getAllByText("Unknown").length).toBeGreaterThanOrEqual(3);
  });

  it("renders Unavailable label for each null optional instrument", () => {
    render(
      <OperatorDashboard
        executionEnabled={false}
        initialPublishers={[]}
        initialSnapshot={{ stats: null, pendingDeletions: null, recentPayouts: null }}
      />,
    );
    /* Availability component renders "Unavailable" for each null optional */
    const unavail = screen.getAllByText("Unavailable");
    expect(unavail.length).toBeGreaterThanOrEqual(3);
  });

  it("stats Unavailable does NOT affect deletions/payouts and vice versa", () => {
    render(
      <OperatorDashboard
        executionEnabled={false}
        initialPublishers={[]}
        initialSnapshot={{
          stats: { counts: { investigations: 42 }, warnings: [] },
          pendingDeletions: null,
          recentPayouts: null,
        }}
      />,
    );
    expect(screen.getByText("42")).toBeTruthy();
    const unavail = screen.getAllByText("Unavailable");
    expect(unavail.length).toBe(2);
  });
});

/* ── M2 · transport authority ──────────────────────────────────── */

describe("Operator Watch Room · M2 transport authority", () => {
  it("fires exact GET paths on mount", async () => {
    mockAll();
    render(<OperatorDashboard />);
    await screen.findByText(/Keep watch/);
    expect(apiFetchMock).toHaveBeenCalledWith("/publishers");
    expect(apiFetchMock).toHaveBeenCalledWith("/stats");
    expect(apiFetchMock).toHaveBeenCalledWith("/trust-center/deletion-requests");
    expect(apiFetchMock).toHaveBeenCalledWith("/payouts/transfers?limit=5");
  });

  it("fires exact POST path with encoding and JSON content type", async () => {
    const notifyDeferred = deferred<Response>();
    apiFetchMock.mockImplementation((url: string, init?: RequestInit) => {
      if (url === "/publishers")
        return Promise.resolve(
          response({ publishers: [{ ...PUBLISHERS[0], ip_holder_id: "ip/with/slashes" }] }),
        );
      if (url === "/stats") return Promise.resolve(response(STATS));
      if (url === "/trust-center/deletion-requests")
        return Promise.resolve(response({ requests: [] }));
      if (url === "/payouts/transfers?limit=5")
        return Promise.resolve(response({ transfers: [] }));
      if (
        url === `/publishers/${encodeURIComponent("ip/with/slashes")}/notify` &&
        init?.method === "POST"
      )
        return notifyDeferred.promise;
      return Promise.resolve(response({}));
    });
    render(<OperatorDashboard />);
    await screen.findByText("Record external notice");
    const button = screen.getByText("Record external notice");
    fireEvent.click(button);
    await waitFor(() =>
      expect(apiFetchMock).toHaveBeenCalledWith(
        "/publishers/ip%2Fwith%2Fslashes/notify",
        expect.objectContaining({
          method: "POST",
          headers: expect.objectContaining({ "Content-Type": "application/json" }),
        }),
      ),
    );
  });

  it("renders safe error copy without transport internals", async () => {
    apiFetchMock.mockImplementation((url: string) => {
      if (url === "/publishers") return Promise.resolve(response({}, false));
      return Promise.resolve(response({}));
    });
    render(<OperatorDashboard />);
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("could not be refreshed");
    expect(document.body.textContent).not.toContain("HTTP");
    expect(document.body.textContent).not.toContain("/publishers");
    expect(document.body.textContent).not.toContain("500");
  });

  it("treats each optional failure independently", async () => {
    apiFetchMock.mockImplementation((url: string) => {
      if (url === "/publishers")
        return Promise.resolve(response({ publishers: PUBLISHERS }));
      if (url === "/stats") return Promise.resolve(response({}, false));
      if (url === "/trust-center/deletion-requests")
        return Promise.resolve(response({}, false));
      if (url === "/payouts/transfers?limit=5")
        return Promise.resolve(
          response({ transfers: [{ status: "completed", amount_usd_cents: 500, initiated_at: null }] }),
        );
      return Promise.resolve(response({}));
    });
    render(<OperatorDashboard />);
    await screen.findByText(/Keep watch/);
    expect(screen.getAllByText("Unavailable").length).toBe(2);
    expect(screen.getByText("completed")).toBeTruthy();
    expect(screen.getByText("MIT Press")).toBeTruthy();
  });
});

/* ── M3 · single-flight receipt ────────────────────────────────── */

describe("Operator Watch Room · M3 single-flight receipt", () => {
  it("disables only the targeted publisher row during notify", async () => {
    const notifyDeferred = deferred<Response>();
    apiFetchMock.mockImplementation((url: string, init?: RequestInit) => {
      if (url === "/publishers" && !init)
        return Promise.resolve(response({ publishers: PUBLISHERS }));
      if (url === "/stats") return Promise.resolve(response(STATS));
      if (url === "/trust-center/deletion-requests")
        return Promise.resolve(response({ requests: [] }));
      if (url === "/payouts/transfers?limit=5")
        return Promise.resolve(response({ transfers: [] }));
      if (typeof url === "string" && url.includes("/notify") && init?.method === "POST")
        return notifyDeferred.promise;
      return Promise.resolve(response({}));
    });
    render(<OperatorDashboard />);
    await screen.findByText("Record external notice");
    const button = screen.getByText("Record external notice");
    fireEvent.click(button);
    expect(button.textContent).toBe("Recording…");
    expect(button.hasAttribute("disabled")).toBe(true);
  });

  it("issues exactly one POST per click (no double-fire)", async () => {
    let postCount = 0;
    apiFetchMock.mockImplementation((url: string, init?: RequestInit) => {
      if (url === "/publishers" && !init)
        return Promise.resolve(response({ publishers: PUBLISHERS }));
      if (url === "/stats") return Promise.resolve(response(STATS));
      if (url === "/trust-center/deletion-requests")
        return Promise.resolve(response({ requests: [] }));
      if (url === "/payouts/transfers?limit=5")
        return Promise.resolve(response({ transfers: [] }));
      if (typeof url === "string" && url.includes("/notify") && init?.method === "POST") {
        postCount++;
        return Promise.resolve(response({}));
      }
      return Promise.resolve(response({}));
    });
    render(<OperatorDashboard />);
    await screen.findByText("Record external notice");
    const button = screen.getByText("Record external notice");
    fireEvent.click(button);
    fireEvent.click(button);
    fireEvent.click(button);
    await waitFor(() => expect(postCount).toBe(1));
  });
});

/* ── M4 · watch room authoring ─────────────────────────────────── */

describe("Operator Watch Room · M4 authoring", () => {
  it("renders the decorative environment image pointer-inert", async () => {
    mockAll();
    const { container } = render(<OperatorDashboard />);
    await screen.findByText(/Keep watch/);
    const img = container.querySelector(".operator-watch-room__environment")!;
    expect(img.getAttribute("alt")).toBe("");
    expect(img.getAttribute("aria-hidden")).toBe("true");
    expect(img.getAttribute("draggable")).toBe("false");
  });

  it("renders four publisher buckets", async () => {
    mockAll();
    render(<OperatorDashboard />);
    await screen.findByText("Pre-onboarded");
    expect(screen.getByText("Invited")).toBeTruthy();
    expect(screen.getByText("Claimed")).toBeTruthy();
    expect(screen.getByText("Opted out")).toBeTruthy();
  });

  it("labels the action as recording not sending", async () => {
    mockAll();
    render(<OperatorDashboard />);
    await screen.findByText("Record external notice");
    expect(screen.queryByText(/Mark notified|Send notification/i)).toBeNull();
  });

  it("states the non-goal boundary callout", async () => {
    mockAll();
    render(<OperatorDashboard />);
    await screen.findByText(/does not send email/);
  });

  it("shows Review link when pending deletions > 0", async () => {
    apiFetchMock.mockImplementation((url: string) => {
      if (url === "/publishers")
        return Promise.resolve(response({ publishers: [] }));
      if (url === "/stats") return Promise.resolve(response(STATS));
      if (url === "/trust-center/deletion-requests")
        return Promise.resolve(
          response({ requests: [{ status: "pending" }, { status: "pending" }] }),
        );
      if (url === "/payouts/transfers?limit=5")
        return Promise.resolve(response({ transfers: [] }));
      return Promise.resolve(response({}));
    });
    render(<OperatorDashboard />);
    await screen.findByText("Review privacy queue →");
  });
});

/* ── M5 · deterministic state matrix ──────────────────────────── */

describe("Operator Watch Room · M5 deterministic state matrix", () => {
  it("Loading state: publisher roster loading; optional instruments do not masquerade as zero", () => {
    render(
      <OperatorDashboard
        executionEnabled={false}
        initialPublishers={null}
        initialSnapshot={{ stats: null, pendingDeletions: null, recentPayouts: null }}
        initialLoading={true}
      />,
    );
    expect(screen.getByText("Opening the publisher ledger…")).toBeTruthy();
    expect(screen.getAllByText("Unavailable").length).toBeGreaterThanOrEqual(3);
  });

  it("Empty state: authoritative empty list is distinct from load failure", () => {
    render(
      <OperatorDashboard
        executionEnabled={false}
        initialPublishers={[]}
        initialSnapshot={{
          stats: { counts: {}, warnings: [] },
          pendingDeletions: 0,
          recentPayouts: [],
        }}
      />,
    );
    expect(screen.getAllByText("No records in this state.").length).toBe(4);
    expect(screen.getByText("No transfer records returned.")).toBeTruthy();
    expect(screen.queryByText("Unavailable")).toBeNull();
  });

  it("Notifying state: only the chosen publisher action is disabled", () => {
    render(
      <OperatorDashboard
        executionEnabled={false}
        initialPublishers={PUBLISHERS.filter((p) => p.status === "pre_onboarded")}
        initialSnapshot={EMPTY_SNAPSHOT}
        initialNotifyingId="ip-mit"
      />,
    );
    const btn = screen.getByText("Recording…");
    expect(btn.hasAttribute("disabled")).toBe(true);
  });

  it("Night mode: decorative image structure is correct", () => {
    mockAll();
    const { container } = render(<OperatorDashboard />);
    const img = container.querySelector(".operator-watch-room__environment");
    expect(img).toBeTruthy();
    const veil = container.querySelector(".operator-watch-room__veil");
    expect(veil).toBeTruthy();
  });
});

const EMPTY_SNAPSHOT = { stats: null, pendingDeletions: null, recentPayouts: null };

/* ── M6 · StrictMode stale suppression ─────────────────────────── */

describe("Operator Watch Room · M6 StrictMode stale suppression", () => {
  it("suppresses an older StrictMode request after the newer completes", async () => {
    const first = deferred<Response>();
    const second = deferred<Response>();
    let call = 0;
    apiFetchMock.mockImplementation((url: string) => {
      if (url === "/publishers") {
        call++;
        return call === 1 ? first.promise : second.promise;
      }
      return Promise.resolve(response({}));
    });
    render(
      <StrictMode>
        <OperatorDashboard />
      </StrictMode>,
    );
    second.resolve(
      response({ publishers: [{ ...PUBLISHERS[0], display_name: "Second" }] }),
    );
    await waitFor(() => expect(screen.getByText("Second")).toBeTruthy());
    first.resolve(
      response({ publishers: [{ ...PUBLISHERS[0], display_name: "Stale" }] }),
    );
    await waitFor(() => expect(screen.queryByText("Stale")).toBeNull());
  });
});

describe("Operator Watch Room · hostile payload and concurrency proof", () => {
  it("rejects malformed required publisher rows instead of fabricating an empty roster", async () => {
    apiFetchMock.mockImplementation((url: string) => Promise.resolve(
      url === "/publishers"
        ? response({ publishers: [{ ...PUBLISHERS[0], legal_contact_email: {} }] })
        : response({}, false),
    ));
    render(<OperatorDashboard />);
    expect((await screen.findByRole("alert")).textContent).toContain("watch room");
    expect(screen.getByText("The publisher roster is unavailable.")).toBeTruthy();
  });

  it("isolates malformed payout rows as unavailable", async () => {
    apiFetchMock.mockImplementation((url: string) => {
      if (url === "/publishers") return Promise.resolve(response({ publishers: PUBLISHERS }));
      if (url === "/stats") return Promise.resolve(response(STATS));
      if (url === "/trust-center/deletion-requests") return Promise.resolve(response({ requests: [] }));
      return Promise.resolve(response({ transfers: [{}] }));
    });
    render(<OperatorDashboard />);
    await screen.findByText("MIT Press");
    expect(screen.getAllByText("Unavailable").length).toBe(1);
  });

  it("keeps two different publisher IDs visibly pending at the same time", async () => {
    const first = deferred<Response>();
    const second = deferred<Response>();
    const actionable = [PUBLISHERS[0], { ...PUBLISHERS[0], ip_holder_id: "ip-princeton", display_name: "Princeton University Press" }];
    apiFetchMock.mockImplementation((url: string, init?: RequestInit) => {
      if (url === "/publishers") return Promise.resolve(response({ publishers: actionable }));
      if (url === "/stats") return Promise.resolve(response(STATS));
      if (url === "/trust-center/deletion-requests") return Promise.resolve(response({ requests: [] }));
      if (url === "/payouts/transfers?limit=5") return Promise.resolve(response({ transfers: [] }));
      if (url === "/publishers/ip-mit/notify" && init?.method === "POST") return first.promise;
      if (url === "/publishers/ip-princeton/notify" && init?.method === "POST") return second.promise;
      return Promise.resolve(response({}));
    });
    render(<OperatorDashboard />);
    const buttons = await screen.findAllByRole("button", { name: "Record external notice" });
    fireEvent.click(buttons[0]);
    fireEvent.click(buttons[1]);
    const pending = screen.getAllByRole("button", { name: "Recording…" });
    expect(pending).toHaveLength(2);
    expect(pending.every((button) => button.hasAttribute("disabled"))).toBe(true);
  });

  it("reloads and applies authoritative publisher state after a successful POST", async () => {
    let publisherGets = 0;
    apiFetchMock.mockImplementation((url: string, init?: RequestInit) => {
      if (url === "/publishers") {
        publisherGets += 1;
        const status = publisherGets === 1 ? "pre_onboarded" : "invited";
        return Promise.resolve(response({ publishers: [{ ...PUBLISHERS[0], status }] }));
      }
      if (url === "/stats") return Promise.resolve(response(STATS));
      if (url === "/trust-center/deletion-requests") return Promise.resolve(response({ requests: [] }));
      if (url === "/payouts/transfers?limit=5") return Promise.resolve(response({ transfers: [] }));
      if (url === "/publishers/ip-mit/notify" && init?.method === "POST") return Promise.resolve(response({}));
      return Promise.resolve(response({}, false));
    });
    render(<OperatorDashboard />);
    fireEvent.click(await screen.findByRole("button", { name: "Record external notice" }));
    await waitFor(() => expect(screen.queryByRole("button", { name: "Record external notice" })).toBeNull());
    expect(publisherGets).toBe(2);
  });

  it("keeps a successful receipt non-actionable when its follow-up refresh fails", async () => {
    let publisherGets = 0;
    apiFetchMock.mockImplementation((url: string, init?: RequestInit) => {
      if (url === "/publishers") {
        publisherGets += 1;
        return publisherGets === 1
          ? Promise.resolve(response({ publishers: [PUBLISHERS[0]] }))
          : Promise.resolve(response({}, false));
      }
      if (url === "/stats") return Promise.resolve(response(STATS));
      if (url === "/trust-center/deletion-requests") return Promise.resolve(response({ requests: [] }));
      if (url === "/payouts/transfers?limit=5") return Promise.resolve(response({ transfers: [] }));
      if (url === "/publishers/ip-mit/notify" && init?.method === "POST") {
        return Promise.resolve(response({ ...PUBLISHERS[0], status: "invited", notification_sent_at: "2026-07-16" }));
      }
      return Promise.resolve(response({}, false));
    });
    render(<OperatorDashboard />);
    fireEvent.click(await screen.findByRole("button", { name: "Record external notice" }));
    expect(await screen.findByText(/could not be refreshed/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Record external notice" })).toBeNull();
    expect(document.body.textContent).not.toContain("Nothing was changed");
  });
});
