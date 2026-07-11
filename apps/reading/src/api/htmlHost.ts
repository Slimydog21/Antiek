/**
 * HTML host port client (HTML-native book account host).
 *
 * POST /books/html-host/evaluate
 *
 * Advisory gate only — never invents hosted=true or purchase_executed.
 */

import { API_BASE, apiFetch } from "../lib/api";

export interface HtmlHostRequest {
  title: string;
  parent_asset_id?: string | null;
  operator_id?: string | null;
  free_copy_preflight?: { freely_available: boolean; [k: string]: unknown } | null;
  purchase_gate?: {
    purchase_intent_allowed: boolean;
    purchase_executed?: boolean;
    [k: string]: unknown;
  } | null;
  html_projection?: {
    ready: boolean;
    html_sha256?: string | null;
    html_bytes?: number | null;
    [k: string]: unknown;
  } | null;
}

export interface HtmlHostReceipt {
  host_allowed: boolean;
  hosted: boolean;
  acquisition_path: string;
  parent_asset_id: string | null;
  title: string;
  html_sha256: string | null;
  html_bytes: number | null;
  view_mode: string;
  reasons: string[];
  notes: string[];
  authority: string;
  purchase_executed: boolean;
}

export class HtmlHostHttpError extends Error {
  readonly status: number;
  readonly body: string;
  constructor(status: number, body: string) {
    super(`html-host API ${status}: ${body.slice(0, 200)}`);
    this.name = "HtmlHostHttpError";
    this.status = status;
    this.body = body;
  }
}

async function readOkBody(res: Response): Promise<unknown> {
  if (!res.ok) {
    throw new HtmlHostHttpError(res.status, await res.text());
  }
  return res.json() as Promise<unknown>;
}

export function parseHtmlHostReceipt(body: unknown): HtmlHostReceipt {
  if (!body || typeof body !== "object") {
    throw new Error("html host response must be an object");
  }
  const o = body as Record<string, unknown>;
  if (typeof o.host_allowed !== "boolean") {
    throw new Error("html host rejected: host_allowed must be boolean");
  }
  if (typeof o.hosted !== "boolean") {
    throw new Error("html host rejected: hosted must be boolean");
  }
  if (o.hosted === true) {
    throw new Error(
      "html host rejected: hosted=true not accepted (gate never completes host)",
    );
  }
  if (typeof o.purchase_executed !== "boolean") {
    throw new Error("html host rejected: purchase_executed must be boolean");
  }
  if (o.purchase_executed === true) {
    throw new Error(
      "html host rejected: purchase_executed=true not accepted",
    );
  }
  if (typeof o.authority !== "string" || o.authority.trim() !== "html_host_port_advisory") {
    throw new Error(
      "html host rejected: authority must be html_host_port_advisory",
    );
  }
  if (typeof o.title !== "string" || !o.title.trim()) {
    throw new Error("html host rejected: title required");
  }
  if (typeof o.acquisition_path !== "string" || !o.acquisition_path.trim()) {
    throw new Error("html host rejected: acquisition_path required");
  }
  if (typeof o.view_mode !== "string" || !o.view_mode.trim()) {
    throw new Error("html host rejected: view_mode required");
  }
  if (!Array.isArray(o.reasons) || !Array.isArray(o.notes)) {
    throw new Error("html host rejected: reasons/notes must be arrays");
  }

  // Trust-boundary: host_allowed requires acquisition + html projection honesty
  if (o.host_allowed === true) {
    if (o.view_mode !== "html") {
      throw new Error(
        "html host rejected: host_allowed=true requires view_mode=html",
      );
    }
    if (
      o.acquisition_path !== "free_copy" &&
      o.acquisition_path !== "purchase_intent"
    ) {
      throw new Error(
        "html host rejected: host_allowed requires free_copy or purchase_intent path",
      );
    }
    if (typeof o.html_sha256 !== "string" || !/^[0-9a-f]{64}$/.test(o.html_sha256)) {
      throw new Error(
        "html host rejected: host_allowed requires 64-char hex html_sha256",
      );
    }
  }

  return {
    host_allowed: o.host_allowed,
    hosted: false,
    acquisition_path: o.acquisition_path,
    parent_asset_id:
      typeof o.parent_asset_id === "string" ? o.parent_asset_id : null,
    title: o.title.trim(),
    html_sha256: typeof o.html_sha256 === "string" ? o.html_sha256 : null,
    html_bytes:
      typeof o.html_bytes === "number" && Number.isFinite(o.html_bytes)
        ? o.html_bytes
        : null,
    view_mode: o.view_mode,
    reasons: o.reasons.map((r) => {
      if (typeof r !== "string") throw new Error("reasons must be strings");
      return r;
    }),
    notes: o.notes.map((n) => {
      if (typeof n !== "string") throw new Error("notes must be strings");
      return n;
    }),
    authority: "html_host_port_advisory",
    purchase_executed: false,
  };
}

export async function postHtmlHostEvaluate(
  req: HtmlHostRequest,
): Promise<HtmlHostReceipt> {
  const title = String(req.title || "").trim();
  if (!title) throw new Error("title must be non-empty");

  const payload: Record<string, unknown> = { title };
  if (req.parent_asset_id != null && String(req.parent_asset_id).trim()) {
    payload.parent_asset_id = String(req.parent_asset_id).trim();
  }
  if (req.operator_id != null && String(req.operator_id).trim()) {
    payload.operator_id = String(req.operator_id).trim();
  }
  if (req.free_copy_preflight != null) {
    if (typeof req.free_copy_preflight.freely_available !== "boolean") {
      throw new Error(
        "free_copy_preflight.freely_available must be an explicit boolean",
      );
    }
    payload.free_copy_preflight = req.free_copy_preflight;
  }
  if (req.purchase_gate != null) {
    if (typeof req.purchase_gate.purchase_intent_allowed !== "boolean") {
      throw new Error(
        "purchase_gate.purchase_intent_allowed must be an explicit boolean",
      );
    }
    if (req.purchase_gate.purchase_executed === true) {
      throw new Error("purchase_gate.purchase_executed=true not accepted");
    }
    payload.purchase_gate = req.purchase_gate;
  }
  if (req.html_projection != null) {
    if (typeof req.html_projection.ready !== "boolean") {
      throw new Error("html_projection.ready must be an explicit boolean");
    }
    payload.html_projection = req.html_projection;
  }

  const res = await apiFetch(`${API_BASE}/books/html-host/evaluate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseHtmlHostReceipt(await readOkBody(res));
}

export function formatHtmlHostSummary(r: HtmlHostReceipt): string {
  return (
    `host_allowed=${r.host_allowed} · hosted=${r.hosted} · ` +
    `path=${r.acquisition_path} · view=${r.view_mode}`
  );
}
