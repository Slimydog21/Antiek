// Typed client for GET/PUT /settings/privacy (OYM P1 §2 — privacy toggles).
//
// The surface list is the substrate's LIVE production registry
// (substrate/dp_shuffler/production.py) — never a local copy. The
// `enabled` flag is the user's stored preference resolved against the
// registry default (opt-in surfaces default OFF, everything else ON);
// forbidden surfaces (query_content_telemetry) are pinned OFF and the
// backend refuses to enable them.

import { API_BASE, apiFetch } from "../lib/api";

export type TelemetrySensitivity = "low" | "medium" | "high" | "forbidden";

export interface PrivacySurface {
  surface_name: string;
  sensitivity: TelemetrySensitivity;
  epsilon_per_day: number;
  opt_in_required: boolean;
  description: string;
  enabled: boolean;
  default_enabled: boolean;
}

export interface PrivacySettingsResponse {
  surfaces: PrivacySurface[];
  count: number;
}

export async function fetchPrivacySettings(): Promise<PrivacySettingsResponse> {
  const res = await apiFetch(`${API_BASE}/settings/privacy`);
  if (!res.ok) {
    throw new Error(`privacy settings API ${res.status}`);
  }
  return (await res.json()) as PrivacySettingsResponse;
}

export async function setPrivacySurface(
  surfaceName: string,
  enabled: boolean,
): Promise<PrivacySurface> {
  const res = await apiFetch(`${API_BASE}/settings/privacy`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ surface_name: surfaceName, enabled }),
  });
  if (!res.ok) {
    throw new Error(`privacy settings API ${res.status}`);
  }
  return (await res.json()) as PrivacySurface;
}
