import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import SpendConsentPanel from "./SpendConsentPanel";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const sample = {
  receipt_id: "rcpt-abcdef123456",
  operator_id: "op-1",
  job_id: "job-1",
  operation_id: "opn-1",
  config_hash: "abc123",
  ceiling_cents: 500,
  issued_at_ms: 1_000,
  expires_at_ms: 9_999_999_999_999,
  nonce: "n1",
  key_id: "k1",
};

describe("SpendConsentPanel", () => {
  it("loads via injectable loadFn", async () => {
    const loadFn = vi.fn(async () => sample);
    render(<SpendConsentPanel loadFn={loadFn} nowMs={2_000} />);
    fireEvent.click(screen.getByTestId("spend-consent-load"));
    await waitFor(() => {
      expect(screen.getByTestId("spend-consent-summary").textContent).toMatch(
        /ceiling 500/,
      );
    });
    expect(screen.getByTestId("spend-consent-sig").textContent).toMatch(
      /signature_verified=false/,
    );
  });

  it("rejects forged signature_verified", async () => {
    const loadFn = vi.fn(async () => ({
      ...sample,
      signature_verified: true,
    }));
    render(<SpendConsentPanel loadFn={loadFn} />);
    fireEvent.click(screen.getByTestId("spend-consent-load"));
    await waitFor(() => {
      expect(screen.getByTestId("spend-consent-error").textContent).toMatch(
        /signature_verified/,
      );
    });
  });

  it("shows static receipt when valid", () => {
    render(<SpendConsentPanel receipt={sample} nowMs={2_000} />);
    // static path sets view in useState initializer
    expect(screen.getByTestId("spend-consent-summary").textContent).toMatch(
      /ceiling 500/,
    );
  });
});
