/**
 * HTML-native view preference client (PR #801/#route).
 *
 * POST /assets/view-preference/decide
 */

import { API_BASE, apiFetch } from "../lib/api";

export type ViewMode = "html" | "pdf" | "metadata_only" | "unavailable";

export interface ViewPreferenceDecision {
  mode: ViewMode;
  preferred: boolean;
  reason: string;
  notes: string[];
}

export interface ViewPreferenceRequest {
  html_ready: boolean;
  pdf_available?: boolean;
  require_html?: boolean;
  asset_id?: string;
}

async function readJson<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`view-preference API ${res.status}: ${text.slice(0, 200)}`);
  }
  return (await res.json()) as T;
}

export async function decideViewPreference(
  req: ViewPreferenceRequest,
): Promise<ViewPreferenceDecision> {
  const res = await apiFetch(`${API_BASE}/assets/view-preference/decide`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      html_ready: req.html_ready,
      pdf_available: req.pdf_available ?? false,
      require_html: req.require_html ?? true,
      asset_id: req.asset_id ?? "",
    }),
  });
  return readJson<ViewPreferenceDecision>(res);
}

export function formatViewMode(mode: ViewMode): string {
  switch (mode) {
    case "html":
      return "HTML (preferred)";
    case "pdf":
      return "PDF fallback (not HTML-native preferred)";
    case "metadata_only":
      return "metadata only (PDF body blocked by HTML policy)";
    case "unavailable":
      return "unavailable";
    default:
      return String(mode);
  }
}
