/**
 * Capacity soft-warn + hard-refuse helpers — surface Antiek-hosted ACU
 * near/over/at monthly budget. No fake billing; message + used/monthly
 * come from the API only.
 */
export interface CapacityWarning {
  code: string;
  message: string;
  used_compute_units: number | null;
  monthly_compute_units: number | null;
  enforcement: string;
  used_status: string;
}

const STASH_PREFIX = "antiek:capacity-soft-warn:";
export const CAPACITY_EXHAUSTED_CODE = "compute_capacity_exhausted";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function numOrNull(value: unknown): number | null {
  if (value === null || value === undefined) return null;
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

export function parseCapacityWarning(raw: unknown): CapacityWarning | null {
  if (!isRecord(raw)) return null;
  const message = typeof raw.message === "string" ? raw.message.trim() : "";
  if (!message) return null;
  return {
    code: typeof raw.code === "string" ? raw.code : "compute_capacity_soft_warn",
    message,
    used_compute_units: numOrNull(raw.used_compute_units),
    monthly_compute_units: numOrNull(raw.monthly_compute_units),
    enforcement: typeof raw.enforcement === "string" ? raw.enforcement : "",
    used_status: typeof raw.used_status === "string" ? raw.used_status : "",
  };
}

export function formatCapacityWarnToast(warn: CapacityWarning): string {
  const used = warn.used_compute_units;
  const monthly = warn.monthly_compute_units;
  if (used != null && monthly != null && monthly > 0) {
    return (
      "Agent compute near monthly capacity (" +
      used +
      "/" +
      monthly +
      " ACU). BYO Token spend is separate."
    );
  }
  return warn.message;
}

const FALLBACK_EXHAUSTED_MESSAGE =
  "Agent compute at monthly capacity. New research starts are refused until " +
  "you raise the ACU limit in Settings → Agent compute. BYO Token spend is separate.";

/** Parse FastAPI 429 detail (structured object or legacy bare string). */
export function parseCapacityExhaustedDetail(
  status: number,
  body: string,
): CapacityWarning | null {
  if (status !== 429) return null;
  let parsed: unknown;
  try {
    parsed = JSON.parse(body) as unknown;
  } catch {
    return null;
  }
  if (!isRecord(parsed)) return null;
  const detail = parsed.detail;
  if (typeof detail === "string") {
    if (detail !== CAPACITY_EXHAUSTED_CODE) return null;
    return {
      code: CAPACITY_EXHAUSTED_CODE,
      message: FALLBACK_EXHAUSTED_MESSAGE,
      used_compute_units: null,
      monthly_compute_units: null,
      enforcement: "hard",
      used_status: "",
    };
  }
  if (!isRecord(detail)) return null;
  if (detail.code !== CAPACITY_EXHAUSTED_CODE) return null;
  const message =
    typeof detail.message === "string" && detail.message.trim()
      ? detail.message.trim()
      : FALLBACK_EXHAUSTED_MESSAGE;
  return {
    code: CAPACITY_EXHAUSTED_CODE,
    message,
    used_compute_units: numOrNull(detail.used_compute_units),
    monthly_compute_units: numOrNull(detail.monthly_compute_units),
    enforcement:
      typeof detail.enforcement === "string" ? detail.enforcement : "hard",
    used_status: typeof detail.used_status === "string" ? detail.used_status : "",
  };
}

export function formatCapacityExhaustedToast(ex: CapacityWarning): string {
  const used = ex.used_compute_units;
  const monthly = ex.monthly_compute_units;
  if (used != null && monthly != null) {
    return (
      "Agent compute at monthly capacity (" +
      used +
      "/" +
      monthly +
      " ACU). New starts refused — raise the limit in Settings. BYO Token spend is separate."
    );
  }
  return ex.message || FALLBACK_EXHAUSTED_MESSAGE;
}

/** Thrown when POST start/spin is hard-refused (429 compute_capacity_exhausted). */
export class CapacityExhaustedError extends Error {
  readonly exhaustion: CapacityWarning;
  constructor(exhaustion: CapacityWarning) {
    super(formatCapacityExhaustedToast(exhaustion));
    this.name = "CapacityExhaustedError";
    this.exhaustion = exhaustion;
  }
}

/** Stash for the investigation surface after navigate (spin / POST). */
export function stashCapacityWarning(
  investigationId: string,
  warn: CapacityWarning | null | undefined,
): void {
  if (!warn || typeof window === "undefined") return;
  try {
    window.sessionStorage.setItem(
      STASH_PREFIX + investigationId,
      JSON.stringify(warn),
    );
  } catch {
    /* quota / private mode — toast still fires at call site */
  }
}

/** Consume once when InvestigationCenter mounts. */
export function takeCapacityWarning(
  investigationId: string,
): CapacityWarning | null {
  if (typeof window === "undefined") return null;
  const key = STASH_PREFIX + investigationId;
  try {
    const raw = window.sessionStorage.getItem(key);
    if (!raw) return null;
    window.sessionStorage.removeItem(key);
    return parseCapacityWarning(JSON.parse(raw));
  } catch {
    try {
      window.sessionStorage.removeItem(key);
    } catch {
      /* ignore */
    }
    return null;
  }
}
