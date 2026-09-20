/**
 * Link Monster API client.
 *
 * Mirrors `interfaces/research/api/link_monster_routes.py`. The digest
 * packet shape below is the wire contract; keep the field names in
 * lock-step with `acquisition/link_monster/digest.py:LinkDigest.to_jsonable`.
 */

import { API_BASE, apiFetch } from "../lib/api";

export type MonsterPlatform = "youtube" | "x" | "instagram" | "tiktok" | "substack" | "generic";

export interface MonsterVideo {
  provider: string;
  video_id: string | null;
  url: string;
  thumbnail_url: string | null;
  duration_seconds: number | null;
  channel: string | null;
  upload_date: string | null;
  caption_kind: string | null;
}

export interface MonsterTranscript {
  source: string;
  caption_kind: string | null;
  chars: number;
  segments: Array<{ start: number; duration: number; text: string }>;
}

export interface MonsterText {
  markdown: string;
  chars: number;
  word_count: number;
  source: string;
}

export interface LinkDigest {
  url: string;
  final_url: string;
  platform: MonsterPlatform;
  platform_label: string;
  title: string | null;
  author: string | null;
  author_url: string | null;
  published_at: string | null;
  description: string | null;
  site_name: string | null;
  thumbnail_url: string | null;
  image_urls: string[];
  video: MonsterVideo | null;
  transcript: MonsterTranscript | null;
  text: MonsterText | null;
  provenance: Record<string, string>;
  outcome: "meal" | "snack";
  artifacts: {
    images: number;
    videos: number;
    transcript_chars: number;
    text_chars: number;
    body_chars: number;
  };
  digested_at: string;
}

export interface MonsterFeedItem {
  document_id: string;
  title: string | null;
  author: string | null;
  source_uri: string;
  acquired_at: string;
  digest: LinkDigest;
}

export interface MonsterStats {
  meals: number;
  snacks: number;
  total: number;
  chunks: number;
  nodes: number;
  edges: number;
  by_platform: Record<string, number>;
  last_digested_at: string | null;
}

export interface MonsterStoreSummary {
  chunks_written: number;
  node_ids: string[];
  edge_ids: string[];
  content_class: string | null;
  already_digested: boolean;
}

export interface MonsterDigestResponse {
  ok: boolean;
  document_id: string;
  already_digested: boolean;
  digest: LinkDigest;
  store: MonsterStoreSummary;
}

export type MonsterFailureKind =
  | "invalid_url" // 400
  | "ssrf_blocked" // 422
  | "rate_limited" // 429
  | "upstream_error" // 502
  | "digest_failed"
  | "store_failed"
  | "http"; // any other status

export class MonsterError extends Error {
  constructor(
    public readonly kind: MonsterFailureKind,
    message: string,
    public readonly status?: number,
  ) {
    super(message);
    this.name = "MonsterError";
  }
}

function failureKind(status: number, reason: string): MonsterFailureKind {
  if (status === 400) return "invalid_url";
  if (status === 422) return "ssrf_blocked";
  if (status === 429) return "rate_limited";
  if (status === 502) return reason === "digest_failed" || reason === "store_failed" ? reason : "upstream_error";
  return "http";
}

/** Feed one URL to the Monster. */
export async function feedMonster(url: string): Promise<MonsterDigestResponse> {
  let resp: Response;
  try {
    resp = await apiFetch(`${API_BASE}/links/monster`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });
  } catch (err) {
    throw new MonsterError("upstream_error", err instanceof Error ? err.message : "network failure");
  }
  let body: { ok: boolean; reason?: string; message?: string };
  try {
    body = await resp.json();
  } catch {
    throw new MonsterError("http", `unparseable response (${resp.status})`, resp.status);
  }
  if (!resp.ok || body.ok === false) {
    throw new MonsterError(failureKind(resp.status, body.reason ?? ""), body.message ?? `HTTP ${resp.status}`, resp.status);
  }
  return body as unknown as MonsterDigestResponse;
}

/** Monster Menu — recent digests. */
export async function listMonsterFeed(limit = 20): Promise<MonsterFeedItem[]> {
  const resp = await apiFetch(`${API_BASE}/links/monster/feed?limit=${limit}`);
  const body = await resp.json();
  if (!resp.ok || body.ok === false) {
    throw new MonsterError("http", `feed failed (${resp.status})`, resp.status);
  }
  return body.items as MonsterFeedItem[];
}

/** Monster stats. */
export async function getMonsterStats(): Promise<MonsterStats> {
  const resp = await apiFetch(`${API_BASE}/links/monster/stats`);
  const body = await resp.json();
  if (!resp.ok || body.ok === false) {
    throw new MonsterError("http", `stats failed (${resp.status})`, resp.status);
  }
  const { ok: _ok, ...stats } = body;
  return stats as MonsterStats;
}
