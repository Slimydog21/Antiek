/**
 * Cascade launch client with source_policy honesty (PR #781 contract).
 *
 * POST /research/plans/{root_id}/launch
 *
 * When require_source_preflight is true, source_policy must be non-empty
 * before any network call, and a successful response must include a
 * source_preflight receipt. Blank/unknown policy entries fail closed.
 */

import { API_BASE, apiFetch } from "../lib/api";

export type SourcePolicyName =
  | "arxiv"
  | "substack"
  | "web"
  | "operator_corpus";

export const ALLOWED_SOURCE_POLICIES: readonly SourcePolicyName[] = [
  "arxiv",
  "substack",
  "web",
  "operator_corpus",
] as const;

export interface CascadeLaunchRequest {
  root_id: string;
  per_research_budget_usd?: number;
  aggregate_budget_usd?: number | null;
  source_policy?: SourcePolicyName[] | string[] | null;
  require_source_preflight?: boolean;
}

export interface CascadeLaunchResult {
  raw: Record<string, unknown>;
  source_policy: SourcePolicyName[] | null;
  require_source_preflight: boolean;
  source_preflight: Record<string, unknown> | null;
}

export class CascadeLaunchHttpError extends Error {
  readonly status: number;
  readonly body: string;
  constructor(status: number, body: string) {
    super(`cascade-launch API ${status}: ${body.slice(0, 200)}`);
    this.name = "CascadeLaunchHttpError";
    this.status = status;
    this.body = body;
  }
}

export class CascadeLaunchClientError extends Error {
  readonly code: string;
  constructor(code: string, message: string) {
    super(message);
    this.name = "CascadeLaunchClientError";
    this.code = code;
  }
}

async function readOkBody(res: Response): Promise<unknown> {
  if (!res.ok) {
    const text = await res.text();
    throw new CascadeLaunchHttpError(res.status, text);
  }
  return res.json() as Promise<unknown>;
}

export function normalizeSourcePolicy(
  policy: string[] | null | undefined,
): SourcePolicyName[] | null {
  if (policy === null || policy === undefined) return null;
  if (!Array.isArray(policy)) {
    throw new CascadeLaunchClientError(
      "source_policy_invalid",
      "source_policy must be an array when provided",
    );
  }
  if (policy.length === 0) return null;
  const allowed = new Set<string>(ALLOWED_SOURCE_POLICIES);
  const out: SourcePolicyName[] = [];
  const seen = new Set<string>();
  const bad: string[] = [];
  for (const raw of policy) {
    const s = String(raw).trim();
    if (!s) {
      bad.push(JSON.stringify(raw));
      continue;
    }
    if (!allowed.has(s)) {
      bad.push(s);
      continue;
    }
    if (seen.has(s)) continue;
    seen.add(s);
    out.push(s as SourcePolicyName);
  }
  if (bad.length) {
    throw new CascadeLaunchClientError(
      "source_policy_invalid",
      "unknown or blank source_policy entries: " + bad.join(", "),
    );
  }
  return out.length ? out : null;
}

function extractSourcePreflight(
  raw: Record<string, unknown>,
): Record<string, unknown> | null {
  const pf = raw.source_preflight;
  if (pf === null || pf === undefined) return null;
  if (typeof pf !== "object" || Array.isArray(pf)) {
    throw new CascadeLaunchClientError(
      "source_preflight_invalid",
      "source_preflight must be an object when present",
    );
  }
  return pf as Record<string, unknown>;
}

export async function postCascadeLaunch(
  req: CascadeLaunchRequest,
): Promise<CascadeLaunchResult> {
  const root_id = (req.root_id || "").trim();
  if (!root_id) {
    throw new CascadeLaunchClientError(
      "root_id_required",
      "root_id must be non-empty",
    );
  }
  const require = req.require_source_preflight === true;
  const policy = normalizeSourcePolicy(req.source_policy ?? null);
  if (require && (policy === null || policy.length === 0)) {
    throw new CascadeLaunchClientError(
      "source_policy_required",
      "source_policy is required when require_source_preflight is true",
    );
  }

  const budget = req.per_research_budget_usd ?? 0.5;
  if (typeof budget !== "number" || !Number.isFinite(budget) || budget <= 0) {
    throw new CascadeLaunchClientError(
      "budget_invalid",
      "per_research_budget_usd must be a finite number > 0",
    );
  }

  const res = await apiFetch(
    `${API_BASE}/research/plans/${encodeURIComponent(root_id)}/launch`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        per_research_budget_usd: budget,
        aggregate_budget_usd: req.aggregate_budget_usd ?? null,
        source_policy: policy,
        require_source_preflight: require,
      }),
    },
  );
  const rawUnknown = await readOkBody(res);
  if (!rawUnknown || typeof rawUnknown !== "object" || Array.isArray(rawUnknown)) {
    throw new Error("cascade-launch response must be an object");
  }
  const raw = rawUnknown as Record<string, unknown>;
  const source_preflight = extractSourcePreflight(raw);

  if (require) {
    if (!source_preflight) {
      throw new CascadeLaunchClientError(
        "source_preflight_missing",
        "launch with require_source_preflight must return source_preflight receipt",
      );
    }
    const receiptPolicy = source_preflight.source_policy;
    if (!Array.isArray(receiptPolicy)) {
      throw new CascadeLaunchClientError(
        "source_preflight_missing_policy",
        "source_preflight.source_policy must be a non-empty array",
      );
    }
    // Fail closed: receipt policy must normalize to a non-empty allowed list.
    let normalizedReceipt: SourcePolicyName[] | null;
    try {
      normalizedReceipt = normalizeSourcePolicy(receiptPolicy as string[]);
    } catch (e) {
      if (e instanceof CascadeLaunchClientError) {
        throw new CascadeLaunchClientError(
          "source_preflight_invalid_policy",
          e.message,
        );
      }
      throw e;
    }
    if (normalizedReceipt === null || normalizedReceipt.length === 0) {
      throw new CascadeLaunchClientError(
        "source_preflight_missing_policy",
        "source_preflight.source_policy must be a non-empty allowed list",
      );
    }
  }

  return {
    raw,
    source_policy: policy,
    require_source_preflight: require,
    source_preflight,
  };
}
