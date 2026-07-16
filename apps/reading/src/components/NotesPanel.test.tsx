import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { Event } from "../generated/types";
import NotesPanel from "./NotesPanel";

afterEach(cleanup);

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
});
