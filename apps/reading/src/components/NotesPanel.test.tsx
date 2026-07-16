import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../api/distillationReconciliation", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/distillationReconciliation")>();
  return {
    ...actual,
    checkProviderOutcome: vi.fn(),
    getDistillationReconciliation: vi.fn(),
    releaseProvenUnsentHold: vi.fn(),
  };
});

import {
  checkProviderOutcome,
  getDistillationReconciliation,
  releaseProvenUnsentHold,
  type DistillationReconciliation,
} from "../api/distillationReconciliation";
import type { DistillationDeliveredPayload, Event } from "../generated/types";
import NotesPanel from "./NotesPanel";

afterEach(cleanup);
beforeEach(() => {
  vi.mocked(getDistillationReconciliation).mockReset();
  vi.mocked(checkProviderOutcome).mockReset();
  vi.mocked(releaseProvenUnsentHold).mockReset();
});

function approvalEvent(reason: "approval_required" | "qualified_route_unavailable"): Event {
  const approvable = reason === "approval_required";
  return {
    event_id: "evt-approval",
    investigation_id: "inv-1",
    synthesis_id: null,
    phase: null,
    role: "synthesizer",
    action_type: "distillation.approval_required",
    payload: {
      action_type: "distillation.approval_required",
      request_event_id: "evt-request",
      reason,
      chain_id: approvable ? "chain-1" : null,
      manifest_sha256: approvable ? "a".repeat(64) : null,
      ceiling_cents: approvable ? 100 : null,
      currency: approvable ? "USD" : null,
      maximum_chain_exposure_cents: approvable ? 80 : null,
    },
    parent_event_id: "evt-request",
    policy_id: "wrestling-spend/approval-required",
    param_version: "test",
    schema_version: 34,
    emitted_at: "2026-07-16T00:00:00Z",
    document_id: "doc-1",
  };
}

function deliveredEvent(): Event {
  return {
    ...approvalEvent("approval_required"),
    event_id: "evt-delivery",
    action_type: "distillation.delivered",
    payload: {
      action_type: "distillation.delivered",
      request_event_id: "evt-request",
      claims: [],
      rendered_text: "Completed distillation",
      rendered_text_hash: "abcd1234",
      token_count: 42,
    },
    policy_id: "wrestling/distillation",
  };
}

function ambiguousEvent(): Event {
  return {
    ...deliveredEvent(),
    event_id: "evt-ambiguous",
    policy_id: "wrestling-fallback/ambiguous",
    payload: {
      ...deliveredEvent().payload,
      request_event_id: "evt-request",
      rendered_text: "Provider outcome is uncertain.",
    } as DistillationDeliveredPayload,
  };
}

function reconciliationView(
  nextAction: DistillationReconciliation["next_action"] = "release_proven_unsent",
  actionExecutable = nextAction === "release_proven_unsent",
): DistillationReconciliation {
  const state = nextAction === "provider_lookup_required" ? "unknown" : "reserved";
  return {
    request_event_id: "evt-request",
    command_state: "ambiguous",
    spend_run_id: "run-1",
    fallback_chain_id: "chain-1",
    manifest_sha256: "a".repeat(64),
    current_fallback_index: 0,
    current_hold_id: "hold-1",
    currency: "USD",
    ceiling_cents: 200,
    authorized_spent_cents: 0,
    held_cents: 80,
    available_cents: 120,
    next_action: nextAction,
    action_executable: actionExecutable,
    holds: [
      {
        fallback_index: 0,
        hold_id: "hold-1",
        provider: "provider",
        model: "model",
        state,
        projected_max_cents: 80,
        actual_cents: null,
        is_current: true,
        evidence_requirement:
          state === "reserved"
            ? "ledger_proven_unsent"
            : "authoritative_provider_lookup",
      },
    ],
  };
}

function requestedEvent(): Event {
  return {
    ...approvalEvent("approval_required"),
    event_id: "evt-request",
    action_type: "distillation.requested",
    payload: {
      action_type: "distillation.requested",
      user_prompt: "Explain this source",
      region_id: null,
      target_token_count: 500,
    },
    parent_event_id: null,
    policy_id: "wrestling/request",
  };
}

function renderPanel(events: Event | Event[]): void {
  render(
    <NotesPanel
      events={Array.isArray(events) ? events : [events]}
      status="open"
      reconnects={0}
      investigationId="inv-1"
      documentId="doc-1"
    />,
  );
}

describe("NotesPanel distillation spend state", () => {
  it("shows exact ceiling exposure and Settings review command", () => {
    renderPanel([requestedEvent(), approvalEvent("approval_required")]);
    expect(screen.getByText("Spend approval required")).not.toBeNull();
    expect(screen.queryByText("waiting for synthesizer…")).toBeNull();
    expect(screen.getByText(/Ceiling \$1\.00 USD/).textContent).toContain(
      "maximum exposure $0.80 USD",
    );
    expect(
      screen.getByRole("link", { name: "Review exact terms in Settings" }).getAttribute("href"),
    ).toBe("/settings");
  });

  it("does not invent terms when no qualified route exists", () => {
    renderPanel([requestedEvent(), approvalEvent("qualified_route_unavailable")]);
    expect(screen.getByText("Qualified paid route unavailable")).not.toBeNull();
    expect(screen.queryByText("waiting for synthesizer…")).toBeNull();
    expect(screen.queryByText(/maximum exposure/)).toBeNull();
    expect(
      screen.getByRole("link", { name: "Open model settings" }).getAttribute("href"),
    ).toBe("/settings");
  });

  it("resolves the approval row after the bound request is delivered", () => {
    renderPanel([approvalEvent("approval_required"), deliveredEvent()]);
    expect(screen.getByText("Spend approved · completed")).not.toBeNull();
    expect(screen.queryByRole("link", { name: "Review exact terms in Settings" })).toBeNull();
  });

  it("requires review of exact reserved-hold terms before release", async () => {
    const before = reconciliationView();
    const after = reconciliationView("none");
    after.held_cents = 0;
    after.available_cents = 200;
    after.holds[0].state = "released";
    vi.mocked(getDistillationReconciliation).mockResolvedValue(before);
    vi.mocked(releaseProvenUnsentHold).mockResolvedValue(after);
    renderPanel(ambiguousEvent());

    fireEvent.click(screen.getByRole("button", { name: "Review held budget" }));
    await screen.findByText("Reserved $0.80 USD");
    expect(screen.getByText("Command state ambiguous")).not.toBeNull();
    expect(screen.getByText(`Manifest ${"a".repeat(64)}`)).not.toBeNull();
    expect(screen.getByText("Fallback route 0")).not.toBeNull();
    expect(screen.getByText("Expected hold state reserved")).not.toBeNull();
    expect(releaseProvenUnsentHold).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Release reserved hold" }));
    await screen.findByText("Hold released · budget restored");
    expect(releaseProvenUnsentHold).toHaveBeenCalledWith(
      "evt-request",
      expect.objectContaining({
        expected_manifest_sha256: "a".repeat(64),
        expected_hold_id: "hold-1",
        expected_hold_state: "reserved",
      }),
    );
  });

  it("never offers local release for provider-possible exposure", async () => {
    vi.mocked(getDistillationReconciliation).mockResolvedValue(
      reconciliationView("provider_lookup_required"),
    );
    renderPanel(ambiguousEvent());
    fireEvent.click(screen.getByRole("button", { name: "Review held budget" }));

    await screen.findByText("Provider verification required · budget remains held");
    expect(screen.queryByRole("button", { name: "Release reserved hold" })).toBeNull();
    expect(releaseProvenUnsentHold).not.toHaveBeenCalled();
    expect(checkProviderOutcome).not.toHaveBeenCalled();
  });

  it("checks provider only from exact executable terms and renders settlement", async () => {
    const before = reconciliationView("provider_lookup_required", true);
    const after = reconciliationView("none", false);
    after.held_cents = 0;
    after.authorized_spent_cents = 60;
    after.holds[0].state = "settled";
    after.holds[0].actual_cents = 60;
    vi.mocked(getDistillationReconciliation).mockResolvedValue(before);
    vi.mocked(checkProviderOutcome).mockResolvedValue(after);
    renderPanel(ambiguousEvent());

    fireEvent.click(screen.getByRole("button", { name: "Review held budget" }));
    await screen.findByText("Provider verification available");
    expect(screen.getByText("Expected hold state unknown")).not.toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Check provider outcome" }));

    await screen.findByText("Provider charge verified · hold settled");
    expect(checkProviderOutcome).toHaveBeenCalledWith(
      "evt-request",
      expect.objectContaining({
        expected_manifest_sha256: "a".repeat(64),
        expected_hold_id: "hold-1",
        expected_hold_state: "unknown",
      }),
    );
    expect(releaseProvenUnsentHold).not.toHaveBeenCalled();
  });

  it("keeps authoritative unknown exposure held after provider check", async () => {
    const unknown = reconciliationView("provider_lookup_required", true);
    vi.mocked(getDistillationReconciliation).mockResolvedValue(unknown);
    vi.mocked(checkProviderOutcome).mockResolvedValue(unknown);
    renderPanel(ambiguousEvent());

    fireEvent.click(screen.getByRole("button", { name: "Review held budget" }));
    await screen.findByText("Provider verification available");
    fireEvent.click(screen.getByRole("button", { name: "Check provider outcome" }));

    await waitFor(() => expect(checkProviderOutcome).toHaveBeenCalledTimes(1));
    expect(screen.getByText("Held $0.80 USD")).not.toBeNull();
    expect(screen.getByRole("button", { name: "Check provider outcome" })).not.toBeNull();
  });

  it("discards provider-check terms after a stale or failed lookup", async () => {
    vi.mocked(getDistillationReconciliation).mockResolvedValue(
      reconciliationView("provider_lookup_required", true),
    );
    vi.mocked(checkProviderOutcome).mockRejectedValue(new Error("private provider failure"));
    renderPanel(ambiguousEvent());

    fireEvent.click(screen.getByRole("button", { name: "Review held budget" }));
    await screen.findByText("Provider verification available");
    fireEvent.click(screen.getByRole("button", { name: "Check provider outcome" }));

    await screen.findByText(
      "Hold state changed. Review current terms before trying again. Budget remains held.",
    );
    expect(screen.queryByRole("button", { name: "Check provider outcome" })).toBeNull();
    expect(screen.queryByText(/private provider failure/)).toBeNull();
  });

  it("keeps budget held and redacts transport failures", async () => {
    vi.mocked(getDistillationReconciliation).mockRejectedValue(
      new Error("secret provider response"),
    );
    renderPanel(ambiguousEvent());
    fireEvent.click(screen.getByRole("button", { name: "Review held budget" }));

    await waitFor(() =>
      expect(
        screen.getByText("Spend evidence is unavailable. Budget remains held."),
      ).not.toBeNull(),
    );
    expect(screen.queryByText(/secret provider response/)).toBeNull();
  });

  it("discards stale release terms and requires a fresh review after rejection", async () => {
    vi.mocked(getDistillationReconciliation).mockResolvedValue(reconciliationView());
    vi.mocked(releaseProvenUnsentHold).mockRejectedValue(new Error("409 private detail"));
    renderPanel(ambiguousEvent());

    fireEvent.click(screen.getByRole("button", { name: "Review held budget" }));
    await screen.findByText("Expected hold state reserved");
    fireEvent.click(screen.getByRole("button", { name: "Release reserved hold" }));

    await screen.findByText(
      "Hold state changed. Review current terms before trying again. Budget remains held.",
    );
    expect(screen.queryByRole("button", { name: "Release reserved hold" })).toBeNull();
    expect(screen.queryByText(/private detail/)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Retry evidence check" }));
    await waitFor(() => expect(getDistillationReconciliation).toHaveBeenCalledTimes(2));
  });
});
