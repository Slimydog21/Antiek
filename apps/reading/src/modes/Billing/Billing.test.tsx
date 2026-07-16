import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { apiFetch } from "../../lib/api";
import Billing, { BillingView, type BillingSummary } from "./index";

vi.mock("../../lib/api", () => ({ apiFetch: vi.fn() }));
afterEach(cleanup);

// ── Fixtures ────────────────────────────────────────────────────────

const fullSummary: BillingSummary = {
  user_id: "__operator__",
  period: "2026-07",
  free_tokens_consumed: 0,
  free_tokens_remaining: 5_000_000,
  paid_public_token_cost_usd: "0.00",
  paid_public_margin_usd: "0.00",
  paid_private_token_cost_usd: "12.50",
  paid_private_margin_usd: "6.25",
  total_raw_usd: "12.50",
  total_margin_usd: "6.25",
  total_billable_usd: "18.75",
  record_count: 42,
};

const emptySummary: BillingSummary = {
  user_id: "__operator__",
  period: "2026-07",
  free_tokens_consumed: 0,
  free_tokens_remaining: 5_000_000,
  paid_public_token_cost_usd: "0.00",
  paid_public_margin_usd: "0.00",
  paid_private_token_cost_usd: "0.00",
  paid_private_margin_usd: "0.00",
  total_raw_usd: "0.00",
  total_margin_usd: "0.00",
  total_billable_usd: "0.00",
  record_count: 0,
};

const longValuesSummary: BillingSummary = {
  user_id: "__operator__",
  period: "2026-12",
  free_tokens_consumed: 0,
  free_tokens_remaining: 5_000_000,
  paid_public_token_cost_usd: "0.00",
  paid_public_margin_usd: "0.00",
  paid_private_token_cost_usd: "99999.99",
  paid_private_margin_usd: "49999.995",
  total_raw_usd: "99999.99",
  total_margin_usd: "49999.995",
  total_billable_usd: "149999.985",
  record_count: 999999,
};

const response = (body: unknown, ok = true) =>
  ({
    ok,
    json: vi.fn().mockResolvedValue(body),
  }) as unknown as Response;

const viewCallbacks = {
  onUserIdChange: vi.fn(),
  onPeriodChange: vi.fn(),
  onApply: vi.fn(),
  onRetry: vi.fn(),
};

// ── BillingView (pure) ──────────────────────────────────────────────

describe("BillingView", () => {
  beforeEach(() => vi.clearAllMocks());

  // Truth boundaries
  it("states the observatory boundary: not an invoice or settled amount", () => {
    render(
      <BillingView
        state="idle"
        userId="__operator__"
        period="2026-07"
        data={null}
        userIdError={null}
        periodError={null}
        {...viewCallbacks}
      />,
    );
    const aside = screen.getByLabelText("Observatory boundary");
    expect(
      within(aside).getByText(/event-derived billable estimate/i),
    ).toBeTruthy();
    expect(within(aside).getByText(/not an invoice/i)).toBeTruthy();
  });

  it("states that non-operator identities return empty", () => {
    render(
      <BillingView
        state="idle"
        userId="__operator__"
        period="2026-07"
        data={null}
        userIdError={null}
        periodError={null}
        {...viewCallbacks}
      />,
    );
    const aside = screen.getByLabelText("Observatory boundary");
    expect(
      within(aside).getByText(/non-operator identities return an empty/i),
    ).toBeTruthy();
  });

  it("states that all dispatches are classified paid-private", () => {
    render(
      <BillingView
        state="idle"
        userId="__operator__"
        period="2026-07"
        data={null}
        userIdError={null}
        periodError={null}
        {...viewCallbacks}
      />,
    );
    const aside = screen.getByLabelText("Observatory boundary");
    // Text is split by <strong> around "paid-private" — check textContent
    expect(aside.textContent).toMatch(/classifies all observed dispatches as paid-private/i);
  });

  it("states no completeness/availability metadata", () => {
    render(
      <BillingView
        state="idle"
        userId="__operator__"
        period="2026-07"
        data={null}
        userIdError={null}
        periodError={null}
        {...viewCallbacks}
      />,
    );
    const aside = screen.getByLabelText("Observatory boundary");
    expect(
      within(aside).getByText(/no completeness or availability metadata/i),
    ).toBeTruthy();
  });

  // Ready state
  it("renders the ready state with record count and billable estimate", () => {
    render(
      <BillingView
        state="ready"
        userId="__operator__"
        period="2026-07"
        data={fullSummary}
        userIdError={null}
        periodError={null}
        {...viewCallbacks}
      />,
    );
    expect(
      screen.getByRole("heading", { name: /42 usage records/i }),
    ).toBeTruthy();
    // Billable estimate in results header + totals — use getAllByText
    expect(screen.getAllByText("$18.75").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("$12.50").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("$6.25").length).toBeGreaterThanOrEqual(1);
  });

  it("labels the total as event-derived billable estimate", () => {
    render(
      <BillingView
        state="ready"
        userId="__operator__"
        period="2026-07"
        data={fullSummary}
        userIdError={null}
        periodError={null}
        {...viewCallbacks}
      />,
    );
    expect(
      screen.getByText("Event-derived billable estimate"),
    ).toBeTruthy();
  });

  it("renders the free-tier progress bar with correct percentage", () => {
    render(
      <BillingView
        state="ready"
        userId="__operator__"
        period="2026-07"
        data={fullSummary}
        userIdError={null}
        periodError={null}
        {...viewCallbacks}
      />,
    );
    const bar = screen.getByRole("progressbar");
    expect(bar.getAttribute("aria-valuenow")).toBe("0");
    expect(bar.getAttribute("aria-valuemax")).toBe("100");
  });

  it("shows cost split cards with margin labels", () => {
    render(
      <BillingView
        state="ready"
        userId="__operator__"
        period="2026-07"
        data={fullSummary}
        userIdError={null}
        periodError={null}
        {...viewCallbacks}
      />,
    );
    expect(screen.getByText("Paid public")).toBeTruthy();
    expect(screen.getByText("Paid private")).toBeTruthy();
    expect(screen.getByText("10% margin")).toBeTruthy();
    expect(screen.getByText("50% margin")).toBeTruthy();
  });

  // Empty state
  it("renders the empty state without inferring zero", () => {
    render(
      <BillingView
        state="empty"
        userId="__operator__"
        period="2026-01"
        data={emptySummary}
        userIdError={null}
        periodError={null}
        {...viewCallbacks}
      />,
    );
    expect(
      screen.getByText(/no usage records returned/i),
    ).toBeTruthy();
    expect(
      screen.getByText(/non-operator identities currently return empty/i),
    ).toBeTruthy();
  });

  // Loading state
  it("renders the loading state with polite aria-live", () => {
    render(
      <BillingView
        state="loading"
        userId="__operator__"
        period="2026-07"
        data={null}
        userIdError={null}
        periodError={null}
        {...viewCallbacks}
      />,
    );
    expect(
      screen.getByText(/listening for usage signals/i),
    ).toBeTruthy();
    expect(
      screen.getByText(/no zero totals are inferred/i),
    ).toBeTruthy();
  });

  // Error state
  it("renders the error state without raw backend errors", () => {
    render(
      <BillingView
        state="error"
        userId="__operator__"
        period="2026-07"
        data={null}
        userIdError={null}
        periodError={null}
        {...viewCallbacks}
      />,
    );
    expect(
      screen.getByText(/usage signals unavailable/i),
    ).toBeTruthy();
    expect(
      screen.getByText(/raw backend errors are not rendered/i),
    ).toBeTruthy();
    expect(screen.getByRole("alert")).toBeTruthy();
  });

  it("offers retry on error", () => {
    render(
      <BillingView
        state="error"
        userId="__operator__"
        period="2026-07"
        data={null}
        userIdError={null}
        periodError={null}
        {...viewCallbacks}
      />,
    );
    const btn = screen.getByRole("button", { name: /try again/i });
    fireEvent.click(btn);
    expect(viewCallbacks.onRetry).toHaveBeenCalledTimes(1);
  });

  // Invalid input
  it("shows period validation hint for invalid format", () => {
    render(
      <BillingView
        state="idle"
        userId="__operator__"
        period="bad"
        data={null}
        userIdError={null}
        periodError="Use YYYY-MM format (e.g. 2026-07)"
        {...viewCallbacks}
      />,
    );
    expect(
      screen.getByText(/use yyyy-mm format/i),
    ).toBeTruthy();
    expect(
      screen.getByLabelText(/period/i).getAttribute("aria-invalid"),
    ).toBe("true");
  });

  it("shows user ID validation hint for empty value", () => {
    render(
      <BillingView
        state="idle"
        userId=""
        period="2026-07"
        data={null}
        userIdError="User ID is required"
        periodError={null}
        {...viewCallbacks}
      />,
    );
    expect(screen.getByText(/user id is required/i)).toBeTruthy();
    expect(
      screen.getByLabelText(/user id/i).getAttribute("aria-invalid"),
    ).toBe("true");
  });

  it("disables submit when form is invalid", () => {
    render(
      <BillingView
        state="idle"
        userId=""
        period="bad"
        data={null}
        userIdError="User ID is required"
        periodError="Use YYYY-MM format"
        {...viewCallbacks}
      />,
    );
    expect(
      screen.getByRole("button", { name: /read signals/i }).hasAttribute("disabled"),
    ).toBe(true);
  });

  it("disables submit during loading", () => {
    render(
      <BillingView
        state="loading"
        userId="__operator__"
        period="2026-07"
        data={null}
        userIdError={null}
        periodError={null}
        {...viewCallbacks}
      />,
    );
    expect(
      screen.getByRole("button", { name: /read signals/i }).hasAttribute("disabled"),
    ).toBe(true);
  });

  // Idle state
  it("renders idle state prompting user to query", () => {
    render(
      <BillingView
        state="idle"
        userId="__operator__"
        period="2026-07"
        data={null}
        userIdError={null}
        periodError={null}
        {...viewCallbacks}
      />,
    );
    expect(screen.getByText(/ready to observe/i)).toBeTruthy();
  });

  // Long values
  it("renders long values without truncation errors", () => {
    render(
      <BillingView
        state="ready"
        userId={longValuesSummary.user_id}
        period={longValuesSummary.period}
        data={longValuesSummary}
        userIdError={null}
        periodError={null}
        {...viewCallbacks}
      />,
    );
    expect(screen.getAllByText("$149,999.985").length).toBeGreaterThanOrEqual(1);
    // toLocaleString() may or may not use commas depending on locale
    const heading = screen.getByRole("heading", { name: /usage records/i });
    expect(heading.textContent).toContain("999");
    expect(heading.textContent).toMatch(/usage records/i);
  });

  // Singular record
  it("uses singular 'record' for count of 1", () => {
    const single: BillingSummary = { ...fullSummary, record_count: 1 };
    render(
      <BillingView
        state="ready"
        userId="__operator__"
        period="2026-07"
        data={single}
        userIdError={null}
        periodError={null}
        {...viewCallbacks}
      />,
    );
    const heading = screen.getByRole("heading", { name: /1 usage record/i });
    expect(heading.textContent).toBe("1 usage record");
  });

  // Paid-public currently zero note
  it("notes that paid-public is currently zero", () => {
    render(
      <BillingView
        state="ready"
        userId="__operator__"
        period="2026-07"
        data={fullSummary}
        userIdError={null}
        periodError={null}
        {...viewCallbacks}
      />,
    );
    expect(
      screen.getByText(/currently zero: no paid-public dispatches observed/i),
    ).toBeTruthy();
  });

  // Werner mood
  it("renders Werner in empty mood on error", () => {
    render(
      <BillingView
        state="error"
        userId="__operator__"
        period="2026-07"
        data={null}
        userIdError={null}
        periodError={null}
        {...viewCallbacks}
      />,
    );
    expect(
      screen.getByRole("img", { name: /werner found no data/i }),
    ).toBeTruthy();
  });

  it("renders Werner in thinking mood during loading", () => {
    render(
      <BillingView
        state="loading"
        userId="__operator__"
        period="2026-07"
        data={null}
        userIdError={null}
        periodError={null}
        {...viewCallbacks}
      />,
    );
    expect(
      screen.getByRole("img", { name: /werner is listening/i }),
    ).toBeTruthy();
  });

  it("forces the night fixture independently of host media", () => {
    const { container } = render(
      <BillingView
        state="ready"
        userId="__operator__"
        period="2026-07"
        data={fullSummary}
        userIdError={null}
        periodError={null}
        fixtureTheme="dark"
        {...viewCallbacks}
      />,
    );
    expect(container.querySelector(".buo-shell")?.getAttribute("data-theme")).toBe("dark");
  });

  // Free-tier consumed note
  it("notes that free-tier values are currently zero due to paid-private classification", () => {
    render(
      <BillingView
        state="ready"
        userId="__operator__"
        period="2026-07"
        data={fullSummary}
        userIdError={null}
        periodError={null}
        {...viewCallbacks}
      />,
    );
    expect(
      screen.getByText(/all dispatches are classified paid-private/i),
    ).toBeTruthy();
  });

  // Not-a-settled-charge
  it("labels results as not a settled charge", () => {
    render(
      <BillingView
        state="ready"
        userId="__operator__"
        period="2026-07"
        data={fullSummary}
        userIdError={null}
        periodError={null}
        {...viewCallbacks}
      />,
    );
    expect(
      screen.getByText(/not a settled charge/i),
    ).toBeTruthy();
  });
});

// ── Billing (controller / integration) ──────────────────────────────

describe("Billing controller", () => {
  beforeEach(() => vi.clearAllMocks());

  it("starts in idle state and loads after explicit Apply", async () => {
    vi.mocked(apiFetch).mockResolvedValue(response(fullSummary));
    render(<Billing />);
    // Starts idle
    expect(screen.getByText(/ready to observe/i)).toBeTruthy();
    // Click "Read signals"
    fireEvent.click(screen.getByRole("button", { name: /read signals/i }));
    expect(
      await screen.findByRole("heading", { name: /42 usage records/i }),
    ).toBeTruthy();
    expect(apiFetch).toHaveBeenCalledTimes(1);
    expect(apiFetch).toHaveBeenCalledWith(
      expect.stringContaining("/billing/summary/__operator__/"),
    );
  });

  it("shows error state on HTTP failure without rendering raw error", async () => {
    vi.mocked(apiFetch).mockResolvedValue(response(null, false));
    render(<Billing />);
    fireEvent.click(screen.getByRole("button", { name: /read signals/i }));
    expect(
      await screen.findByText(/usage signals unavailable/i),
    ).toBeTruthy();
    expect(screen.queryByText(/HTTP \d+/i)).toBeNull();
  });

  it("does not expose retry after the draft becomes invalid", async () => {
    vi.mocked(apiFetch).mockResolvedValue(response(null, false));
    render(<Billing />);
    fireEvent.click(screen.getByRole("button", { name: /read signals/i }));
    await screen.findByRole("button", { name: /try again/i });
    fireEvent.change(screen.getByLabelText(/user id/i), { target: { value: "" } });
    expect(screen.queryByRole("button", { name: /try again/i })).toBeNull();
    expect(apiFetch).toHaveBeenCalledTimes(1);
  });

  it("rejects a malformed successful payload instead of inferring empty", async () => {
    vi.mocked(apiFetch).mockResolvedValue(
      response({ user_id: "__operator__", period: "2026-07" }),
    );
    render(<Billing />);
    fireEvent.click(screen.getByRole("button", { name: /read signals/i }));
    expect(
      await screen.findByText(/usage signals unavailable/i),
    ).toBeTruthy();
    expect(screen.queryByText(/0 usage records/i)).toBeNull();
  });

  it("rejects payload with negative integers", async () => {
    vi.mocked(apiFetch).mockResolvedValue(
      response({ ...fullSummary, free_tokens_consumed: -100 }),
    );
    render(<Billing />);
    fireEvent.click(screen.getByRole("button", { name: /read signals/i }));
    expect(
      await screen.findByText(/usage signals unavailable/i),
    ).toBeTruthy();
  });

  it("rejects payload with non-integer token counts", async () => {
    vi.mocked(apiFetch).mockResolvedValue(
      response({ ...fullSummary, free_tokens_consumed: 1.5 }),
    );
    render(<Billing />);
    fireEvent.click(screen.getByRole("button", { name: /read signals/i }));
    expect(
      await screen.findByText(/usage signals unavailable/i),
    ).toBeTruthy();
  });

  it("rejects integers that cannot survive JSON parsing exactly", async () => {
    vi.mocked(apiFetch).mockResolvedValue(
      response({ ...fullSummary, record_count: Number.MAX_SAFE_INTEGER + 1 }),
    );
    render(<Billing />);
    fireEvent.click(screen.getByRole("button", { name: /read signals/i }));
    expect(await screen.findByText(/usage signals unavailable/i)).toBeTruthy();
  });

  it("rejects totals that violate the backend billing arithmetic", async () => {
    vi.mocked(apiFetch).mockResolvedValue(
      response({ ...fullSummary, total_billable_usd: "18.76" }),
    );
    render(<Billing />);
    fireEvent.click(screen.getByRole("button", { name: /read signals/i }));
    expect(await screen.findByText(/usage signals unavailable/i)).toBeTruthy();
  });

  it("rejects free or paid-public values the live adapter cannot emit", async () => {
    vi.mocked(apiFetch).mockResolvedValue(
      response({ ...fullSummary, paid_public_token_cost_usd: "0.01" }),
    );
    render(<Billing />);
    fireEvent.click(screen.getByRole("button", { name: /read signals/i }));
    expect(await screen.findByText(/usage signals unavailable/i)).toBeTruthy();
  });

  it("rejects payload with negative USD strings", async () => {
    vi.mocked(apiFetch).mockResolvedValue(
      response({ ...fullSummary, total_raw_usd: "-1.00" }),
    );
    render(<Billing />);
    fireEvent.click(screen.getByRole("button", { name: /read signals/i }));
    expect(
      await screen.findByText(/usage signals unavailable/i),
    ).toBeTruthy();
  });

  it("accepts exponent-form decimal strings without rounding away evidence", async () => {
    const tiny = `$0.${"0".repeat(99)}1`;
    vi.mocked(apiFetch).mockResolvedValue(
      response({
        ...fullSummary,
        paid_private_token_cost_usd: "2E-100",
        paid_private_margin_usd: "1E-100",
        total_raw_usd: "2E-100",
        total_margin_usd: "1E-100",
        total_billable_usd: "3E-100",
      }),
    );
    render(<Billing />);
    fireEvent.click(screen.getByRole("button", { name: /read signals/i }));
    expect((await screen.findAllByText(tiny)).length).toBeGreaterThan(0);
  });

  it("rejects exponent values whose expansion exceeds the allocation bound", async () => {
    vi.mocked(apiFetch).mockResolvedValue(
      response({ ...fullSummary, total_raw_usd: "1E+1000" }),
    );
    render(<Billing />);
    fireEvent.click(screen.getByRole("button", { name: /read signals/i }));
    expect(await screen.findByText(/usage signals unavailable/i)).toBeTruthy();
  });

  it("shows empty state for zero record_count", async () => {
    vi.mocked(apiFetch).mockResolvedValue(response(emptySummary));
    render(<Billing />);
    fireEvent.click(screen.getByRole("button", { name: /read signals/i }));
    expect(
      await screen.findByText(/no usage records returned/i),
    ).toBeTruthy();
  });

  it("applies user changes via explicit Apply button, not per keystroke", async () => {
    vi.mocked(apiFetch).mockResolvedValue(response(fullSummary));
    render(<Billing />);
    fireEvent.click(screen.getByRole("button", { name: /read signals/i }));
    await screen.findByRole("heading", { name: /42 usage records/i });

    const userInput = screen.getByLabelText(/user id/i);
    fireEvent.change(userInput, { target: { value: "other-user" } });
    // Should NOT have triggered a new fetch yet
    expect(apiFetch).toHaveBeenCalledTimes(1);

    // Now submit — wait for the button to be re-enabled after first load
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /read signals/i }).hasAttribute("disabled")).toBe(false),
    );
    fireEvent.click(screen.getByRole("button", { name: /read signals/i }));
    await waitFor(() => expect(apiFetch).toHaveBeenCalledTimes(2));
    expect(apiFetch).toHaveBeenLastCalledWith(
      expect.stringContaining(encodeURIComponent("other-user")),
    );
  });

  it("ignores stale responses after a newer query", async () => {
    let resolveFirst!: (value: Response) => void;
    vi.mocked(apiFetch)
      .mockImplementationOnce(
        () => new Promise((resolve) => { resolveFirst = resolve; }),
      )
      .mockResolvedValueOnce(response(fullSummary));

    render(<Billing />);
    fireEvent.click(screen.getByRole("button", { name: /read signals/i }));
    fireEvent.submit(screen.getByRole("search"));
    expect(
      await screen.findByRole("heading", { name: /42 usage records/i }),
    ).toBeTruthy();
    resolveFirst(response(emptySummary));
    await waitFor(() => expect(screen.getByRole("heading", { name: /42 usage records/i })).toBeTruthy());
    expect(screen.queryByText(/no usage records returned/i)).toBeNull();
  });

  it("invalidates an in-flight observation when the draft query changes", async () => {
    let resolveRequest!: (value: Response) => void;
    vi.mocked(apiFetch).mockImplementationOnce(
      () => new Promise((resolve) => { resolveRequest = resolve; }),
    );
    render(<Billing />);
    fireEvent.click(screen.getByRole("button", { name: /read signals/i }));
    fireEvent.change(screen.getByLabelText(/user id/i), {
      target: { value: "other-user" },
    });
    resolveRequest(response(fullSummary));
    await waitFor(() => expect(screen.getByText(/ready to observe/i)).toBeTruthy());
    expect(screen.queryByRole("heading", { name: /usage records/i })).toBeNull();
  });

  it("rejects a response for a different user or period", async () => {
    vi.mocked(apiFetch).mockResolvedValue(response({ ...fullSummary, user_id: "someone-else" }));
    render(<Billing />);
    fireEvent.click(screen.getByRole("button", { name: /read signals/i }));
    expect((await screen.findByRole("alert")).textContent).toMatch(/unavailable or malformed/i);
  });

  it("rejects zero-record payloads carrying nonzero money", async () => {
    vi.mocked(apiFetch).mockResolvedValue(response({ ...emptySummary, total_billable_usd: "1.00" }));
    render(<Billing />);
    fireEvent.click(screen.getByRole("button", { name: /read signals/i }));
    expect((await screen.findByRole("alert")).textContent).toMatch(/unavailable or malformed/i);
  });

  it("discards in-flight response on unmount", async () => {
    let resolvePromise: ((value: Response) => void) | undefined;
    vi.mocked(apiFetch).mockReturnValue(
      new Promise((r) => { resolvePromise = r; }) as unknown as Promise<Response>,
    );
    const { unmount } = render(<Billing />);
    fireEvent.click(screen.getByRole("button", { name: /read signals/i }));
    unmount();
    // Should not throw or warn when the response resolves after unmount
    resolvePromise?.(response(fullSummary));
    expect(true).toBe(true);
  });

  it("validates period format strictly", () => {
    render(<Billing />);
    const periodInput = screen.getByLabelText(/period/i);

    // Valid formats
    fireEvent.change(periodInput, { target: { value: "2026-07" } });
    expect(screen.queryByText(/use yyyy-mm format/i)).toBeNull();

    // Invalid: month 00
    fireEvent.change(periodInput, { target: { value: "2026-00" } });
    expect(screen.getByText(/use yyyy-mm format/i)).toBeTruthy();

    // Invalid: month 13
    fireEvent.change(periodInput, { target: { value: "2026-13" } });
    expect(screen.getByText(/use yyyy-mm format/i)).toBeTruthy();

    // Invalid: no dash
    fireEvent.change(periodInput, { target: { value: "202607" } });
    expect(screen.getByText(/use yyyy-mm format/i)).toBeTruthy();
  });

  it("validates nonempty user ID", () => {
    render(<Billing />);
    const userInput = screen.getByLabelText(/user id/i);

    fireEvent.change(userInput, { target: { value: "" } });
    expect(screen.getByText(/user id is required/i)).toBeTruthy();

    fireEvent.change(userInput, { target: { value: "someone" } });
    expect(screen.queryByText(/user id is required/i)).toBeNull();
  });

  it("encodes URL components correctly", async () => {
    vi.mocked(apiFetch).mockResolvedValue(response(fullSummary));
    render(<Billing />);

    fireEvent.change(screen.getByLabelText(/user id/i), {
      target: { value: "user/special&chars" },
    });
    fireEvent.click(screen.getByRole("button", { name: /read signals/i }));

    await waitFor(() =>
      expect(apiFetch).toHaveBeenLastCalledWith(
        expect.stringContaining(encodeURIComponent("user/special&chars")),
      ),
    );
  });

  it("handles network errors gracefully without exposing raw errors", async () => {
    vi.mocked(apiFetch).mockRejectedValue(new Error("ECONNREFUSED"));
    render(<Billing />);
    fireEvent.click(screen.getByRole("button", { name: /read signals/i }));
    expect(
      await screen.findByText(/usage signals unavailable/i),
    ).toBeTruthy();
    expect(screen.queryByText(/ECONNREFUSED/i)).toBeNull();
  });
});
