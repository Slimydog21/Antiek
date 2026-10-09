import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createAudioModel, decodeAudioCatalog, decodeAudioDeletion, decodeAudioInventory, decodeAudioRecord, deleteAudioModel, disableAudioModel, fetchAudioCatalog, fetchAudioModels, type AudioModelDescriptor, type AudioModelRecord } from "./settingsAudioModels";

const descriptor: AudioModelDescriptor = { catalog_id: "openai", model_id: "whisper-1", adapter_kind: "audio_transcription", operation: "transcribe", endpoint: "https://api.openai.com", request_path: "/v1/audio/transcriptions" };
const row: AudioModelRecord = { id: "audio-aaaaaaaaaaaaaaaa-bbbbbbbbbbbbbbbb", display_name: "My audio", catalog_id: "openai", model_id: "whisper-1", endpoint: "https://api.openai.com", operation: "transcribe", enabled: true, registered: false, dispatch_authority: "unbound" };
const signal = () => new AbortController().signal;
function response(body: unknown, status = 200) { return new Response(status === 204 ? null : JSON.stringify(body), { status }); }
beforeEach(() => vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(response({ models: [] })))));
afterEach(() => vi.unstubAllGlobals());

describe("audio response contracts", () => {
  it("accepts only the audio descriptor and credential-free saved projection", () => {
    expect(decodeAudioCatalog({ models: [descriptor] })).toEqual([descriptor]);
    expect(decodeAudioInventory({ models: [row] })).toEqual([row]);
    expect(decodeAudioDeletion({ credential_removed: false })).toBe(false);
    expect(row.dispatch_authority).toBe("unbound");
  });
  it.each([
    { models: [{ ...descriptor, api_key: "unit-secret" }] },
    { models: [{ ...descriptor, adapter_kind: "openai_compat" }] },
    { models: [{ ...descriptor, endpoint: "https://wrong.example" }] },
    { models: [{ ...descriptor, request_path: "/chat/completions" }] },
    { models: [descriptor, descriptor] },
    { models: [descriptor], owner: "private" },
  ])("refuses an invalid or private catalog %j", (value) => expect(decodeAudioCatalog(value)).toBeNull());
  it.each([
    { ...row, api_key: "unit-secret" }, { ...row, credential_id: "private" }, { ...row, owner_user_id: "private" },
    { ...row, dispatch_authority: "ready" }, { ...row, enabled: "true" }, { ...row, registered: 1 },
    { ...row, id: "../other" }, { ...row, display_name: "" }, { ...row, display_name: "x".repeat(65) },
    { ...row, operation: "chat" }, { ...row, endpoint: "https://wrong.example" },
  ])("refuses a malformed or credential-bearing projection %j", (value) => expect(decodeAudioRecord(value)).toBeNull());
  it("refuses duplicate records and nonexact envelopes or deletion results", () => {
    expect(decodeAudioInventory({ models: [row, row] })).toBeNull();
    expect(decodeAudioInventory({ models: [row], stale_registered: [] })).toBeNull();
    expect(decodeAudioDeletion({ credential_removed: false, api_key: "unit-secret" })).toBeNull();
    expect(decodeAudioDeletion({ credential_removed: "yes" })).toBeNull();
  });
});
describe("real audio client transport", () => {
  it("uses existing cookie transport and the exact GET contracts with caller cancellation", async () => {
    const requests: { url: string; init: RequestInit | undefined }[] = [];
    vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) => { requests.push({ url, init }); return Promise.resolve(response({ models: url.endsWith("catalog") ? [descriptor] : [row] })); }));
    const abort = signal();
    expect(await fetchAudioCatalog(abort)).toEqual({ kind: "success", value: [descriptor] });
    expect(await fetchAudioModels(abort)).toEqual({ kind: "success", value: [row] });
    expect(requests.map((r) => r.url)).toEqual(["/settings/audio-models/catalog", "/settings/audio-models/user"]);
    for (const request of requests) { expect(request.init?.credentials).toBe("include"); expect(request.init?.signal).toBe(abort); }
  });
  it("sends exactly five fields and consumes the write-only reference before awaiting the response", async () => {
    let sent: unknown;
    vi.stubGlobal("fetch", vi.fn((_url: string, init?: RequestInit) => { sent = JSON.parse(String(init?.body)); return Promise.resolve(response(row, 201)); }));
    const credential = { value: "unit-audio-secret" };
    const result = createAudioModel(descriptor, row.display_name, credential, signal());
    expect(credential.value).toBe("");
    expect(sent).toEqual({ catalog_id: "openai", model_id: "whisper-1", endpoint: "https://api.openai.com", display_name: "My audio", api_key: "unit-audio-secret" });
    expect(await result).toEqual({ kind: "success", value: row });
  });
  it("refuses local key reflection before outbound work", async () => {
    const credential = { value: "unit-audio-secret" };
    expect(await createAudioModel(descriptor, "unit-audio-secret", credential, signal())).toEqual({ kind: "failure", reason: "validation" });
    expect(credential.value).toBe(""); expect(fetch).not.toHaveBeenCalled();
  });
  it("refuses a reflected or changed created display without exposing it", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(response({ ...row, display_name: "unit-audio-secret" }, 201))));
    expect(await createAudioModel(descriptor, "My audio", { value: "unit-audio-secret" }, signal())).toEqual({ kind: "unknown" });
  });
  it("sends only disable:false to the exact captured record and preserves false deletion", async () => {
    const requests: { url: string; method: string | undefined; body: unknown }[] = [];
    vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) => { requests.push({ url, method: init?.method, body: init?.body ? JSON.parse(String(init.body)) : null }); return Promise.resolve(init?.method === "PATCH" ? response(null, 204) : response({ credential_removed: false })); }));
    expect(await disableAudioModel(row.id, signal())).toEqual({ kind: "success", value: true });
    expect(await deleteAudioModel(row.id, signal())).toEqual({ kind: "success", value: false });
    expect(requests).toEqual([{ url: `/settings/audio-models/user/${row.id}`, method: "PATCH", body: { enabled: false } }, { url: `/settings/audio-models/user/${row.id}`, method: "DELETE", body: null }]);
  });
  it("refuses invalid record paths without a request", async () => {
    expect(await deleteAudioModel("../owner", signal())).toEqual({ kind: "failure", reason: "validation" }); expect(fetch).not.toHaveBeenCalled();
  });
  it.each([[401, "auth"], [404, "missing"], [422, "validation"], [503, "unavailable"]])("preserves HTTP %i as a value-free failure", async (status, reason) => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(response({ detail: "PRIVATE unit-secret" }, Number(status)))));
    expect(await fetchAudioModels(signal())).toEqual({ kind: "failure", reason });
  });
  it.each([true, false])("preserves publication cleanup confirmation %s", async (confirmed) => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(response({ detail: "audio publication unconfirmed", credential_cleanup_confirmed: confirmed }, 409))));
    expect(await createAudioModel(descriptor, "My audio", { value: "unit-secret" }, signal())).toEqual({ kind: "publication-unconfirmed", credentialCleanupConfirmed: confirmed });
  });
  it("treats malformed mutation replies and transport rejection as unknown without retry", async () => {
    const transport = vi.fn(() => Promise.resolve(new Response("not json", { status: 201 }))); vi.stubGlobal("fetch", transport);
    expect(await createAudioModel(descriptor, "My audio", { value: "unit-secret" }, signal())).toEqual({ kind: "unknown" }); expect(transport).toHaveBeenCalledTimes(1);
    transport.mockImplementation(() => Promise.reject(new Error("PRIVATE unit-secret")));
    expect(await deleteAudioModel(row.id, signal())).toEqual({ kind: "unknown" }); expect(transport).toHaveBeenCalledTimes(2);
  });
});
