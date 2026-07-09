/**
 * Midnight Oil API client — create → recommended ceiling → approve.
 * Mirrors interfaces/research/api/midnight_oil_routes.py
 * Deliverable view_format is always html (never PDF).
 */

import { API_BASE, apiFetch } from "../lib/api";

export type MidnightOilJobResponse = {
  job_id: string;
  goals: string[];
  duration_minutes: number;
  model_id?: string | null;
  status: string;
  recommended_price_ceiling_usd: number;
  approved_ceiling_usd?: number | null;
  force_below_recommended?: boolean;
  asset_id?: string | null;
  notes?: string;
  view_format: "html";
  runnable: boolean;
  html?: string;
};

async function readJson<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`midnight-oil API ${res.status}: ${text.slice(0, 200)}`);
  }
  return (await res.json()) as T;
}

export async function createMidnightOilJob(body: {
  goals: string[];
  duration_minutes: number;
  model_id?: string | null;
  fanout_depth?: number;
  asset_id?: string | null;
}): Promise<MidnightOilJobResponse> {
  const res = await apiFetch(`${API_BASE}/midnight-oil/create`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return readJson<MidnightOilJobResponse>(res);
}

export async function approveMidnightOilCeiling(body: {
  job_id: string;
  ceiling_usd?: number | null;
  use_recommended?: boolean;
  force_below?: boolean;
}): Promise<MidnightOilJobResponse> {
  const res = await apiFetch(`${API_BASE}/midnight-oil/approve`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return readJson<MidnightOilJobResponse>(res);
}

export async function getMidnightOilJob(
  jobId: string,
): Promise<MidnightOilJobResponse> {
  const res = await apiFetch(`${API_BASE}/midnight-oil/jobs/${encodeURIComponent(jobId)}`);
  return readJson<MidnightOilJobResponse>(res);
}
