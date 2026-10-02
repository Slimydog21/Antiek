import type { PropsWithChildren } from "react";
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { unstable_HistoryRouter as HistoryRouter } from "react-router-dom";
import { AuthProvider, useAuth, type AuthContextValue } from "../lib/auth";
import { toast } from "../components/lemon/LemonToast";
import type { Event } from "../generated/types";
import { useOwnerModelController, type OwnerModelController } from "./useOwnerModelController";
import { useResearchHomeBinding } from "../modes/ResearchWorkstation/StartResearch";
import { initializeNavigationHistory, replaceNavigationStateWithoutPublication } from "../workspace/navigationLifetime";
import { useStartInvestigation, type DeepResearchDraft } from "./useStartInvestigation";
import { createRootResearchLaunchArchive } from "../modes/ResearchWorkstation/rootResearchLaunch";

const archiveSlot = vi.hoisted(() => ({ current: null as ReturnType<typeof createRootResearchLaunchArchive> | null }));
vi.mock("../modes/ResearchWorkstation/rootResearchLaunch", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../modes/ResearchWorkstation/rootResearchLaunch")>();
  return { ...actual, get rootResearchLaunchArchive() {
    if (!archiveSlot.current) throw new Error("Missing per-case actual archive");
    return archiveSlot.current;
  } };
});
let streamState = { events: [] as Event[], status: "closed" as "closed" | "open" | "connecting" | "error", reconnects: 0 };
vi.mock("./useEventStream", () => ({ useEventStream: () => streamState }));

// Real AuthProvider, controller, HTTP parsers, home observer and router.
// Only HTTP and event-stream transport are controlled. These are unit identities
// and operation-matched receipts, not live owners, completed work or known charges.
const KEY = "antiek.research.unresolved-owner-launch.session.v2";
const LEGACY = "antiek.research.pending-owner-launch.session.v1";
const model = {
  id: "fixture-key", provider_kind: "openai_compat", provider_catalog_id: "fixture",
  model_id: "variant-a", model_ids: ["variant-a", "variant-b"], display_name: "Unit model",
  base_url: null, enabled: true, key_present: true, registered: true, route_eligible: true,
  pricing_status: "known", hard_ceiling_eligible: true, execution_status: "executable", rate_snapshot: null,
};
let identity: { user_id: string; email: string | null; auth_method: string };
let auth: AuthContextValue;
let controller: OwnerModelController;
let home: ReturnType<typeof useResearchHomeBinding>;
let revision: object;
let mode: object | null;
let quickBusy: boolean;
let bodies: Record<string, unknown>[];
let models = [model];
let reply: (body: Record<string, unknown>) => Promise<Response>;
const pending = new Set<Promise<Response>>();
function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
function json(value: unknown, status = 200): Response {
  return new Response(JSON.stringify(value), { status, headers: { "Content-Type": "application/json" } });
}
function receipt(body: Record<string, unknown>, id = "unit-investigation") {
  if (typeof body.operation_id !== "string") throw new Error("Missing controller-issued operation");
  return { investigation_id: id, start_event_id: `start-${id}`, status: "started", operation_id: body.operation_id, owner_model_status: "queued" };
}
function unitEvent(investigationId: string, payload: Event["payload"]): Event {
  return { event_id: `unit-${payload.action_type}`, investigation_id: investigationId,
    action_type: payload.action_type, payload, param_version: "unit", emitted_at: "2000-01-01T00:00:00Z" };
}
function deferred() {
  let resolve!: (value: Response) => void;
  let reject!: (reason: Error) => void;
  const promise = new Promise<Response>((yes, no) => { resolve = yes; reject = no; });
  pending.add(promise);
  return { promise, resolve(value: Response) { pending.delete(promise); resolve(value); },
    reject(reason: Error) { pending.delete(promise); reject(reason); } };
}
function probe() {
  auth = useAuth();
  controller = useOwnerModelController({ operationPrefix: "research", policy: "strict-owner", allowHouse: false });
  home = useResearchHomeBinding();
  return useStartInvestigation({ controller, ...home,
    isAdmitted: () => mode !== null && !quickBusy,
    readAdmission: () => mode !== null && !quickBusy ? mode : null,
    readDraftRevision: () => revision });
}
function mount() {
  const history = initializeNavigationHistory(window);
  function Wrapper({ children }: PropsWithChildren) {
    return <HistoryRouter history={history}><AuthProvider>{children}</AuthProvider></HistoryRouter>;
  }
  return renderHook(probe, { wrapper: Wrapper });
}
async function ready() {
  await waitFor(() => expect(auth.modelExecution.readCurrent().kind).toBe("ready"));
  await waitFor(() => expect(controller.inventory.kind).toBe("ready"));
  await waitFor(() => expect(home.readHome()).not.toBeNull());
  act(() => controller.select({ kind: "saved", recordId: model.id, modelId: "variant-b" }));
}
function draft(): DeepResearchDraft {
  return { question: "  Explain payer containment  ", researchTier: "deep", sourcePolicy: ["operator_corpus", "web"], revision };
}
beforeEach(() => {
  if (archiveSlot.current) throw new Error("Prior archive fixture not cleaned up");
  archiveSlot.current = createRootResearchLaunchArchive();
  identity = { user_id: "fixture-owner", email: null, auth_method: "antiek_session_cookie" };
  revision = {}; mode = {}; quickBusy = false; bodies = []; models = [model];
  streamState = { events: [], status: "closed", reconnects: 0 };
  sessionStorage.clear();
  initializeNavigationHistory(window);
  replaceNavigationStateWithoutPublication({}, "/");
  reply = async (body) => json(receipt(body));
  vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (url.endsWith("/auth/me")) return json(identity);
    if (url.includes("/settings/models")) return json({ models, count: models.length, stale_registered: [], source: "unit" });
    if (url.endsWith("/investigations")) {
      const body: unknown = JSON.parse(String(init?.body));
      if (!isRecord(body)) throw new Error("Unexpected start body");
      bodies.push(body); return reply(body);
    }
    throw new Error(`Unexpected unit HTTP route: ${url}`);
  }));
  vi.spyOn(toast, "err").mockImplementation(() => 0);
  vi.spyOn(toast, "warn").mockImplementation(() => 0);
});
afterEach(async () => {
  cleanup();
  await act(async () => {});
  expect(pending.size).toBe(0);
  archiveSlot.current = null;
  vi.restoreAllMocks(); vi.unstubAllGlobals();
});

describe("useStartInvestigation paid admission", () => {
  it("issues the saved variant, full required draft and one POST under a synchronous duplicate", async () => {
    const view = mount(); await ready(); const held = deferred(); reply = () => held.promise;
    let first!: Promise<string | null>;
    act(() => { first = view.result.current.submit(draft()); });
    await act(async () => { expect(await view.result.current.submit(draft())).toBeNull(); });
    expect(bodies).toHaveLength(1);
    expect(bodies[0]).toEqual({ question: "Explain payer containment", research_tier: "deep", source_policy: ["operator_corpus", "web"],
      model_choice: { authority: "user_model", provider_id: "fixture-key", model_id: "variant-b" }, operation_id: expect.stringMatching(/^research-/) });
    expect(view.result.current.isIssued()).toBe(true);
    const raw = sessionStorage.getItem(KEY)!;
    expect(raw).not.toContain("Explain"); expect(raw).not.toContain("variant-b"); expect(raw).not.toContain("source_policy");
    await act(async () => { held.resolve(json(receipt(bodies[0]))); await first; });
    expect(view.result.current.startedId).toBe("unit-investigation"); expect(sessionStorage.getItem(KEY)).toBeNull();
  });
  it("refuses live Quick busy and retained mode callbacks without sending", async () => {
    const view = mount(); await ready(); const submit = view.result.current.submit;
    quickBusy = true;
    await act(async () => { expect(await submit(draft())).toBeNull(); });
    quickBusy = false; mode = {}; view.rerender();
    await act(async () => { expect(await submit(draft())).toBeNull(); });
    expect(bodies).toHaveLength(0);
  });
  it("refuses a retained draft revision and a too-short current draft", async () => {
    const view = mount(); await ready(); const old = draft(); revision = {}; view.rerender();
    await act(async () => { expect(await view.result.current.submit(old)).toBeNull(); });
    await act(async () => { await view.result.current.submit({ ...draft(), question: "ab" }); });
    expect(view.result.current.error).toBe("Question is too short. At least 3 characters."); expect(bodies).toHaveLength(0);
  });
  it("keeps issued delivery after a real inventory refresh invalidates its preparation", async () => {
    const view = mount(); await ready(); const held = deferred(); reply = () => held.promise;
    let operation!: Promise<string | null>;
    act(() => { operation = view.result.current.submit(draft()); });
    models = [];
    await act(async () => { await controller.refresh(); });
    await act(async () => { held.resolve(json(receipt(bodies[0]))); await operation; });
    expect(view.result.current.startedId).toBe("unit-investigation"); expect(bodies).toHaveLength(1);
  });
  it("archives a valid late receipt after real owner A-B-A without publishing it", async () => {
    const view = mount(); await ready(); const held = deferred(); reply = () => held.promise;
    let operation!: Promise<string | null>;
    act(() => { operation = view.result.current.submit(draft()); });
    identity = { ...identity, user_id: "fixture-owner-b" };
    await act(async () => { await auth.refresh(); });
    identity = { ...identity, user_id: "fixture-owner" };
    await act(async () => { await auth.refresh(); });
    await act(async () => { held.resolve(json(receipt(bodies[0]))); expect(await operation).toBeNull(); });
    expect(view.result.current.startedId).toBeNull(); expect(archiveSlot.current!.hasUnresolved()).toBe(false);
    expect(sessionStorage.getItem(KEY)).toBeNull(); expect(toast.warn).not.toHaveBeenCalled();
  });
  it("refuses retained separate acknowledgment after owner replacement", async () => {
    const view = mount(); await ready(); const separate = view.result.current.startSeparate;
    identity = { ...identity, user_id: "fixture-owner-b" };
    await act(async () => { await auth.refresh(); }); await ready();
    act(() => { expect(separate()).toBe(false); }); expect(bodies).toHaveLength(0);
  });
});

describe("useStartInvestigation unknown outcomes", () => {
  it.each([
    ["missing investigation ID", { investigation_id: "" }],
    ["missing start event", { start_event_id: " " }],
    ["wrong status", { status: "in_progress" }],
    ["wrong operation", { operation_id: "foreign-operation" }],
    ["wrong owner route", { owner_model_status: "unknown" }],
  ])("retains uncertainty for %s with no soft effects", async (_label, change) => {
    const view = mount(); await ready();
    reply = async (body) => json({ ...receipt(body), ...change, capacity_warning: { code: "compute_capacity_soft_warn", message: "near", enforcement: "soft" } });
    await act(async () => { await view.result.current.submit(draft()); });
    expect(view.result.current.startedId).toBeNull(); expect(view.result.current.showUncertainty).toBe(true);
    expect(sessionStorage.getItem(KEY)).not.toBeNull(); expect(toast.warn).not.toHaveBeenCalled(); expect(bodies).toHaveLength(1);
  });
  it("directs exact connect_model to Settings and never grants generic retry", async () => {
    const view = mount(); await ready(); reply = async () => json({ detail: "connect_model" }, 409);
    await act(async () => { await view.result.current.submit(draft()); });
    expect(view.result.current.error).toBe("Choose a model in Settings. The previous request may have been accepted or charged.");
    await act(async () => { await view.result.current.submit(draft()); }); expect(bodies).toHaveLength(1);
  });
  it.each([["provider error", 500, { detail: "provider-secret-value" }], ["unrelated conflict", 409, { detail: "different_conflict" }],
    ["malformed conflict", 409, "not-json"]])("keeps %s private and uncertain", async (_label, status, body) => {
    const view = mount(); await ready(); reply = async () => json(body, status);
    await act(async () => { await view.result.current.submit(draft()); });
    expect(view.result.current.error).toBe("Could not confirm the start. The request may have been accepted or charged.");
    expect(view.result.current.error).not.toContain("provider-secret-value"); expect(bodies).toHaveLength(1);
  });
  it("keeps multiple explicit separate intents and refuses a changed hold acknowledgment", async () => {
    const view = mount(); await ready(); reply = async () => { throw new Error("unit transport loss"); };
    await act(async () => { await view.result.current.submit(draft()); });
    act(() => { expect(view.result.current.startSeparate()).toBe(true); });
    const stored = JSON.parse(sessionStorage.getItem(KEY)!) as { version: number; holds: Array<{ owner: object; operation_id: string }> };
    stored.holds.push({ ...stored.holds[0], operation_id: "unit-other-original-operation" }); sessionStorage.setItem(KEY, JSON.stringify(stored));
    await act(async () => { await view.result.current.submit(draft()); }); expect(bodies).toHaveLength(1);
    act(() => { expect(view.result.current.startSeparate()).toBe(true); });
    await act(async () => { await view.result.current.submit(draft()); });
    expect(bodies).toHaveLength(2); expect(bodies[1].operation_id).not.toBe(bodies[0].operation_id);
    expect(JSON.parse(sessionStorage.getItem(KEY)!).holds).toHaveLength(3);
  });
  it("preserves opaque malformed legacy data while confirming a separate new intent", async () => {
    sessionStorage.setItem(LEGACY, "private-question-and-legacy-data"); const view = mount(); await ready();
    expect(view.result.current.showUncertainty).toBe(true);
    await act(async () => { await view.result.current.submit(draft()); }); expect(bodies).toHaveLength(0);
    act(() => { expect(view.result.current.startSeparate()).toBe(true); });
    await act(async () => { await view.result.current.submit(draft()); });
    expect(bodies).toHaveLength(1); expect(sessionStorage.getItem(LEGACY)).toBe("private-question-and-legacy-data");
  });
  it("does not replay an unresolved operation across actual unmount/remount", async () => {
    const first = mount(); await ready(); reply = async () => { throw new Error("unit transport loss"); };
    await act(async () => { await first.result.current.submit(draft()); }); const original = bodies[0].operation_id;
    first.unmount(); const second = mount(); await ready();
    await act(async () => { await second.result.current.submit(draft()); }); expect(bodies).toHaveLength(1);
    act(() => { expect(second.result.current.startSeparate()).toBe(true); });
    await act(async () => { await second.result.current.submit(draft()); });
    expect(bodies).toHaveLength(2); expect(bodies[1].operation_id).not.toBe(original);
    expect(sessionStorage.getItem(KEY)).toContain(String(original));
  });
});

describe("useStartInvestigation storage and received delivery", () => {
  it.each(["read", "write", "readback"])("refuses POST when marker %s fails", async (failure) => {
    const view = mount(); await ready();
    const get = Storage.prototype.getItem; let written = false;
    if (failure === "write") vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("unit quota"); });
    else if (failure === "read") vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("unit denied"); });
    else {
      const set = Storage.prototype.setItem;
      vi.spyOn(Storage.prototype, "setItem").mockImplementation(function (this: Storage, key, value) { set.call(this, key, value); written = key === KEY; });
      vi.spyOn(Storage.prototype, "getItem").mockImplementation(function (this: Storage, key) { return key === KEY && written ? "different" : get.call(this, key); });
    }
    await act(async () => { await view.result.current.submit(draft()); }); expect(bodies).toHaveLength(0);
    expect(view.result.current.error).toBe("Cannot verify previous research requests in this browser. No new request was sent.");
  });
  it("keeps a conservative hold if accepted marker removal fails, without another POST", async () => {
    const view = mount(); await ready();
    vi.spyOn(Storage.prototype, "removeItem").mockImplementation(() => { throw new Error("unit removal denial"); });
    await act(async () => { await view.result.current.submit(draft()); });
    expect(view.result.current.startedId).toBe("unit-investigation"); expect(sessionStorage.getItem(KEY)).not.toBeNull();
    await act(async () => { await view.result.current.submit(draft()); }); expect(bodies).toHaveLength(1);
  });
  it("retains a received result after a publisher or navigation callback fails", async () => {
    const view = mount(); await ready();
    reply = async (body) => json({ ...receipt(body), capacity_warning: { code: "compute_capacity_soft_warn", message: "near", enforcement: "soft" } });
    vi.mocked(toast.warn).mockImplementation(() => { throw new Error("unit presentation fault"); });
    await act(async () => { await view.result.current.submit(draft()); });
    expect(view.result.current.startedId).toBe("unit-investigation"); expect(archiveSlot.current!.hasUnresolved()).toBe(false);
    expect(toast.warn).toHaveBeenCalledTimes(1);
    expect(view.result.current.error).toBe("The research start was received, but its capacity notice could not be displayed.");
    act(() => view.result.current.reportDeliveryFailure("unit-investigation"));
    expect(view.result.current.error).toContain("was received");
    await act(async () => { await view.result.current.submit(draft()); }); expect(bodies).toHaveLength(1);
  });
  it("filters another investigation's events, failure, cost and unbound open status", async () => {
    const view = mount(); await ready();
    streamState = { events: [
      unitEvent("old-investigation", { action_type: "dispatch.call", provider: "unit", model: "unit", tier: "flash", target_role: "unit",
        input_tokens: 1, output_tokens: 1, cost_usd: 99, latency_ms: 0, prompt_hash: "unit" }),
      unitEvent("old-investigation", { action_type: "investigation.failed", phase: 1, reason: "old failure" }),
    ], status: "open", reconnects: 0 };
    await act(async () => { await view.result.current.submit(draft()); });
    expect(view.result.current.events).toEqual([]); expect(view.result.current.liveCost).toBe(0);
    expect(view.result.current.failed).toBe(false); expect(view.result.current.phase).toBe("connecting");
  });
});


describe("useStartInvestigation exact separate-intent continuity", () => {
  it("requires an explicit new intent after editing a received question without claiming uncertainty", async () => {
    const view = mount(); await ready();
    await act(async () => { await view.result.current.submit(draft()); });
    revision = {}; view.rerender();
    expect(view.result.current.startedId).toBeNull();
    expect(view.result.current.showUncertainty).toBe(false);
    expect(view.result.current.requiresNewIntent).toBe(true);
    await act(async () => { await view.result.current.submit(draft()); }); expect(bodies).toHaveLength(1);
    act(() => { expect(view.result.current.startSeparate()).toBe(true); });
    await act(async () => { await view.result.current.submit(draft()); });
    expect(bodies).toHaveLength(2); expect(bodies[1].operation_id).not.toBe(bodies[0].operation_id);
  });
  it("refuses a global archive acknowledgment whose exact holds disappeared to empty", async () => {
    const view = mount(); await ready();
    const scope = auth.modelExecution.readCurrent();
    if (scope.kind !== "ready") throw new Error("No actual unit owner scope");
    const archive = archiveSlot.current!;
    let handle: ReturnType<typeof archive.beginChild> = null;
    act(() => { handle = archive.beginChild(archive.createIntent(), { question: "Unit archive-only hold" }, scope); });
    if (!handle) throw new Error("Archive hold not created");
    act(() => { expect(view.result.current.startSeparate()).toBe(true); });
    act(() => { expect(archive.accepted(handle!, { investigation_id: "unit-other", status: "started", start_event_id: "unit-event" })).toBe(true); });
    await act(async () => { await view.result.current.submit(draft()); }); expect(bodies).toHaveLength(0);
    act(() => { expect(view.result.current.startSeparate()).toBe(true); });
    await act(async () => { await view.result.current.submit(draft()); }); expect(bodies).toHaveLength(1);
  });
  it("keeps a malformed modern marker opaque and refuses dispatch", async () => {
    sessionStorage.setItem(KEY, '{"version":2,"holds":[{"question":"private-body"}]}');
    const view = mount(); await ready();
    await act(async () => { await view.result.current.submit(draft()); });
    expect(bodies).toHaveLength(0); expect(view.result.current.continuityUnavailable).toBe(true);
    expect(view.result.current.error).not.toContain("private-body");
    act(() => { expect(view.result.current.startSeparate()).toBe(false); });
    expect(sessionStorage.getItem(KEY)).toContain("private-body");
  });
  it("compare-removes only an unsent own marker when archive begin refuses, preserving a foreign hold", async () => {
    const foreign = { owner: { user_id: "foreign-unit-owner", email: null, auth_method: "antiek_session_cookie", operator_email_discriminator: null }, operation_id: "foreign-original-operation" };
    sessionStorage.setItem(KEY, JSON.stringify({ version: 2, holds: [foreign] }));
    const view = mount(); await ready();
    expect(view.result.current.showUncertainty).toBe(false);
    vi.spyOn(archiveSlot.current!, "begin").mockReturnValue(null);
    await act(async () => { await view.result.current.submit(draft()); });
    expect(bodies).toHaveLength(0); expect(JSON.parse(sessionStorage.getItem(KEY)!)).toEqual({ version: 2, holds: [foreign] });
  });
  it("retains the unsent marker conservatively if archive refusal cleanup cannot remove it", async () => {
    const view = mount(); await ready();
    vi.spyOn(archiveSlot.current!, "begin").mockReturnValue(null);
    vi.spyOn(Storage.prototype, "removeItem").mockImplementation(() => { throw new Error("unit removal denied"); });
    await act(async () => { await view.result.current.submit(draft()); });
    expect(bodies).toHaveLength(0); expect(sessionStorage.getItem(KEY)).not.toBeNull();
    expect(view.result.current.showUncertainty).toBe(true);
  });
  it("archives a late unmounted receipt and removes only its marker while a newer intent remains pending", async () => {
    const first = mount(); await ready(); const oldResponse = deferred(); reply = () => oldResponse.promise;
    let oldOperation!: Promise<string | null>;
    act(() => { oldOperation = first.result.current.submit(draft()); });
    first.unmount(); const second = mount(); await ready();
    act(() => { expect(second.result.current.startSeparate()).toBe(true); });
    const newResponse = deferred(); reply = () => newResponse.promise; let newOperation!: Promise<string | null>;
    act(() => { newOperation = second.result.current.submit(draft()); });
    await act(async () => { oldResponse.resolve(json(receipt(bodies[0], "unit-old"))); expect(await oldOperation).toBeNull(); });
    const raw = sessionStorage.getItem(KEY)!;
    expect(raw).not.toContain(String(bodies[0].operation_id)); expect(raw).toContain(String(bodies[1].operation_id));
    expect(second.result.current.startedId).toBeNull(); expect(second.result.current.isIssued()).toBe(true);
    await act(async () => { newResponse.resolve(json(receipt(bodies[1], "unit-new"))); await newOperation; });
    expect(second.result.current.startedId).toBe("unit-new"); expect(sessionStorage.getItem(KEY)).toBeNull();
  });
  it("contains synchronous preparation failure before marker or POST", async () => {
    const view = mount(); await ready();
    vi.spyOn(controller, "prepareLaunch").mockImplementation(() => { throw new Error("unit preparation fault"); });
    await act(async () => { await view.result.current.submit(draft()); });
    expect(bodies).toHaveLength(0); expect(sessionStorage.getItem(KEY)).toBeNull();
    expect(view.result.current.error).toBe("Could not prepare this research request. No new request was sent.");
  });
});


describe("useStartInvestigation admitted hard capacity diagnostics", () => {
  const exhausted = { code: "compute_capacity_exhausted", message: "Unit capacity reached",
    used_compute_units: 10, monthly_compute_units: 10, enforcement: "hard", used_status: "known" };
  it("publishes the current typed hard Settings diagnostic while retaining uncertainty and refusing retry", async () => {
    const view = mount(); await ready(); reply = async () => json({ detail: exhausted }, 429);
    await act(async () => { await view.result.current.submit(draft()); });
    expect(toast.err).toHaveBeenCalledTimes(1);
    expect(toast.err).toHaveBeenCalledWith(expect.stringContaining("10/10 ACU"), { ttl: 10000, target: { path: "/settings" } });
    expect(view.result.current.error).toContain("may have been accepted or charged");
    expect(view.result.current.showUncertainty).toBe(true); expect(sessionStorage.getItem(KEY)).not.toBeNull();
    await act(async () => { await view.result.current.submit(draft()); }); expect(bodies).toHaveLength(1);
  });
  it("archives a retired hard outcome as unknown without publishing its diagnostic", async () => {
    const view = mount(); await ready(); const held = deferred(); reply = () => held.promise;
    let operation!: Promise<string | null>;
    act(() => { operation = view.result.current.submit(draft()); });
    act(() => { initializeNavigationHistory(window).push("/unit-away"); });
    await act(async () => { held.resolve(json({ detail: exhausted }, 429)); expect(await operation).toBeNull(); });
    expect(view.result.current.error).toBeNull(); expect(view.result.current.startedId).toBeNull();
    expect(toast.err).not.toHaveBeenCalled(); expect(toast.warn).not.toHaveBeenCalled();
    expect(archiveSlot.current!.hasUnresolved()).toBe(true); expect(sessionStorage.getItem(KEY)).not.toBeNull();
    expect(bodies).toHaveLength(1);
  });
});
