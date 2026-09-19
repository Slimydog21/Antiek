import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const harness = { generation: 1, refs: [] as Array<{ resolve: (v: unknown) => void; signal?: AbortSignal }>, projects: [] as Array<{ resolve: (v: unknown) => void; signal?: AbortSignal }>, interrogations: [] as Array<{ resolve: (v: unknown) => void; signal?: AbortSignal }>, options: [] as Array<{ resolve: (v: unknown) => void; signal?: AbortSignal }>, quotes: [] as Array<{ resolve: (v: unknown) => void }>, launches: [] as Array<{ resolve: (v: unknown) => void }>, runs: [] as Array<{ resolve: (v: unknown) => void }> };
const workload = [["decomposer", 1, 1], ["evidence_retriever", 1, 7], ["parameter_extractor", 1, 0], ["connector", 1, 0], ["synthesizer", 1, 5], ["knowledge_extractor", 0, 12]] as const;
const wholeRun = { schema_version: 1, projection_kind: "admission_upper_bound", plan_sha256: "a".repeat(64), maximum_usd: "3.00000000", forecast_usd_low: null, forecast_usd_high: null, forecast_status: "not_measured", roles: workload.map(([role, mandatory_calls, conditional_calls]) => ({ role, mandatory_calls, conditional_calls, max_calls: mandatory_calls + conditional_calls, selected_route_only: role === "synthesizer", route_max_usd: "0.10000000", role_max_usd: ((mandatory_calls + conditional_calls) * 0.1).toFixed(8), pricing_fingerprints: ["b".repeat(64)] })) };
vi.mock("../../lib/auth", () => ({ useAuth: () => ({ state: { status: "authenticated" }, sessionGeneration: harness.generation }) }));
vi.mock("../../api/engagement", () => ({
  fetchCollectiveManifestReference: vi.fn((_id: string, signal?: AbortSignal) => new Promise((resolve) => harness.refs.push({ resolve, signal }))),
  projectCollectiveManifest: vi.fn((_id: string, signal?: AbortSignal) => new Promise((resolve) => harness.projects.push({ resolve, signal }))),
  fetchCollectiveCouncilReference: vi.fn((_id: string, signal?: AbortSignal) => new Promise((resolve) => harness.refs.push({ resolve, signal }))),
  runCollectiveCouncil: vi.fn(() => new Promise((resolve) => harness.runs.push({ resolve }))),
}));
vi.mock("../../lib/api", () => ({
  getReasoningAncestryInterrogation: vi.fn((_investigationId: string, _receiptId: string, signal?: AbortSignal) => new Promise((resolve) => harness.interrogations.push({ resolve, signal }))),
  getAncestryContinuationOptions: vi.fn((_investigationId: string, _receiptId: string, signal?: AbortSignal) => new Promise((resolve) => harness.options.push({ resolve, signal }))),
  quoteAncestryContinuation: vi.fn(() => new Promise((resolve) => harness.quotes.push({ resolve }))),
  launchAncestryContinuation: vi.fn(() => new Promise((resolve) => harness.launches.push({ resolve }))),
}));
import CollectiveContinuityBridge from "./CollectiveContinuityBridge";

describe("CollectiveContinuityBridge", () => {
  beforeEach(() => { harness.generation = 1; harness.refs = []; harness.projects = []; harness.interrogations = []; harness.options = []; harness.quotes = []; harness.launches = []; harness.runs = []; }); afterEach(cleanup);
  it("rejects forged replay payload fields", () => {
    render(<CollectiveContinuityBridge resume_ref={{ manifest_id: "m", ordered_spawn_ids: ["forged"] }} />);
    expect(screen.getByTestId("collective-continuity-unavailable")).toBeTruthy(); expect(harness.refs).toHaveLength(0);
  });
  it("rejects a malformed interrogation reference instead of falling back to a generic collective", () => {
    render(<CollectiveContinuityBridge resume_ref={{ manifest_id: "m" }} interrogation_ref={{ receipt_id: "receipt", question: "forged" }} />);
    expect(screen.getByTestId("collective-continuity-unavailable")).toBeTruthy();
    expect(harness.refs).toHaveLength(0);
  });
  it("hydrates manifest then projects without an action call", async () => {
    render(<CollectiveContinuityBridge resume_ref={{ manifest_id: "m" }} />);
    await act(async () => harness.refs[0].resolve({ manifest_id: "m", collective_id: "c", membership_sha256: "h" }));
    await act(async () => harness.projects[0].resolve({ manifest_id: "m", collective_id: "c", ordered_spawn_ids: ["s"], prompt_block: "current" }));
    expect(screen.getByTestId("collective-continuity-ready").textContent).toContain("current");
  });
  it("hydrates an immutable interrogation reference and composes its exact question", async () => {
    render(<CollectiveContinuityBridge resume_ref={{ manifest_id: "m" }} interrogation_ref={{ investigation_id: "inv", receipt_id: "receipt" }} />);
    await act(async () => harness.refs[0].resolve({ manifest_id: "m", collective_id: "c", membership_sha256: "h" }));
    await act(async () => harness.projects[0].resolve({ manifest_id: "m", collective_id: "c", ordered_spawn_ids: ["s"], prompt_block: "completed reasoning" }));
    await act(async () => harness.interrogations[0].resolve({
      status: "accepted", stale: false,
      manifest: { manifest_id: "m", collective_id: "c", membership_sha256: "h", ordered_spawn_ids: ["s"] },
      receipt: { receipt_id: "receipt", receipt_sha256: "r".repeat(64), manifest_id: "m", collective_id: "c", membership_sha256: "h", ordered_spawn_ids: ["s"], question: "What survives?", closure_ordinals: [1, 2, 3] },
    }));
    await act(async () => harness.options[0].resolve({ schema_version: 1, investigation_id: "inv", receipt_id: "receipt", receipt_sha256: "r".repeat(64), context_sha256: "c".repeat(64), task_class: "ancestry_collective_continuation", stale: false, assumed_input_tokens: 10, whole_run_cost_projected: true, choices: [], budget: { spent_status: "unknown" }, view_format: "html", action_authority: false }));
    expect(screen.getByRole("region", { name: "Immutable interrogation question" }).textContent).toContain("What survives?");
    expect(screen.getByText(/## Interrogation question/).textContent).toContain("completed reasoning");
  });
  it("reviews an exact quote before a separate explicit launch and exposes the child workstation", async () => {
    render(<CollectiveContinuityBridge resume_ref={{ manifest_id: "m" }} interrogation_ref={{ investigation_id: "inv", receipt_id: "receipt" }} />);
    await act(async () => harness.refs[0].resolve({ manifest_id: "m", collective_id: "c", membership_sha256: "h" }));
    await act(async () => harness.projects[0].resolve({ manifest_id: "m", collective_id: "c", ordered_spawn_ids: ["s"], prompt_block: "completed reasoning" }));
    await act(async () => harness.interrogations[0].resolve({ status: "accepted", stale: false, manifest: { manifest_id: "m", collective_id: "c", membership_sha256: "h", ordered_spawn_ids: ["s"] }, receipt: { receipt_id: "receipt", receipt_sha256: "r".repeat(64), manifest_id: "m", collective_id: "c", membership_sha256: "h", ordered_spawn_ids: ["s"], question: "What survives?", closure_ordinals: [1] } }));
    await act(async () => harness.options[0].resolve({ schema_version: 1, investigation_id: "inv", receipt_id: "receipt", receipt_sha256: "r".repeat(64), context_sha256: "c".repeat(64), task_class: "ancestry_collective_continuation", stale: false, assumed_input_tokens: 10, whole_run_cost_projected: true, choices: [{ role: "synthesizer", projection_scope: "selected_synthesizer_call_only", provider_id: "openai", model_id: "gpt-exact", fallback_index: 0, route_identity: "route", pricing_fingerprint: "p".repeat(64), estimated_usd_low: 0.1, estimated_usd_high: 0.2, remaining_after_high_usd: 1.8, would_exceed_budget: false, pricing_source_url: "https://example.test", pricing_verified_at: "now", pricing_expires_at: "later", boot_ready: true, available: true, reason: "ready", whole_run_envelope: wholeRun }], budget: { remaining_usd: 2, spent_status: "known" }, view_format: "html", action_authority: false }));
    fireEvent.change(screen.getByLabelText("Maximum continuation spend in USD"), { target: { value: "" } });
    expect(screen.getByTestId("collective-continuity-ready").textContent).not.toContain("NaN");
    expect(screen.getByTestId("collective-continuity-ready").textContent).toContain("enter a valid whole-run maximum");
    fireEvent.change(screen.getByLabelText("Maximum continuation spend in USD"), { target: { value: "2.00" } });
    screen.getByRole("button", { name: "Review exact quote" }).click();
    expect(harness.quotes).toHaveLength(1);
    fireEvent.change(screen.getByLabelText("Maximum continuation spend in USD"), { target: { value: "1.50" } });
    await act(async () => harness.quotes[0].resolve({ quote_token: "old-token", quote_id: "old", quote_payload_sha256: "x", route_manifest_fingerprint: "m", context_sha256: "c".repeat(64), receipt_sha256: "r".repeat(64), selected_driver_role: "synthesizer", selected_driver_provider: "openai", selected_driver_model: "gpt-exact", selected_driver_pricing_fingerprint: "p".repeat(64), workload_plan_sha256: wholeRun.plan_sha256, whole_run_maximum_usd: wholeRun.maximum_usd, approved_run_ceiling_usd: "2.00", issued_at_ms: 1, expires_at_ms: 9999999999999, view_format: "html", spend_performed: false }));
    expect(screen.queryByRole("button", { name: "Start quoted continuation" })).toBeNull();
    screen.getByRole("button", { name: "Review exact quote" }).click();
    await act(async () => harness.quotes[1].resolve({ quote_token: "token", quote_id: "q", quote_payload_sha256: "x", route_manifest_fingerprint: "m", context_sha256: "c".repeat(64), receipt_sha256: "r".repeat(64), selected_driver_role: "synthesizer", selected_driver_provider: "openai", selected_driver_model: "gpt-exact", selected_driver_pricing_fingerprint: "p".repeat(64), workload_plan_sha256: wholeRun.plan_sha256, whole_run_maximum_usd: wholeRun.maximum_usd, approved_run_ceiling_usd: "1.50", issued_at_ms: 1, expires_at_ms: 9999999999999, view_format: "html", spend_performed: false }));
    screen.getByRole("button", { name: "Start quoted continuation" }).click();
    expect(harness.launches).toHaveLength(1);
    fireEvent.change(screen.getByLabelText("Maximum continuation spend in USD"), { target: { value: "1.25" } });
    await act(async () => harness.launches[0].resolve({ investigation_id: "stale-child", status: "started", start_event_id: "stale-event", parent_investigation_id: "inv", ancestry_interrogation_receipt_id: "receipt", selected_driver_provider: "openai", selected_driver_model: "gpt-exact", view_format: "html" }));
    expect(screen.queryByRole("link", { name: "open research workstation" })).toBeNull();
    screen.getByRole("button", { name: "Review exact quote" }).click();
    await act(async () => harness.quotes[2].resolve({ quote_token: "new-token", quote_id: "new-q", quote_payload_sha256: "x", route_manifest_fingerprint: "m", context_sha256: "c".repeat(64), receipt_sha256: "r".repeat(64), selected_driver_role: "synthesizer", selected_driver_provider: "openai", selected_driver_model: "gpt-exact", selected_driver_pricing_fingerprint: "p".repeat(64), workload_plan_sha256: wholeRun.plan_sha256, whole_run_maximum_usd: wholeRun.maximum_usd, approved_run_ceiling_usd: "1.25", issued_at_ms: 1, expires_at_ms: 9999999999999, view_format: "html", spend_performed: false }));
    screen.getByRole("button", { name: "Start quoted continuation" }).click();
    await act(async () => harness.launches[1].resolve({ investigation_id: "child", status: "started", start_event_id: "event", parent_investigation_id: "inv", ancestry_interrogation_receipt_id: "receipt", selected_driver_provider: "openai", selected_driver_model: "gpt-exact", view_format: "html" }));
    expect(screen.getByRole("link", { name: "open research workstation" }).getAttribute("href")).toBe("/inv/child");
  });
  it("aborts and fences a slow reference across auth generations", () => {
    const view = render(<CollectiveContinuityBridge resume_ref={{ plan_id: "p" }} />); const old = harness.refs[0];
    harness.generation = 2; view.rerender(<CollectiveContinuityBridge resume_ref={{ plan_id: "p" }} />);
    expect(old.signal?.aborted).toBe(true); expect(screen.queryByTestId("collective-continuity-ready")).toBeNull();
  });
  it("does not install a completed council run after the account and plan identity change", async () => {
    const council = (id: string, state: string) => ({ schema_version: 1, plan: { plan_id: id, shared_prompt: `prompt-${id}`, state, approved_ceiling_cents: 10 }, result: null, view_format: "html" });
    const view = render(<CollectiveContinuityBridge resume_ref={{ plan_id: "old" }} />);
    await act(async () => harness.refs[0].resolve(council("old", "approved")));
    screen.getByRole("button", { name: /Run approved council/ }).click();
    harness.generation = 2;
    view.rerender(<CollectiveContinuityBridge resume_ref={{ plan_id: "new" }} />);
    await act(async () => harness.refs[1].resolve(council("new", "complete")));
    expect(screen.getByText("prompt-new")).toBeTruthy();
    await act(async () => harness.runs[0].resolve({}));
    await act(async () => harness.refs[2].resolve(council("old", "complete")));
    expect(screen.getByText("prompt-new")).toBeTruthy();
    expect(screen.queryByText("prompt-old")).toBeNull();
  });
});
