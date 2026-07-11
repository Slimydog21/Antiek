/**
 * Marketplace purchase gate client (#847 free-copy companion).
 *
 * POST /books/purchase-gate/evaluate
 *
 * Advisory only — never invents purchase_executed or free miss.
 */

import { API_BASE, apiFetch } from "../lib/api";

export interface PurchaseGateRequest {
  title: string;
  author?: string | null;
  free_copy_preflight?: {
    freely_available: boolean;
    [key: string]: unknown;
  } | null;
  skip_free_copy: boolean;
  operator_skip_acknowledged?: boolean | null;
  store?: string | null;
}

export interface PurchaseGateDecision {
  title: string;
  author: string | null;
  purchase_intent_allowed: boolean;
  purchase_executed: boolean;
  path: string;
  reasons: string[];
  notes: string[];
  free_copy_freely_available: boolean | null;
  authority: string;
}

export class PurchaseGateHttpError extends Error {
  readonly status: number;
  readonly body: string;
  constructor(status: number, body: string) {
    super(`book-purchase-gate API ${status}: ${body.slice(0, 200)}`);
    this.name = "PurchaseGateHttpError";
    this.status = status;
    this.body = body;
  }
}

async function readOkBody(res: Response): Promise<unknown> {
  if (!res.ok) {
    throw new PurchaseGateHttpError(res.status, await res.text());
  }
  return res.json() as Promise<unknown>;
}

export function parsePurchaseGateDecision(body: unknown): PurchaseGateDecision {
  if (!body || typeof body !== "object") {
    throw new Error("purchase gate response must be an object");
  }
  const o = body as Record<string, unknown>;
  if (typeof o.title !== "string" || !o.title.trim()) {
    throw new Error("purchase gate rejected: title required");
  }
  if (typeof o.purchase_intent_allowed !== "boolean") {
    throw new Error(
      "purchase gate rejected: purchase_intent_allowed must be boolean",
    );
  }
  if (typeof o.purchase_executed !== "boolean") {
    throw new Error("purchase gate rejected: purchase_executed must be boolean");
  }
  if (o.purchase_executed === true) {
    throw new Error(
      "purchase gate rejected: purchase_executed=true not accepted (gate never executes)",
    );
  }
  if (typeof o.authority !== "string" || o.authority.trim() !== "purchase_gate_advisory") {
    throw new Error(
      "purchase gate rejected: authority must be purchase_gate_advisory",
    );
  }
  if (typeof o.path !== "string" || !o.path.trim()) {
    throw new Error("purchase gate rejected: path required");
  }
  if (!Array.isArray(o.reasons) || !Array.isArray(o.notes)) {
    throw new Error("purchase gate rejected: reasons/notes must be arrays");
  }
  const freeAvail =
    typeof o.free_copy_freely_available === "boolean"
      ? o.free_copy_freely_available
      : o.free_copy_freely_available === null
        ? null
        : (() => {
            throw new Error(
              "purchase gate rejected: free_copy_freely_available must be boolean|null",
            );
          })();

  // Trust-boundary decision matrix (never invent free-miss/skip).
  if (o.purchase_intent_allowed === true) {
    if (freeAvail === true) {
      throw new Error(
        "purchase gate rejected: freely_available=true cannot allow purchase intent",
      );
    }
    if (freeAvail === false) {
      if (o.path !== "purchase_intent_after_free_miss") {
        throw new Error(
          "purchase gate rejected: free miss must use path purchase_intent_after_free_miss",
        );
      }
    } else {
      // freeAvail === null: only skip_free_copy path may allow intent
      if (o.path !== "skip_free_copy") {
        throw new Error(
          "purchase gate rejected: free_copy null only allows intent via skip_free_copy path",
        );
      }
    }
  } else if (freeAvail === true && o.path !== "use_free_copy") {
    throw new Error(
      "purchase gate rejected: freely_available=true must use path use_free_copy when blocked",
    );
  }

  return {
    title: o.title.trim(),
    author: typeof o.author === "string" ? o.author : null,
    purchase_intent_allowed: o.purchase_intent_allowed,
    purchase_executed: false,
    path: o.path,
    reasons: o.reasons.map((r) => {
      if (typeof r !== "string") throw new Error("reasons must be strings");
      return r;
    }),
    notes: o.notes.map((n) => {
      if (typeof n !== "string") throw new Error("notes must be strings");
      return n;
    }),
    free_copy_freely_available: freeAvail,
    authority: "purchase_gate_advisory",
  };
}

export async function postPurchaseGate(
  req: PurchaseGateRequest,
): Promise<PurchaseGateDecision> {
  const title = String(req.title || "").trim();
  if (!title) throw new Error("title must be non-empty");
  if (typeof req.skip_free_copy !== "boolean") {
    throw new Error("skip_free_copy must be an explicit boolean");
  }

  const payload: Record<string, unknown> = {
    title,
    skip_free_copy: req.skip_free_copy,
  };
  if (req.author != null && String(req.author).trim()) {
    payload.author = String(req.author).trim();
  }
  if (req.store != null && String(req.store).trim()) {
    payload.store = String(req.store).trim();
  }
  if (req.skip_free_copy) {
    if (req.operator_skip_acknowledged !== true) {
      throw new Error(
        "skip_free_copy requires operator_skip_acknowledged=true",
      );
    }
    payload.operator_skip_acknowledged = true;
  } else {
    if (!req.free_copy_preflight || typeof req.free_copy_preflight !== "object") {
      throw new Error("free_copy_preflight required unless skip_free_copy");
    }
    if (typeof req.free_copy_preflight.freely_available !== "boolean") {
      throw new Error(
        "free_copy_preflight.freely_available must be an explicit boolean",
      );
    }
    payload.free_copy_preflight = req.free_copy_preflight;
  }

  const res = await apiFetch(`${API_BASE}/books/purchase-gate/evaluate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parsePurchaseGateDecision(await readOkBody(res));
}

export function formatPurchaseGateSummary(d: PurchaseGateDecision): string {
  return (
    `intent_allowed=${d.purchase_intent_allowed} · executed=${d.purchase_executed} · ` +
    `path=${d.path}`
  );
}
