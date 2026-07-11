import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import SourcePreflightPanel from "./SourcePreflightPanel";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const sample = {
  source_receipt_id: "rcpt-1",
  source_policy: ["arxiv", "substack"],
  gather_mode: "parallel",
  entries: [
    {
      source: "arxiv",
      status: "ready",
      runner_consumes_today: false,
      external_call_would_be_required: true,
      note: "ok",
      adapter_importable: true,
      offline_probe_ok: true,
    },
    {
      source: "substack",
      status: "import_only",
      runner_consumes_today: false,
      external_call_would_be_required: true,
      note: "no client",
      adapter_importable: true,
      offline_probe_ok: false,
    },
  ],
  notes: [],
};

describe("SourcePreflightPanel", () => {
  it("runs preflight via injectable and shows honest probe flags", async () => {
    const preflightFn = vi.fn(async () => sample);
    render(
      <SourcePreflightPanel
        preflightFn={preflightFn}
        initialPolicies={["arxiv", "substack"]}
      />,
    );
    fireEvent.click(screen.getByTestId("source-preflight-run"));
    await waitFor(() => {
      expect(screen.getByTestId("source-preflight-result")).toBeTruthy();
    });
    expect(preflightFn).toHaveBeenCalledWith({
      source_policy: ["arxiv", "substack"],
    });
    expect(screen.getByTestId("source-preflight-entry-arxiv").textContent).toMatch(
      /offline probe ok/i,
    );
    expect(
      screen.getByTestId("source-preflight-entry-substack").textContent,
    ).toMatch(/offline probe not ok/i);
    expect(
      screen.getByTestId("source-preflight-entry-arxiv").textContent,
    ).toMatch(/does not claim consumption/i);
  });

  it("surfaces errors without a result", async () => {
    const preflightFn = vi.fn(async () => {
      throw new Error("preflight failed");
    });
    render(<SourcePreflightPanel preflightFn={preflightFn} />);
    fireEvent.click(screen.getByTestId("source-preflight-run"));
    await waitFor(() => {
      expect(screen.getByTestId("source-preflight-error").textContent).toMatch(
        /preflight failed/,
      );
    });
    expect(screen.queryByTestId("source-preflight-result")).toBeNull();
  });
});
