import { apiFetch } from "../lib/api";

export interface AudioModelDescriptor {
  catalog_id: "openai";
  model_id: "whisper-1";
  adapter_kind: "audio_transcription";
  operation: "transcribe";
  endpoint: "https://api.openai.com";
  request_path: "/v1/audio/transcriptions";
}
export interface AudioModelRecord {
  id: string;
  display_name: string;
  catalog_id: "openai";
  model_id: "whisper-1";
  endpoint: "https://api.openai.com";
  operation: "transcribe";
  enabled: boolean;
  registered: boolean;
  dispatch_authority: "unbound";
}
export type AudioFailure =
  | { kind: "failure"; reason: "auth" | "missing" | "validation" | "unavailable" | "protocol" }
  | { kind: "publication-unconfirmed"; credentialCleanupConfirmed: boolean }
  | { kind: "unknown" };
export type AudioResult<T> = { kind: "success"; value: T } | AudioFailure;
export interface WriteOnlyAudioCredential { value: string }

function object(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
function exact(value: Record<string, unknown>, keys: readonly string[]): boolean {
  return Object.keys(value).length === keys.length && keys.every((key) => Object.hasOwn(value, key));
}
export function decodeAudioCatalog(value: unknown): AudioModelDescriptor[] | null {
  if (!object(value) || !exact(value, ["models"]) || !Array.isArray(value.models) || value.models.length > 1) return null;
  const models: AudioModelDescriptor[] = [];
  for (const item of value.models) {
    if (!object(item) || !exact(item, ["catalog_id", "model_id", "adapter_kind", "operation", "endpoint", "request_path"])
      || item.catalog_id !== "openai" || item.model_id !== "whisper-1" || item.adapter_kind !== "audio_transcription"
      || item.operation !== "transcribe" || item.endpoint !== "https://api.openai.com" || item.request_path !== "/v1/audio/transcriptions") return null;
    models.push({ catalog_id: item.catalog_id, model_id: item.model_id, adapter_kind: item.adapter_kind,
      operation: item.operation, endpoint: item.endpoint, request_path: item.request_path });
  }
  return models;
}
export function decodeAudioRecord(value: unknown): AudioModelRecord | null {
  if (!object(value) || !exact(value, ["id", "display_name", "catalog_id", "model_id", "endpoint", "operation", "enabled", "registered", "dispatch_authority"])
    || typeof value.id !== "string" || !/^audio-[a-f0-9]{16}-[a-f0-9]{16}$/.test(value.id)
    || typeof value.display_name !== "string" || value.display_name.length < 1 || value.display_name.length > 64
    || value.catalog_id !== "openai" || value.model_id !== "whisper-1" || value.endpoint !== "https://api.openai.com"
    || value.operation !== "transcribe" || typeof value.enabled !== "boolean" || typeof value.registered !== "boolean"
    || value.dispatch_authority !== "unbound") return null;
  return { id: value.id, display_name: value.display_name, catalog_id: value.catalog_id, model_id: value.model_id,
    endpoint: value.endpoint, operation: value.operation, enabled: value.enabled, registered: value.registered, dispatch_authority: value.dispatch_authority };
}
export function decodeAudioInventory(value: unknown): AudioModelRecord[] | null {
  if (!object(value) || !exact(value, ["models"]) || !Array.isArray(value.models) || value.models.length > 128) return null;
  const models: AudioModelRecord[] = [];
  const ids = new Set<string>();
  for (const item of value.models) {
    const record = decodeAudioRecord(item);
    if (!record || ids.has(record.id)) return null;
    ids.add(record.id); models.push(record);
  }
  return models;
}
export function decodeAudioDeletion(value: unknown): boolean | null {
  return object(value) && exact(value, ["credential_removed"]) && typeof value.credential_removed === "boolean" ? value.credential_removed : null;
}

async function consume<T>(pending: Promise<Response>, status: number, mutation: boolean, decode: (value: unknown) => T | null): Promise<AudioResult<T>> {
  try {
    const response = await pending;
    if (response.status === status) {
      const value: unknown = status === 204 ? null : await response.json();
      const decoded = decode(value);
      return decoded === null ? (mutation ? { kind: "unknown" } : { kind: "failure", reason: "protocol" }) : { kind: "success", value: decoded };
    }
    if (response.status === 409) {
      const value: unknown = await response.json();
      if (object(value) && exact(value, ["detail", "credential_cleanup_confirmed"])
        && value.detail === "audio publication unconfirmed" && typeof value.credential_cleanup_confirmed === "boolean") {
        return { kind: "publication-unconfirmed", credentialCleanupConfirmed: value.credential_cleanup_confirmed };
      }
      return { kind: "unknown" };
    }
    if (response.status === 401) return { kind: "failure", reason: "auth" };
    if (response.status === 404) return { kind: "failure", reason: "missing" };
    if (response.status === 422 || response.status === 413) return { kind: "failure", reason: "validation" };
    if (response.status === 503) return mutation ? { kind: "unknown" } : { kind: "failure", reason: "unavailable" };
    return mutation ? { kind: "unknown" } : { kind: "failure", reason: "unavailable" };
  } catch { return mutation ? { kind: "unknown" } : { kind: "failure", reason: "unavailable" }; }
}
function request<T>(path: string, init: RequestInit, status: number, mutation: boolean, decode: (value: unknown) => T | null): Promise<AudioResult<T>> {
  try {
    const pending = apiFetch(path, init);
    // Fetch consumes the body synchronously. Do not retain the write-only body in our own options across an await.
    init.body = undefined;
    return consume(pending, status, mutation, decode);
  } catch { init.body = undefined; return Promise.resolve(mutation ? { kind: "unknown" } : { kind: "failure", reason: "unavailable" }); }
}
export function fetchAudioCatalog(signal: AbortSignal): Promise<AudioResult<AudioModelDescriptor[]>> {
  return request("/settings/audio-models/catalog", { signal }, 200, false, decodeAudioCatalog);
}
export function fetchAudioModels(signal: AbortSignal): Promise<AudioResult<AudioModelRecord[]>> {
  return request("/settings/audio-models/user", { signal }, 200, false, decodeAudioInventory);
}
export function createAudioModel(descriptor: AudioModelDescriptor, displayName: string, credential: WriteOnlyAudioCredential, signal: AbortSignal): Promise<AudioResult<AudioModelRecord>> {
  let key = credential.value;
  credential.value = "";
  if (!decodeAudioCatalog({ models: [descriptor] }) || displayName.length < 1 || displayName.length > 64 || key.length < 8 || key.length > 512
    || displayName.includes(key) || `${descriptor.endpoint} ${descriptor.model_id} ${descriptor.catalog_id}`.includes(key)) {
    key = ""; return Promise.resolve({ kind: "failure", reason: "validation" });
  }
  const init: RequestInit = { method: "POST", signal, headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ catalog_id: descriptor.catalog_id, model_id: descriptor.model_id, endpoint: descriptor.endpoint, display_name: displayName, api_key: key }) };
  key = "";
  return request("/settings/audio-models/user", init, 201, true, (value) => {
    const record = decodeAudioRecord(value);
    return record?.display_name === displayName ? record : null;
  });
}
export function disableAudioModel(id: string, signal: AbortSignal): Promise<AudioResult<true>> {
  if (!/^audio-[a-f0-9]{16}-[a-f0-9]{16}$/.test(id)) return Promise.resolve({ kind: "failure", reason: "validation" });
  return request(`/settings/audio-models/user/${encodeURIComponent(id)}`, { method: "PATCH", signal, headers: { "Content-Type": "application/json" }, body: JSON.stringify({ enabled: false }) }, 204, true, () => true);
}
export function deleteAudioModel(id: string, signal: AbortSignal): Promise<AudioResult<boolean>> {
  if (!/^audio-[a-f0-9]{16}-[a-f0-9]{16}$/.test(id)) return Promise.resolve({ kind: "failure", reason: "validation" });
  return request(`/settings/audio-models/user/${encodeURIComponent(id)}`, { method: "DELETE", signal }, 200, true, decodeAudioDeletion);
}
