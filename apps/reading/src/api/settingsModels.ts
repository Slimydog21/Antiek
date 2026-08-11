import { API_BASE, apiFetch } from "../lib/api";

// User-added model providers (Settings add-model vertical). The API key is
// WRITE-ONLY: it appears in AddUserModelRequest and nowhere else — inventory
// rows carry only a key_present flag, never key material.

export type ProviderKind = "openai_compat" | "anthropic";
export type RouteExecutionStatus =
  | "executable"
  | "blocked_unknown_pricing"
  | "blocked_idempotency_unproven"
  | "blocked_reconciliation_unproven"
  | "blocked_hidden_retries"
  | "blocked_provider_qualification"
  | "blocked_selection_authority"
  | "blocked_no_hard_ceiling_adapter"
  | "blocked_hard_ceiling_adapter_mismatch";

export interface SettingsModelCatalogModel {
  id: string;
  label: string;
  snapshot: string;
}

export interface SettingsModelCatalogProvider {
  catalog_id: string;
  display: string;
  provider_kind: ProviderKind;
  default_base_url: string;
  models: SettingsModelCatalogModel[];
  pricing_source: string;
}

export interface SettingsModelCatalogResponse {
  providers: SettingsModelCatalogProvider[];
  count: number;
}

export interface UserModelRow {
  id: string;
  provider_kind: ProviderKind;
  provider_catalog_id: string | null;
  model_id: string;
  display_name: string;
  base_url: string | null;
  enabled: boolean;
  key_present: boolean;
  registered: boolean;
  route_eligible: boolean;
  pricing_status: "known" | "unknown";
  hard_ceiling_eligible: boolean;
  execution_status: RouteExecutionStatus;
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
  provider_catalog_id?: string;
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
    // Response bodies can reflect malformed upstream input. Keep UI errors
    // value-free so a credential can never be copied into the page or logs.
    throw new Error(
      `Settings request failed (${res.status}). Check the fields and try again.`,
    );
  }
  return (await res.json()) as T;
}

export async function fetchUserModels(): Promise<UserModelsResponse> {
  const res = await apiFetch(`${API_BASE}/settings/models/user`);
  return readJson<UserModelsResponse>(res);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function nonEmptyString(value: unknown): value is string {
  return typeof value === "string" && value.length > 0;
}

function hasExactKeys(
  value: Record<string, unknown>,
  expected: readonly string[],
): boolean {
  const actual = Object.keys(value);
  return (
    actual.length === expected.length &&
    expected.every((key) => Object.prototype.hasOwnProperty.call(value, key))
  );
}

export function parseSettingsModelCatalog(
  raw: unknown,
): SettingsModelCatalogResponse {
  if (
    !isRecord(raw) ||
    !hasExactKeys(raw, ["providers", "count"]) ||
    !Array.isArray(raw.providers)
  ) {
    throw new Error("Invalid settings model catalog response.");
  }
  const providers = raw.providers.map(
    (provider): SettingsModelCatalogProvider => {
      if (
        !isRecord(provider) ||
        !hasExactKeys(provider, [
          "catalog_id",
          "display",
          "provider_kind",
          "default_base_url",
          "models",
          "pricing_source",
        ]) ||
        !nonEmptyString(provider.catalog_id) ||
        provider.catalog_id === "custom" ||
        !nonEmptyString(provider.display) ||
        (provider.provider_kind !== "openai_compat" &&
          provider.provider_kind !== "anthropic") ||
        !nonEmptyString(provider.default_base_url) ||
        !Array.isArray(provider.models) ||
        provider.models.length === 0 ||
        !nonEmptyString(provider.pricing_source)
      ) {
        throw new Error("Invalid settings model catalog response.");
      }
      const models = provider.models.map((model): SettingsModelCatalogModel => {
        if (
          !isRecord(model) ||
          !hasExactKeys(model, ["id", "label", "snapshot"]) ||
          !nonEmptyString(model.id) ||
          !nonEmptyString(model.label) ||
          !nonEmptyString(model.snapshot)
        ) {
          throw new Error("Invalid settings model catalog response.");
        }
        return { id: model.id, label: model.label, snapshot: model.snapshot };
      });
      if (new Set(models.map((model) => model.id)).size !== models.length) {
        throw new Error("Invalid settings model catalog response.");
      }
      return {
        catalog_id: provider.catalog_id,
        display: provider.display,
        provider_kind: provider.provider_kind,
        default_base_url: provider.default_base_url,
        models,
        pricing_source: provider.pricing_source,
      };
    },
  );
  if (
    typeof raw.count !== "number" ||
    !Number.isInteger(raw.count) ||
    raw.count !== providers.length ||
    new Set(providers.map((provider) => provider.catalog_id)).size !==
      providers.length
  ) {
    throw new Error("Invalid settings model catalog response.");
  }
  return { providers, count: raw.count };
}

export async function fetchSettingsModelCatalog(): Promise<SettingsModelCatalogResponse> {
  const res = await apiFetch(`${API_BASE}/settings/models/catalog`);
  return parseSettingsModelCatalog(await readJson<unknown>(res));
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
