import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";

import { SourcePolicyPreflightPanel } from ".";
import type { SourcePolicyPreflightResponse } from "../../api/research";

afterEach(() => cleanup());

const RECEIPT: SourcePolicyPreflightResponse = {
  source_receipt_id: "srcpf-abc123",
  source_policy: ["operator_corpus", "web", "arxiv"],
  gather_mode: "stub",
  external_call_performed: false,
  connector_execution_allowed: false,
  budget_reserved_usd: 0,
  entries: [
    {
      source: "operator_corpus",
      status: "ready",
      runner_consumes_today: true,
      external_call_would_be_required: false,
      note: "available through the local corpus/reuse substrate",
    },
    {
      source: "web",
      status: "stub",
      runner_consumes_today: false,
      external_call_would_be_required: false,
      note: "current gather mode is stub; no public-web call will run",
    },
    {
      source: "arxiv",
      status: "gated",
      runner_consumes_today: false,
      external_call_would_be_required: true,
      note: "paper connector/source-pack execution is not wired into DRW launch yet",
    },
  ],
  notes: ["preflight only"],
};

describe("SourcePolicyPreflightPanel", () => {
  it("renders no-spend source preflight receipts", () => {
    render(
      <SourcePolicyPreflightPanel
        policy={["operator_corpus", "web", "arxiv"]}
        receipt={RECEIPT}
        busy={false}
        onToggle={() => {}}
        onPreflight={() => {}}
      />,
    );

    expect(screen.getByText("Source preflight")).toBeTruthy();
    expect(screen.getByText(/Receipt srcpf-abc123/)).toBeTruthy();
    expect(screen.getByText(/external call no/)).toBeTruthy();
    expect(screen.getByText(/budget reserved \$0\.00/)).toBeTruthy();
    expect(screen.getByText(/current gather mode is stub/i)).toBeTruthy();
    expect(screen.getByText(/not wired into DRW launch yet/i)).toBeTruthy();
  });

  it("lets the operator change policy and request a check", () => {
    const onToggle = vi.fn();
    const onPreflight = vi.fn();
    render(
      <SourcePolicyPreflightPanel
        policy={["operator_corpus", "web"]}
        receipt={null}
        busy={false}
        onToggle={onToggle}
        onPreflight={onPreflight}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "arXiv" }));
    expect(onToggle).toHaveBeenCalledWith("arxiv");
    fireEvent.click(screen.getByRole("button", { name: "Check sources" }));
    expect(onPreflight).toHaveBeenCalledOnce();
  });
});
