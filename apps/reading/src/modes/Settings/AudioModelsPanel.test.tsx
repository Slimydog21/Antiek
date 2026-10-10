import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import AudioModelsPanel from "./AudioModelsPanel";
import { beforeWorkspaceOwnerChange, resumeWorkspaceOwner, setWorkspaceOwner, subscribeWorkspaceOwnerAdmission, suspendWorkspaceOwner, workspaceOwnerSession } from "../../lib/accountWorkspaceOwner";
import type { AudioModelDescriptor, AudioModelRecord } from "../../api/settingsAudioModels";

const A = "acct_" + "a".repeat(32), B = "acct_" + "b".repeat(32);
const descriptor: AudioModelDescriptor = { catalog_id: "openai", model_id: "whisper-1", adapter_kind: "audio_transcription", operation: "transcribe", endpoint: "https://api.openai.com", request_path: "/v1/audio/transcriptions" };
const row: AudioModelRecord = { id: "audio-aaaaaaaaaaaaaaaa-bbbbbbbbbbbbbbbb", display_name: "My audio", catalog_id: "openai", model_id: "whisper-1", endpoint: "https://api.openai.com", operation: "transcribe", enabled: true, registered: true, dispatch_authority: "unbound" };
interface Request { url: string; method: string; body: unknown; signal: AbortSignal | null | undefined; owner: string | null }
let requests: Request[];
let inventory: AudioModelRecord[];
let onRequest: (request: Request) => Promise<Response>;
function response(body: unknown, status = 200) { return new Response(status === 204 ? null : JSON.stringify(body), { status }); }
function deferred<T>() { let resolve: (value: T) => void = () => {}; const promise = new Promise<T>((done) => { resolve = done; }); return { promise, resolve }; }
function input(label: string): HTMLInputElement {
  const node = screen.getByLabelText(label); if (!(node instanceof HTMLInputElement)) throw new Error("Expected input fixture"); return node;
}
async function loaded() { await screen.findByText("No saved audio models."); }
function form() { const node = screen.getByRole("form", { name: "Add audio model" }); if (!(node instanceof HTMLFormElement)) throw new Error("Expected form"); return node; }
function fill() {
  fireEvent.change(screen.getByLabelText("Audio model"), { target: { value: "openai:whisper-1" } });
  fireEvent.change(input("Audio display name"), { target: { value: "My audio" } });
  fireEvent.change(input("Audio API key"), { target: { value: "unit-audio-secret" } });
}
beforeEach(() => {
  setWorkspaceOwner(A); requests = []; inventory = [];
  onRequest = (request) => {
    if (request.method === "GET") return Promise.resolve(response({ models: request.url.endsWith("catalog") ? [descriptor] : inventory }));
    if (request.method === "POST") return Promise.resolve(response(row, 201));
    if (request.method === "PATCH") return Promise.resolve(response(null, 204));
    return Promise.resolve(response({ credential_removed: true }));
  };
  vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) => {
    const request = { url, method: init?.method ?? "GET", body: init?.body ? JSON.parse(String(init.body)) : null, signal: init?.signal, owner: workspaceOwnerSession().subject };
    requests.push(request); return onRequest(request);
  }));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); setWorkspaceOwner(null); });

describe("real normal-account audio Settings", () => {
  it("requires explicit audio choice, submits one exact key, then disables and removes its owned record", async () => {
    render(<AudioModelsPanel />); await loaded();
    expect(screen.getByLabelText("Audio model").getAttribute("value")).toBeNull();
    fill(); fireEvent.submit(form());
    expect(input("Audio API key").value).toBe("");
    await screen.findByText("Audio model saved. Transcription availability is not confirmed.");
    expect(requests.find((r) => r.method === "POST")?.body).toEqual({ catalog_id: "openai", model_id: "whisper-1", endpoint: "https://api.openai.com", display_name: "My audio", api_key: "unit-audio-secret" });
    expect(document.body.textContent).not.toContain("unit-audio-secret");
    fireEvent.click(screen.getByRole("button", { name: "Disable My audio" })); await screen.findByText("Audio model disabled.");
    expect(screen.getByText(/Whisper · Disabled · Registration unavailable/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Remove My audio" })); await screen.findByText("Audio model removed; credential removal confirmed.");
    expect(screen.getByText("No saved audio models.")).toBeTruthy();
    expect(requests.map((r) => r.method)).toEqual(["GET", "GET", "POST", "PATCH", "DELETE"]);
  });
  it.each([null, "__operator__", "unit-test-owner"])("does no private I/O for inadmissible subject %s", (subject) => {
    setWorkspaceOwner(subject); render(<AudioModelsPanel />); expect(screen.getByText(/Sign in with a verified normal account/)).toBeTruthy(); expect(requests).toEqual([]);
  });
  it("holds same-token inventory and nonsecret draft through suspension without outbound work", async () => {
    inventory = [row]; render(<AudioModelsPanel />); await screen.findByText("My audio"); fill();
    const owner = workspaceOwnerSession(); const calls = requests.length;
    act(() => suspendWorkspaceOwner());
    expect(screen.queryByText("My audio")).toBeNull(); expect(screen.queryByLabelText("Audio API key")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Refresh audio models" })); expect(requests.length).toBe(calls);
    await act(async () => { expect(resumeWorkspaceOwner(owner)).toBe(true); });
    expect(workspaceOwnerSession()).toBe(owner); expect(input("Audio display name").value).toBe("My audio"); expect(input("Audio API key").value).toBe(""); expect(screen.getByText("My audio")).toBeTruthy(); expect(requests.length).toBe(calls);
  });
  it("retains one in-flight success until the same token is confirmed, without resubmission", async () => {
    const gate = deferred<Response>(); onRequest = (r) => r.method === "POST" ? gate.promise : Promise.resolve(response({ models: r.url.endsWith("catalog") ? [descriptor] : [] }));
    render(<AudioModelsPanel />); await loaded(); fill(); fireEvent.submit(form()); await waitFor(() => expect(requests.filter((r) => r.method === "POST")).toHaveLength(1));
    const owner = workspaceOwnerSession(); act(() => suspendWorkspaceOwner()); await act(async () => gate.resolve(response(row, 201)));
    expect(screen.queryByText(/Audio model saved/)).toBeNull(); await act(async () => { resumeWorkspaceOwner(owner); });
    await screen.findByText(/Audio model saved/); expect(requests.filter((r) => r.method === "POST")).toHaveLength(1);
  });
  it("refuses replacement and A-B-A old completions, clears secret and aborts the originating request", async () => {
    const gate = deferred<Response>(); onRequest = (r) => r.method === "POST" ? gate.promise : Promise.resolve(response({ models: r.url.endsWith("catalog") ? [descriptor] : [] }));
    render(<AudioModelsPanel />); await loaded(); fill(); const oldKey = input("Audio API key"); fireEvent.submit(form()); await waitFor(() => expect(requests.some((r) => r.method === "POST")).toBe(true));
    const oldPost = requests.find((r) => r.method === "POST");
    await act(async () => { setWorkspaceOwner(B); setWorkspaceOwner(A); });
    expect(oldKey.value).toBe(""); expect(oldPost?.signal?.aborted).toBe(true);
    await act(async () => gate.resolve(response(row, 201))); await loaded(); expect(screen.queryByText("My audio")).toBeNull(); expect(screen.queryByText(/Audio model saved/)).toBeNull();
  });
  it("refuses a retained old button synchronously at account replacement", async () => {
    inventory = [row]; render(<AudioModelsPanel />); await screen.findByText("My audio");
    const oldButton = screen.getByRole("button", { name: "Remove My audio" });
    await act(async () => { setWorkspaceOwner(B); fireEvent.click(oldButton); });
    expect(requests.filter((r) => r.method === "DELETE")).toHaveLength(0);
  });
  it("refuses failed retirement and clears private presentation before late completion", async () => {
    const gate = deferred<Response>(); onRequest = (r) => r.method === "POST" ? gate.promise : Promise.resolve(response({ models: r.url.endsWith("catalog") ? [descriptor] : [] }));
    render(<AudioModelsPanel />); await loaded(); fill(); fireEvent.submit(form()); await waitFor(() => expect(requests.some((r) => r.method === "POST")).toBe(true));
    const stop = beforeWorkspaceOwnerChange(() => { throw new Error("UNIT retirement refusal"); });
    try { act(() => expect(() => setWorkspaceOwner(B)).toThrow("UNIT retirement refusal")); await act(async () => gate.resolve(response(row, 201))); expect(screen.queryByText(/Audio model saved/)).toBeNull(); expect(screen.queryByRole("form")).toBeNull(); }
    finally { stop(); }
  });
  it("checks final confirmation when a later ready observer fails", async () => {
    const gate = deferred<Response>(); onRequest = (r) => r.method === "POST" ? gate.promise : Promise.resolve(response({ models: r.url.endsWith("catalog") ? [descriptor] : [] }));
    render(<AudioModelsPanel />); await loaded(); fill(); fireEvent.submit(form()); await waitFor(() => expect(requests.some((r) => r.method === "POST")).toBe(true));
    const owner = workspaceOwnerSession(); act(() => suspendWorkspaceOwner()); await act(async () => gate.resolve(response(row, 201)));
    const stop = subscribeWorkspaceOwnerAdmission((a) => { if (a.state === "ready") throw new Error("UNIT confirmation refusal"); });
    try { await act(async () => { expect(() => resumeWorkspaceOwner(owner)).toThrow("UNIT confirmation refusal"); }); expect(screen.queryByText(/Audio model saved/)).toBeNull(); }
    finally { stop(); }
  });
  it("refuses unmounted late completion and retires key and request ownership", async () => {
    const gate = deferred<Response>(); onRequest = (r) => r.method === "POST" ? gate.promise : Promise.resolve(response({ models: r.url.endsWith("catalog") ? [descriptor] : [] }));
    const { unmount } = render(<AudioModelsPanel />); await loaded(); fill(); const key = input("Audio API key"); fireEvent.submit(form()); await waitFor(() => expect(requests.some((r) => r.method === "POST")).toBe(true));
    unmount(); expect(key.value).toBe(""); expect(requests.find((r) => r.method === "POST")?.signal?.aborted).toBe(true);
    await act(async () => gate.resolve(response(row, 201))); expect(screen.queryByText(/Audio model saved/)).toBeNull();
  });
  it("deduplicates submission and refuses a competing refresh while the resource ticket is held", async () => {
    const gate = deferred<Response>(); onRequest = (r) => r.method === "POST" ? gate.promise : Promise.resolve(response({ models: r.url.endsWith("catalog") ? [descriptor] : [] }));
    render(<AudioModelsPanel />); await loaded(); fill(); const node = form(); fireEvent.submit(node); fireEvent.submit(node); fireEvent.click(screen.getByRole("button", { name: "Refresh audio models" }));
    await waitFor(() => expect(requests.filter((r) => r.method === "POST")).toHaveLength(1)); expect(requests.filter((r) => r.method === "GET")).toHaveLength(2);
    await act(async () => gate.resolve(response(row, 201))); await screen.findByText(/Audio model saved/);
  });
  it("rechecks the owner before the second GET after a synchronous first-response transition", async () => {
    let replaced = false; onRequest = (r) => { if (!replaced) { replaced = true; setWorkspaceOwner(B); } return Promise.resolve(response({ models: r.url.endsWith("catalog") ? [descriptor] : [] })); };
    render(<AudioModelsPanel />); await loaded(); expect(requests.filter((r) => r.owner === A && r.url.endsWith("/user"))).toHaveLength(0);
  });
  it.each([401, 404, 422, 503])("renders honest read failure %s rather than Empty or private error text", async (status) => {
    onRequest = () => Promise.resolve(response({ detail: "PRIVATE unit-audio-secret" }, status)); render(<AudioModelsPanel />); await screen.findByRole("alert");
    expect(screen.queryByText("No saved audio models.")).toBeNull(); expect(document.body.textContent).not.toContain("PRIVATE"); expect(document.body.textContent).not.toContain("unit-audio-secret");
  });
  it("preserves unconfirmed credential cleanup and uses a read-only refresh", async () => {
    inventory = [row]; onRequest = (r) => Promise.resolve(r.method === "DELETE" ? response({ credential_removed: false }) : response({ models: r.url.endsWith("catalog") ? [descriptor] : inventory }));
    render(<AudioModelsPanel />); await screen.findByText("My audio"); fireEvent.click(screen.getByRole("button", { name: "Remove My audio" })); await screen.findByText(/Credential cleanup is unconfirmed/);
    fireEvent.click(screen.getByRole("button", { name: "Refresh audio models" })); await screen.findByText("My audio"); expect(requests.map((r) => r.method)).toEqual(["GET", "GET", "DELETE", "GET", "GET"]);
  });
  it("makes an ambiguous mutation explicit, blocks resubmission and clears key without auto retry", async () => {
    onRequest = (r) => r.method === "POST" ? Promise.reject(new Error("PRIVATE unit-audio-secret")) : Promise.resolve(response({ models: r.url.endsWith("catalog") ? [descriptor] : [] }));
    render(<AudioModelsPanel />); await loaded(); fill(); fireEvent.submit(form()); await screen.findByText(/The change could not be confirmed/);
    fireEvent.submit(form()); expect(requests.filter((r) => r.method === "POST")).toHaveLength(1); expect(input("Audio API key").value).toBe(""); expect(document.body.textContent).not.toContain("PRIVATE");
  });
  it.each([true, false])("renders publication-unconfirmed with cleanup %s separately", async (confirmed) => {
    onRequest = (r) => r.method === "POST" ? Promise.resolve(response({ detail: "audio publication unconfirmed", credential_cleanup_confirmed: confirmed }, 409)) : Promise.resolve(response({ models: r.url.endsWith("catalog") ? [descriptor] : [] }));
    render(<AudioModelsPanel />); await loaded(); fill(); fireEvent.submit(form()); await screen.findByText(confirmed ? /Credential cleanup was confirmed/ : /Credential cleanup is unconfirmed/); expect(screen.queryByText("My audio")).toBeNull();
  });
});

describe("503 successor: real panel mutation uncertainty", () => {
  it("503 successor: committed create clears the key, refuses retained submission and refreshes by GET only", async () => {
    onRequest = (request) => {
      if (request.method === "POST") { inventory = [row]; return Promise.resolve(response({ detail: "PRIVATE unit-audio-secret" }, 503)); }
      return Promise.resolve(response({ models: request.url.endsWith("catalog") ? [descriptor] : inventory }));
    };
    render(<AudioModelsPanel />); await loaded(); fill();
    const retainedForm = form(); const retainedSave = screen.getByRole("button", { name: "Save audio model" });
    fireEvent.submit(retainedForm); expect(input("Audio API key").value).toBe("");
    await screen.findByText(/The change could not be confirmed/);
    expect(retainedSave.matches(":disabled")).toBe(true);
    fireEvent.submit(retainedForm); fireEvent.click(retainedSave);
    expect(requests.map((request) => request.method)).toEqual(["GET", "GET", "POST"]);
    expect(screen.queryByText("My audio")).toBeNull();
    expect(document.body.textContent).not.toContain("unit-audio-secret");
    expect(document.body.textContent).not.toContain("PRIVATE");
    fireEvent.click(screen.getByRole("button", { name: "Refresh audio models" })); await screen.findByText("My audio");
    expect(requests.map((request) => request.method)).toEqual(["GET", "GET", "POST", "GET", "GET"]);
    expect(input("Audio API key").value).toBe("");
    expect(screen.queryByText(/The change could not be confirmed/)).toBeNull();
  });
  it.each(["PATCH", "DELETE"])("503 successor: committed %s blocks the retained button until a GET-only refresh", async (method) => {
    inventory = [row];
    onRequest = (request) => {
      if (request.method === method) {
        inventory = method === "PATCH" ? [{ ...row, enabled: false, registered: false }] : [];
        return Promise.resolve(response({ detail: "PRIVATE unit-audio-secret" }, 503));
      }
      return Promise.resolve(response({ models: request.url.endsWith("catalog") ? [descriptor] : inventory }));
    };
    render(<AudioModelsPanel />); await screen.findByText("My audio");
    const retainedButton = screen.getByRole("button", { name: method === "PATCH" ? "Disable My audio" : "Remove My audio" });
    fireEvent.click(retainedButton); await screen.findByText(/The change could not be confirmed/);
    expect(retainedButton.matches(":disabled")).toBe(true); fireEvent.click(retainedButton);
    expect(requests.map((request) => request.method)).toEqual(["GET", "GET", method]);
    expect(document.body.textContent).not.toContain("PRIVATE");
    fireEvent.click(screen.getByRole("button", { name: "Refresh audio models" }));
    if (method === "PATCH") await screen.findByText(/Whisper · Disabled · Registration unavailable/);
    else await screen.findByText("No saved audio models.");
    expect(requests.map((request) => request.method)).toEqual(["GET", "GET", method, "GET", "GET"]);
    expect(screen.queryByText(/The change could not be confirmed/)).toBeNull();
  });
});
