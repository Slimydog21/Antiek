/** Synthetic local UNIT replies and owners, through the actual transport/runner.
 * These controls do not call a provider or prove a signed account journey. */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { awaitWorkspaceOwnerSession, resumeWorkspaceOwner, setWorkspaceOwner, suspendWorkspaceOwner, workspaceOwnerSession } from "../../lib/accountWorkspaceOwner";
import { AGENT_PANE_SCOPE } from "./agentTypes";
import { thoughtPartnerTransport, type AgentTransportReply } from "./agentTransport";
import { createTurnRunner, NO_REPLY_MS, type LifecycleState } from "./turnLifecycle";

const fetchMock = vi.fn();
vi.mock("../../lib/api", async (original) => ({
  ...(await original<typeof import("../../lib/api")>()),
  apiFetch: (...args: unknown[]) => fetchMock(...args),
}));

const request = () => ({ prompt: "local UNIT question", history: [], system_context: "local UNIT context" });
function response(value: unknown) {
  return { ok: true, status: 200, json: async () => value };
}
function send() {
  return thoughtPartnerTransport.send({ ...request(), signal: new AbortController().signal });
}
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => { resolve = done; });
  return { promise, resolve };
}
const runners: ReturnType<typeof createTurnRunner>[] = [];
function runner(current?: () => boolean) {
  const states: LifecycleState[] = [];
  const replies: AgentTransportReply[] = [];
  const value = createTurnRunner({
    transport: thoughtPartnerTransport, request, owner: workspaceOwnerSession(), current,
    onState: (state, reply) => { states.push(state); if (reply) replies.push(reply); },
  });
  runners.push(value);
  return { value, states, replies };
}
beforeEach(async () => {
  fetchMock.mockReset();
  setWorkspaceOwner(null); setWorkspaceOwner("unit-agent-dto-A");
  await awaitWorkspaceOwnerSession(workspaceOwnerSession());
  vi.useFakeTimers();
});
afterEach(() => {
  try { for (const value of runners.splice(0)) value.dispose(); }
  finally { setWorkspaceOwner(null); vi.useRealTimers(); vi.restoreAllMocks(); }
});

const malformed = [0, 23, false, {}, [], ["reply"]];
describe("agent reply DTO admission", () => {
  it.each(malformed.map((value) => [value]))("C01 rejects selected non-string text: %j", async (text) => {
    fetchMock.mockResolvedValue(response({ text, body: "unselected legacy reply" }));
    await expect(send()).rejects.toThrow();
  });
  it.each(malformed.map((value) => [value]))("C02 rejects selected non-string legacy body: %j", async (body) => {
    fetchMock.mockResolvedValue(response({ text: null, body }));
    await expect(send()).rejects.toThrow();
  });
  it.each([null, [], "raw reply", 23, true].map((value) => [value]))("C04 rejects a non-object envelope: %j", async (value) => {
    fetchMock.mockResolvedValue(response(value));
    await expect(send()).rejects.toThrow();
  });
  it("C04 preserves a rejected JSON parse as transport rejection", async () => {
    const error = new SyntaxError("local malformed JSON");
    fetchMock.mockResolvedValue({ ok: true, status: 200, json: async () => { throw error; } });
    await expect(send()).rejects.toBe(error);
  });
  it.each(malformed.map((value) => [value]))("rejects malformed consumed retrieval status: %j", async (status) => {
    fetchMock.mockResolvedValue(response({ text: "reply", library_retrieval_status: status }));
    await expect(send()).rejects.toThrow();
  });
  it.each([undefined, null, "hit"])("retains optional retrieval status: %j", async (status) => {
    fetchMock.mockResolvedValue(response({ text: "reply", library_retrieval_status: status }));
    const result = await send();
    expect(result.text).toBe("reply");
    if (status === undefined) expect(result).not.toHaveProperty("libraryRetrievalStatus");
    else expect(result.libraryRetrievalStatus).toBe(status);
  });
  it.each([{}, { text: null }, { text: undefined, body: null }, { text: "", body: "not selected" }])("C04 preserves intentional empty fallback: %j", async (value) => {
    fetchMock.mockResolvedValue(response(value));
    expect((await send()).text).toBe("");
  });
  it.each([{ body: "legacy reply" }, { text: null, body: "legacy reply" }])("C02 preserves legacy string body: %j", async (value) => {
    fetchMock.mockResolvedValue(response(value));
    expect((await send()).text).toBe("legacy reply");
  });
  it("C05 ignores unselected malformed body and unrelated future fields; wire, shape and signal stay exact", async () => {
    fetchMock.mockResolvedValue(response({ text: "current reply", body: {}, shape: "challenge", future: [1] }));
    const signal = new AbortController().signal;
    const result = await thoughtPartnerTransport.send({ ...request(), signal });
    expect(result).toEqual({ text: "current reply", shape: "CHALLENGE" });
    expect(thoughtPartnerTransport.kind).toBe("whole");
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("/thought-partner"); expect(init.method).toBe("POST"); expect(init.signal).toBe(signal);
    const body = JSON.parse(String(init.body));
    expect(Object.keys(body).sort()).toEqual(["history", "investigation_id", "prompt", "system_context"]);
    expect(body).toEqual({ investigation_id: AGENT_PANE_SCOPE, ...request() });
  });
  it("C05 keeps the existing unknown shape normalization", async () => {
    fetchMock.mockResolvedValue(response({ text: "reply", shape: {} }));
    expect((await send()).shape).toBe("SYNTHESIS");
  });
});

describe("real runner response-contract join", () => {
  it("C03 publishes malformed DTO transport failure, retires the request and never becomes a timed no-reply", async () => {
    fetchMock.mockResolvedValue(response({ text: 23 }));
    const r = runner(); r.value.send();
    await vi.advanceTimersByTimeAsync(0);
    expect(r.states.map((state) => state.phase)).toEqual(["sent", "failed"]);
    expect(r.value.state()).toMatchObject({ phase: "failed", reason: "transport" });
    const signal = (fetchMock.mock.calls[0][1] as RequestInit).signal!;
    r.value.dispose();
    expect(signal.aborted).toBe(false); // settled request was retired, not left live for disposal
    await vi.advanceTimersByTimeAsync(NO_REPLY_MS + 1000);
    expect(r.states.map((state) => state.phase)).toEqual(["sent", "failed"]);
  });
  it("C04 genuine empty text still uses the empty-reply failure", async () => {
    fetchMock.mockResolvedValue(response({ text: "" }));
    const r = runner(); r.value.send(); await vi.advanceTimersByTimeAsync(0);
    expect(r.value.state()).toMatchObject({ phase: "failed", reason: "empty", error: null });
  });
  it("C03 one explicit Retry sends once and accepts the next valid reply", async () => {
    fetchMock.mockResolvedValueOnce(response({ text: 23 })).mockResolvedValueOnce(response({ text: "local retry reply" }));
    const r = runner(); r.value.send(); await vi.advanceTimersByTimeAsync(0);
    expect(r.value.state()).toMatchObject({ phase: "failed", reason: "transport" });
    r.value.retry(); await vi.advanceTimersByTimeAsync(0);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(r.states.map((s) => s.phase)).toEqual(["sent", "failed", "sent", "done"]);
    expect(r.replies.at(-1)?.text).toBe("local retry reply");
  });
  it("C06 owner A-B-A refuses the original response and aborts the original signal", async () => {
    const d = deferred<ReturnType<typeof response>>(); fetchMock.mockReturnValue(d.promise);
    const r = runner(); r.value.send();
    const signal = (fetchMock.mock.calls[0][1] as RequestInit).signal!;
    setWorkspaceOwner("unit-agent-dto-B"); setWorkspaceOwner("unit-agent-dto-A");
    await awaitWorkspaceOwnerSession(workspaceOwnerSession());
    d.resolve(response({ text: 23 })); await vi.advanceTimersByTimeAsync(0);
    expect(signal.aborted).toBe(true); expect(r.states.map((s) => s.phase)).toEqual(["sent"]); expect(r.replies).toEqual([]);
  });
  it("C06 retired pane refuses completion independently of the still-confirmed owner", async () => {
    const d = deferred<ReturnType<typeof response>>(); fetchMock.mockReturnValue(d.promise);
    let current = true; const r = runner(() => current); r.value.send();
    current = false; d.resolve(response({ text: "retired pane reply" })); await vi.advanceTimersByTimeAsync(0);
    expect(r.states.map((s) => s.phase)).toEqual(["sent"]); expect(r.replies).toEqual([]);
  });
  it("C06 same-owner suspension holds malformed reply failure until actual resume", async () => {
    const d = deferred<ReturnType<typeof response>>(); fetchMock.mockReturnValue(d.promise);
    const r = runner(); r.value.send(); suspendWorkspaceOwner();
    d.resolve(response({ text: 23 })); await vi.advanceTimersByTimeAsync(0);
    expect(r.states.map((s) => s.phase)).toEqual(["sent"]);
    resumeWorkspaceOwner(); await vi.advanceTimersByTimeAsync(0);
    expect(r.value.state()).toMatchObject({ phase: "failed", reason: "transport" }); expect(fetchMock).toHaveBeenCalledTimes(1);
  });
  it("C06 suspension before send defers the single actual transport dispatch", async () => {
    fetchMock.mockResolvedValue(response({ text: "confirmed local reply" }));
    suspendWorkspaceOwner(); const r = runner(); r.value.send(); await vi.advanceTimersByTimeAsync(0);
    expect(fetchMock).not.toHaveBeenCalled();
    resumeWorkspaceOwner(); await vi.advanceTimersByTimeAsync(0);
    expect(fetchMock).toHaveBeenCalledTimes(1); expect(r.value.state().phase).toBe("done");
  });
  it("C06 replaced attempt refuses an old malformed reply after Retry", async () => {
    const d = deferred<ReturnType<typeof response>>();
    fetchMock.mockReturnValueOnce(d.promise).mockResolvedValueOnce(response({ text: "current local reply" }));
    const r = runner(); r.value.send(); r.value.retry(); await vi.advanceTimersByTimeAsync(0);
    d.resolve(response({ text: 23 })); await vi.advanceTimersByTimeAsync(0);
    expect(r.replies.map((v) => v.text)).toEqual(["current local reply"]);
    expect(r.value.state().phase).toBe("done"); expect(fetchMock).toHaveBeenCalledTimes(2);
  });
  it("C06 eight-second fallback and same-request late reply healing remain exact", async () => {
    const d = deferred<ReturnType<typeof response>>(); fetchMock.mockReturnValue(d.promise);
    const r = runner(); r.value.send(); await vi.advanceTimersByTimeAsync(NO_REPLY_MS);
    expect(r.value.state()).toMatchObject({ phase: "failed", reason: "no_reply" });
    expect((fetchMock.mock.calls[0][1] as RequestInit).signal?.aborted).toBe(false);
    await vi.advanceTimersByTimeAsync(1000); d.resolve(response({ text: "same request local late reply" }));
    await vi.advanceTimersByTimeAsync(0);
    expect(r.states.map((s) => s.phase)).toEqual(["sent", "failed", "done"]);
    expect(r.replies.at(-1)?.text).toBe("same request local late reply"); expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
