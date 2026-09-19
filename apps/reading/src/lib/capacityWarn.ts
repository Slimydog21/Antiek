/**
 * Capacity soft-warn helpers — surface Antiek-hosted ACU near/over monthly
 * budget. No fake billing; message + used/monthly come from the API only.
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

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function parseCapacityWarning(raw: unknown): CapacityWarning | null {
  if (!isRecord(raw)) return null;
  const message = typeof raw.message === "string" ? raw.message.trim() : "";
  if (!message) return null;
  return {
    code: typeof raw.code === "string" ? raw.code : "compute_capacity_soft_warn",
    message,
    used_compute_units:
      raw.used_compute_units === null || raw.used_compute_units === undefined
        ? null
        : Number(raw.used_compute_units),
    monthly_compute_units:
      raw.monthly_compute_units === null || raw.monthly_compute_units === undefined
        ? null
        : Number(raw.monthly_compute_units),
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
