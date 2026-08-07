import { API_BASE, apiFetch } from "../lib/api";

// User-added model providers (Settings add-model vertical). The API key is
// WRITE-ONLY: it appears in AddUserModelRequest and nowhere else — inventory
// rows carry only a key_present flag, never key material.

export type ProviderKind = "openai_compat" | "anthropic";
export type ProviderCatalogId =
  "deepseek" | "kimi" | "zhipu_glm" | "mimo" | "xai";

export interface UserModelRow {
  id: string;
  provider_kind: ProviderKind;
  provider_catalog_id: ProviderCatalogId | null;
  model_id: string;
  display_name: string;
  base_url: string | null;
  enabled: boolean;
  key_present: boolean;
  registered: boolean;
  route_eligible: boolean;
  pricing_status: "known" | "unknown";
  hard_ceiling_eligible: boolean;
  execution_status: string;
  rate_snapshot: string | null;
}

export interface UserModelsResponse {
  models: UserModelRow[];
  count: number;
  /** user-* names still live-registered whose registry record is gone
   *  (corrupt/lost file); they cannot resolve keys and clear at next boot. */
  stale_registered: string[];
  source: string;
}

export interface AddUserModelRequest {
  provider_kind: ProviderKind;
  provider_catalog_id?: ProviderCatalogId;
  model_id: string;
  display_name: string;
  api_key: string;
  base_url?: string;
}

export interface UserModelDeleteResponse {
  removed: string;
  notes: string[];
}

async function readJson<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`settings API ${res.status}: ${text.slice(0, 200)}`);
  }
  return (await res.json()) as T;
}

export async function fetchUserModels(): Promise<UserModelsResponse> {
  const res = await apiFetch(`${API_BASE}/settings/models/user`);
  return readJson<UserModelsResponse>(res);
}

export async function addUserModel(
  body: AddUserModelRequest,
): Promise<UserModelRow> {
  const res = await apiFetch(`${API_BASE}/settings/models/user`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return readJson<UserModelRow>(res);
}

export async function removeUserModel(
  id: string,
): Promise<UserModelDeleteResponse> {
  const res = await apiFetch(
    `${API_BASE}/settings/models/user/${encodeURIComponent(id)}`,
    { method: "DELETE" },
  );
  return readJson<UserModelDeleteResponse>(res);
}
