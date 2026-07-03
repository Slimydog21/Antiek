/**
 * Krea scene-art client (Mountain Shell SPR-02).
 *
 * The ONLY thing the browser uses to ask for generated "scene art" for the
 * living mountain background (SPR-04). It talks EXCLUSIVELY to the backend
 * `/krea/*` proxy (interfaces/research/api/krea_routes.py) — it NEVER sees,
 * holds, or references the Krea API key. The key lives server-side only
 * (INV-2): the server-side bearer-token env var (read in krea_routes.py) never
 * appears in this bundle, so grepping the frontend src for it returns zero.
 *
 * Matches the shared client idiom in lib/api.ts (`apiFetch` carries the
 * Cloudflare Access cookie cross-origin; `API_BASE` is same-origin in dev
 * via the Vite proxy, explicit in prod). Mirrors api/tts.ts's treatment of
 * a 503 as a typed "unavailable / fallback" state rather than a thrown
 * network error.
 *
 * HONESTY: the `/krea/scene` request/response shapes below mirror the
 * backend route, whose Krea wire shape is docs-current as of 2026-06-12
 * (transcribed from docs.krea.ai; live verification pending the SPR-09
 * capped smoke — no live Krea call has ever been made). The server's
 * contract (200 SceneArt | 503 DisabledResponse) is what this client
 * codes against and is stable regardless of the live Krea schema.
 */

import { API_BASE, apiFetch } from "../lib/api";

/** Scene-state the background is requesting art for. These three axes are
 *  the cache key on the server AND the deterministic-placeholder key in
 *  the hook, so they must agree. SPR-04 supplies them. */
export interface SceneState {
  mood: string;
  /** "day" | "night" (free string; server normalizes). */
  dayNight: string;
  season: string;
}

/** The happy-path art payload (HTTP 200 from /krea/scene). */
export interface SceneArt {
  enabled: true;
  isFallback: false;
  /** The generated background image URL. */
  image_url: string;
  /** Server-normalized scene-state key (e.g. "calm|day|summer"). */
  scene_key: string;
  /** True when the server served this from its warm TTL cache (no bill). */
  cached: boolean;
}

/** The typed FALLBACK signal (HTTP 503 from /krea/*). Returned for EVERY
 *  disabled / failure mode: no key, kill-switch, over-budget, rate-limited,
 *  upstream error/timeout/bad-json, job failed/timeout/cancelled, empty
 *  prepaid API balance. The hook turns any of these into
 *  `isFallback: true` + a deterministic placeholder. This is NOT an error
 *  to throw — it is an expected, handled state. */
export interface SceneDisabled {
  enabled: false;
  isFallback: true;
  /** Stable machine reason. The vocabulary is ADDITIVE-ONLY (existing
   *  strings never change; new failure modes get new strings): "no_key",
   *  "kill_switch", "over_daily_budget", "rate_limited", "upstream_error",
   *  "upstream_timeout", "upstream_bad_response", "job_failed",
   *  "job_timeout", plus (added 2026-06-12, SPR-01) "job_cancelled" — the
   *  job reached Krea's terminal cancelled state — and "no_api_balance" —
   *  upstream HTTP 402: Krea's prepaid API balance (separate from any
   *  subscription) is empty and needs a top-up. */
  reason: string;
  /** The scene-state key when the server knew it; lets the caller keep a
   *  stable placeholder keyed to the same state. May be null. */
  scene_key?: string | null;
}

/** Discriminated on `enabled`: art (true) vs the fallback signal (false). */
export type SceneResult = SceneArt | SceneDisabled;

/** Submit/poll shapes (lower-level; SPR-04 mostly uses requestScene). */
export interface GenerateResult {
  enabled: true;
  job_id: string;
  status: string;
}

export interface JobResult {
  enabled: true;
  job_id: string;
  status: string;
  image_url?: string | null;
  /** Stable machine code from a failed job's error object (additive,
   *  2026-06-12). The upstream error MESSAGE is never forwarded. */
  error_code?: string | null;
}

export type GenerateResponse = GenerateResult | SceneDisabled;
export type JobResponse = JobResult | SceneDisabled;

export interface KreaFailureEntry {
  timestamp: string;
  reason: string;
  scene_key?: string | null;
  upstream_status?: number | null;
}

export interface KreaStatusSnapshot {
  enabled: boolean;
  key_present: boolean;
  kill_switch: boolean;
  gate_verdict: string | null;
  reasons: string[];
  budget: {
    spent_today: number;
    cap: number;
    remaining: number;
  };
  rate_window: {
    occupancy: number;
    max: number;
    window_s: number;
  };
  cache: {
    entries: number;
    max_entries: number;
  };
  last_success_at: string | null;
  failure_counts: Record<string, number>;
  failures: KreaFailureEntry[];
}

/** Build the query string for a scene request. */
function sceneQuery(scene: SceneState): string {
  const p = new URLSearchParams({
    mood: scene.mood,
    day_night: scene.dayNight,
    season: scene.season,
  });
  return p.toString();
}

/**
 * Request scene art for a scene-state. Resolves to EITHER `SceneArt`
 * (200) OR the typed `SceneDisabled` fallback signal (503). It does NOT
 * throw on a 503 — a disabled/over-budget/offline backend is an expected
 * state the hook renders a placeholder for. It only throws on a genuinely
 * unexpected non-200/non-503 response (so a real bug is not swallowed).
 */
export async function requestScene(scene: SceneState): Promise<SceneResult> {
  let resp: Response;
  try {
    resp = await apiFetch(`${API_BASE}/krea/scene?${sceneQuery(scene)}`);
  } catch {
    // Network failure (offline) — synthesize the fallback signal so the
    // caller never sees a throw. Keyed nothing (server never answered).
    return {
      enabled: false,
      isFallback: true,
      reason: "offline",
      scene_key: null,
    };
  }
  if (resp.status === 503) {
    // The typed disabled/fallback body.
    return (await safeJson<SceneDisabled>(resp)) ?? {
      enabled: false,
      isFallback: true,
      reason: "upstream_bad_response",
      scene_key: null,
    };
  }
  if (resp.ok) {
    const art = await safeJson<SceneArt>(resp);
    if (art && typeof art.image_url === "string" && art.image_url) {
      return { ...art, enabled: true, isFallback: false } as SceneArt;
    }
    // 200 but unparseable / missing image — treat as fallback, not a crash.
    return {
      enabled: false,
      isFallback: true,
      reason: "upstream_bad_response",
      scene_key: null,
    };
  }
  // Any other status is genuinely unexpected — surface it.
  throw new Error(`GET /krea/scene failed: HTTP ${resp.status}`);
}

/** Submit a raw generation (lower-level; SPR-04 usually uses requestScene).
 *  503 → typed fallback signal; success → {job_id,status}.
 *
 *  NOTE (2026-06-12, SPR-01): `opts.model` is IGNORED by the server — per
 *  docs.krea.ai the model is a URL path segment, selected server-side via
 *  the ANTIEK_KREA_MODEL_PATH env (default bfl/flux-1-dev), never a body
 *  field. The option is kept so older callers keep compiling; the server
 *  drops unknown body keys. Server-enforced bounds (docs.krea.ai
 *  flux-1-dev, 2026-06-12): prompt ≤ 1800 chars, width/height 512–2368 px
 *  — out-of-bounds gets a 422 naming the bound. */
export async function generateImage(
  prompt: string,
  opts?: { model?: string; width?: number; height?: number },
): Promise<GenerateResponse> {
  let resp: Response;
  try {
    resp = await apiFetch(`${API_BASE}/krea/generate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ prompt, ...opts }),
    });
  } catch {
    return { enabled: false, isFallback: true, reason: "offline", scene_key: null };
  }
  if (resp.status === 503) {
    return (await safeJson<SceneDisabled>(resp)) ?? {
      enabled: false, isFallback: true, reason: "upstream_bad_response",
      scene_key: null,
    };
  }
  if (resp.ok) {
    const body = await safeJson<GenerateResult>(resp);
    if (body && typeof body.job_id === "string") {
      return { ...body, enabled: true };
    }
    return {
      enabled: false, isFallback: true, reason: "upstream_bad_response",
      scene_key: null,
    };
  }
  throw new Error(`POST /krea/generate failed: HTTP ${resp.status}`);
}

/** Poll a submitted job. 503 → typed fallback signal. */
export async function getJob(jobId: string): Promise<JobResponse> {
  let resp: Response;
  try {
    resp = await apiFetch(`${API_BASE}/krea/jobs/${encodeURIComponent(jobId)}`);
  } catch {
    return { enabled: false, isFallback: true, reason: "offline", scene_key: null };
  }
  if (resp.status === 503) {
    return (await safeJson<SceneDisabled>(resp)) ?? {
      enabled: false, isFallback: true, reason: "upstream_bad_response",
      scene_key: null,
    };
  }
  if (resp.ok) {
    const body = await safeJson<JobResult>(resp);
    if (body && typeof body.job_id === "string") {
      return { ...body, enabled: true };
    }
    return {
      enabled: false, isFallback: true, reason: "upstream_bad_response",
      scene_key: null,
    };
  }
  throw new Error(`GET /krea/jobs/{id} failed: HTTP ${resp.status}`);
}

/** Read the Krea observability surface. This route is always HTTP 200 when
 *  reachable, including disabled/no-key states. Network failures throw so the
 *  caller can distinguish "status unavailable" from "Krea disabled". */
export async function getKreaStatus(): Promise<KreaStatusSnapshot> {
  const resp = await apiFetch(`${API_BASE}/krea/status`);
  if (!resp.ok) {
    throw new Error(`GET /krea/status failed: HTTP ${resp.status}`);
  }
  return (await resp.json()) as KreaStatusSnapshot;
}

/** Parse JSON tolerantly — a partial/garbage body becomes null (the caller
 *  then synthesizes the fallback signal), never a throw. */
async function safeJson<T>(resp: Response): Promise<T | null> {
  try {
    return (await resp.json()) as T;
  } catch {
    return null;
  }
}

/** Type guard: did the result come back as real art (vs the fallback)? */
export function isSceneArt(r: SceneResult): r is SceneArt {
  return r.enabled === true && r.isFallback === false;
}
