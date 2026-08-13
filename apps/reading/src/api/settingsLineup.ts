/**
 * AI Role Lineup client — typed transport for /settings/lineup.
 *
 * Mirrors interfaces/research/api/settings_lineup.py one-to-one. The
 * lineup is the operator's model-selection surface: a general formation
 * (roles) + an advanced tactics board (per-action/behavior models).
 * Assignments are operator intent; the server re-validates every choice
 * against the live bench (user models + presets + dispatch tiers) and
 * never lets an unknown model through.
 */

import { API_BASE, apiFetch } from "../lib/api";

export type Position = "gk" | "def" | "mid" | "att";
export type ActionKind = "llm" | "media" | "voice" | "embedding";
export type BenchSource = "user_model" | "preset" | "dispatch";

export interface LineupChoice {
  provider_id: string;
  model_id: string;
}

export interface BenchModelView {
  provider_id: string;
  model_id: string;
  label: string;
  source: BenchSource;
  default_tier: string | null;
}

export interface ActionView {
  action_id: string;
  role_id: string;
  label: string;
  blurb: string;
  dispatch_role: string | null;
  default_tier: string | null;
  kind: ActionKind;
}

export interface RoleView {
  role_id: string;
  position: Position;
  label: string;
  blurb: string;
  discovered: boolean;
  actions: ActionView[];
}

export interface LineupResponse {
  version: number;
  general: RoleView[];
  advanced: ActionView[];
  bench: BenchModelView[];
  assignments: {
    general: Record<string, LineupChoice | null>;
    advanced: Record<string, LineupChoice | null>;
  };
  updated_at: string | null;
}

export interface LineupUpdate {
  general: Record<string, LineupChoice | null>;
  advanced: Record<string, LineupChoice | null>;
}

async function readJson<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = `${res.status}`;
    try {
      const body = (await res.json()) as { detail?: string };
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      /* keep status-only fallback */
    }
    throw new Error(detail);
  }
  return (await res.json()) as T;
}

export async function fetchLineup(): Promise<LineupResponse> {
  const res = await apiFetch(`${API_BASE}/settings/lineup`);
  return readJson<LineupResponse>(res);
}

export async function saveLineup(update: LineupUpdate): Promise<LineupResponse> {
  const res = await apiFetch(`${API_BASE}/settings/lineup`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(update),
  });
  return readJson<LineupResponse>(res);
}

/** Formation layout — role id → (x%, y%) on the pitch. */
export const FORMATION: Record<string, { x: number; y: number }> = {
  writer: { x: 30, y: 16 },
  media_creator: { x: 70, y: 16 },
  data_refinement: { x: 16, y: 42 },
  orchestrator: { x: 40, y: 47 },
  critic: { x: 60, y: 47 },
  voice: { x: 84, y: 42 },
  data_miner: { x: 25, y: 70 },
  indexer: { x: 75, y: 70 },
  data_verification: { x: 50, y: 88 },
};

/** Honest tier-strength badge: derived from the dispatch tier NAME, never
 *  a model-quality measurement. synthesis/verify = 9, pro = 8, flash = 6,
 *  presets/user models = 7 (unmeasured), auto = —. */
export function tierStrength(tier: string | null, source: BenchSource | null): number | null {
  if (tier === "synthesis" || tier === "verify") return 9;
  if (tier === "pro") return 8;
  if (tier === "flash") return 6;
  if (tier === "tts" || tier === "transcription") return 7;
  if (source === "preset" || source === "user_model") return 7;
  return null;
}
