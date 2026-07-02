import type { KreaStatusSnapshot } from "../api/krea";

export interface SceneStatusBadgeProps {
  status: KreaStatusSnapshot | null;
  error?: string | null;
}

const REASON_COPY: Record<string, string> = {
  no_key: "no key",
  kill_switch: "kill-switch",
  over_daily_budget: "over-budget",
  rate_limited: "rate-limited",
  upstream_error: "upstream error",
  upstream_timeout: "upstream timeout",
  upstream_bad_response: "bad upstream response",
  job_failed: "job failed",
  job_timeout: "job timeout",
  job_cancelled: "job cancelled",
  no_api_balance: "no API balance",
  offline: "status offline",
};

export function sceneStatusReason(status: KreaStatusSnapshot | null): string | null {
  if (!status) return null;
  if (status.gate_verdict) return status.gate_verdict;
  const latest = status.failures.at(-1);
  return latest?.reason ?? null;
}

export function SceneStatusBadge({ status, error = null }: SceneStatusBadgeProps) {
  const reason = error ? "offline" : sceneStatusReason(status);
  const fallback = Boolean(error) || Boolean(status && !status.enabled) || Boolean(reason);
  if (!fallback) return null;

  const label = reason ? (REASON_COPY[reason] ?? reason.replaceAll("_", " ")) : "fallback";

  return (
    <div
      data-testid="scene-status-badge"
      data-reason={reason ?? ""}
      aria-hidden="true"
      style={{
        position: "absolute",
        left: "12px",
        bottom: "12px",
        zIndex: 5,
        padding: "3px 8px",
        borderRadius: "var(--radius-sm)",
        background: "rgba(15, 23, 42, 0.84)",
        border: "1px solid rgba(255, 255, 255, 0.28)",
        color: "white",
        font: "11px/1.4 var(--mono, ui-monospace, monospace)",
        pointerEvents: "none",
        userSelect: "none",
        whiteSpace: "nowrap",
        backdropFilter: "blur(var(--glass-blur))",
      }}
    >
      {`scene: procedural / ${label}. No live Krea.`}
    </div>
  );
}

export default SceneStatusBadge;
