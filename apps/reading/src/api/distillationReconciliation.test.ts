import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../lib/api", () => ({ API_BASE: "", apiFetch: vi.fn() }));

import { apiFetch } from "../lib/api";
import {
  getDistillationReconciliation,
  releaseProvenUnsentHold,
  reservedReleaseTerms,
  type DistillationReconciliation,
} from "./distillationReconciliation";

const mockFetch = vi.mocked(apiFetch);

function view(): DistillationReconciliation {
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
    next_action: "release_proven_unsent",
    action_executable: false,
    holds: [
      {
        fallback_index: 0,
        hold_id: "hold-1",
        provider: "provider",
        model: "model",
        state: "reserved",
        projected_max_cents: 80,
        actual_cents: null,
        is_current: true,
        evidence_requirement: "ledger_proven_unsent",
      },
    ],
  };
}

beforeEach(() => mockFetch.mockReset());

describe("distillation reconciliation API", () => {
  it("derives exact immutable release terms from an authoritative view", () => {
    expect(reservedReleaseTerms(view())).toEqual({
      expected_command_state: "ambiguous",
      expected_spend_run_id: "run-1",
      expected_fallback_chain_id: "chain-1",
      expected_manifest_sha256: "a".repeat(64),
      expected_fallback_index: 0,
      expected_hold_id: "hold-1",
      expected_hold_state: "reserved",
    });
  });

  it("never derives release authority for provider-possible exposure", () => {
    const unsafe = view();
    unsafe.next_action = "provider_lookup_required";
    unsafe.holds[0].state = "unknown";
    expect(() => reservedReleaseTerms(unsafe)).toThrow("not authorized");
  });

  it("posts the exact reviewed terms and strictly parses the result", async () => {
    const responseView = view();
    responseView.next_action = "none";
    responseView.held_cents = 0;
    responseView.holds[0].state = "released";
    mockFetch.mockResolvedValue(
      new Response(JSON.stringify(responseView), { status: 200 }),
    );
    const terms = reservedReleaseTerms(view());
    await expect(releaseProvenUnsentHold("evt/request", terms)).resolves.toEqual(
      responseView,
    );
    expect(mockFetch).toHaveBeenCalledWith(
      expect.stringContaining("evt%2Frequest/reconciliation/actions/release-proven-unsent"),
      expect.objectContaining({ method: "POST", body: JSON.stringify(terms) }),
    );
  });

  it("rejects malformed read responses", async () => {
    mockFetch.mockResolvedValue(
      new Response(JSON.stringify({ ...view(), action_executable: true }), { status: 200 }),
    );
    await expect(getDistillationReconciliation("evt-request")).rejects.toThrow(
      "Invalid reconciliation response",
    );
  });
});
