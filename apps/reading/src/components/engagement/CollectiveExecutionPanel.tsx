import { useEffect, useRef, useState } from "react";

import {
  getCollectiveExecutionStatus,
  prepareCollectiveExecution,
  type CollectiveExecutionPreparation,
  type CollectiveExecutionStatus,
} from "../../api/engagement";
import {
  enqueueMidnightOilJob,
  getMidnightOilLifecycle,
  issueMidnightOilSpendConsent,
  resetMidnightOilSpendConsent,
  type MidnightOilLifecycleStatus,
} from "../../api/midnightOil";

function idempotencyKey(): string {
  return `collective-execution-${
    typeof crypto !== "undefined" && crypto.randomUUID
      ? crypto.randomUUID()
      : Math.random().toString(36).slice(2)
  }`;
}

export function CollectiveExecutionPanel(props: {
  unitId: string;
  previewSha256: string;
  sessionId: string;
  modelId?: string | null;
  researchTier: "fast" | "deep" | "wrestle";
  onTerminal?: (status: string) => void;
}) {
  const key = useRef(idempotencyKey());
  const [duration, setDuration] = useState(60);
  const [prepared, setPrepared] = useState<CollectiveExecutionPreparation | null>(null);
  const [status, setStatus] = useState<CollectiveExecutionStatus | null>(null);
  const [lifecycle, setLifecycle] = useState<MidnightOilLifecycleStatus | null>(null);
  const [ceilingCents, setCeilingCents] = useState<number | null>(null);
  const [busy, setBusy] = useState<"prepare" | "consent" | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!prepared?.execution_id) return;
    let cancelled = false;
    let done = false;
    const terminal = new Set([
      "complete",
      "failed",
      "budget_halted",
      "timed_out",
      "failed_reconcile",
    ]);
    const poll = async () => {
      try {
        const [next, spend] = await Promise.all([
          getCollectiveExecutionStatus(props.unitId, prepared.execution_id),
          getMidnightOilLifecycle(prepared.job_id),
        ]);
        if (cancelled) return;
        setStatus(next);
        setLifecycle(spend);
        if (next.context_ready || terminal.has(next.state)) {
          done = true;
          props.onTerminal?.(next.session_status);
        }
      } catch (cause) {
        if (!cancelled) setError(cause instanceof Error ? cause.message : "Status unavailable");
      }
    };
    void poll();
    const timer = window.setInterval(() => {
      if (!done) void poll();
    }, 4_000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [prepared?.execution_id, props.onTerminal, props.unitId]);

  const prepare = async () => {
    setBusy("prepare");
    setError("");
    try {
      const next = await prepareCollectiveExecution(props.unitId, {
        session_id: props.sessionId,
        expected_preview_sha256: props.previewSha256,
        idempotency_key: key.current,
        duration_minutes: duration,
        model_id: props.modelId ?? null,
        research_tier: props.researchTier,
        fanout_depth: 3,
      });
      setPrepared(next);
      setCeilingCents(next.recommended_ceiling_cents);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Preparation failed");
    } finally {
      setBusy(null);
    }
  };

  const consentAndQueue = async () => {
    if (!prepared || ceilingCents == null) return;
    setBusy("consent");
    setError("");
    try {
      const consent = await issueMidnightOilSpendConsent({
        job_id: prepared.job_id,
        ceiling_cents: ceilingCents,
        force_below: ceilingCents < prepared.recommended_ceiling_cents,
      });
      // The bearer credential stays in this stack frame and goes directly to
      // the run header. It is never placed in React state or browser storage.
      await enqueueMidnightOilJob(prepared.job_id, consent.token);
      const [next, spend] = await Promise.all([
        getCollectiveExecutionStatus(props.unitId, prepared.execution_id),
        getMidnightOilLifecycle(prepared.job_id),
      ]);
      setStatus(next);
      setLifecycle(spend);
    } catch (cause) {
      try {
        const reconciled = await getCollectiveExecutionStatus(
          props.unitId,
          prepared.execution_id,
        );
        setStatus(reconciled);
        setError(
          reconciled.state === "consent_issued"
            ? "Consent was issued but delivery is unconfirmed. Reconcile before reissuing."
            : "The response was ambiguous; durable execution state is shown below.",
        );
      } catch {
        setError(cause instanceof Error ? cause.message : "Consent or queue failed");
      }
    } finally {
      setBusy(null);
    }
  };

  const recoverConsent = async () => {
    if (!prepared) return;
    setBusy("consent");
    setError("");
    try {
      const reconciled = await getCollectiveExecutionStatus(
        props.unitId,
        prepared.execution_id,
      );
      if (reconciled.state !== "consent_issued") {
        setStatus(reconciled);
        return;
      }
      await resetMidnightOilSpendConsent(prepared.job_id);
      setStatus(null);
      setPrepared({ ...prepared, state: "consent_required", operation_state: "none" });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Consent recovery failed");
    } finally {
      setBusy(null);
    }
  };

  const shownState = status?.state || prepared?.state || "not_prepared";
  return (
    <section
      className="space-y-3 rounded border border-black/20 p-3 dark:border-white/20"
      data-testid="collective-execution-panel"
      data-execution-state={shownState}
      data-consent-token-persisted="false"
    >
      <div>
        <h3 className="text-xs font-semibold uppercase tracking-wide">
          Execute cohesive research
        </h3>
        <p className="text-[11px] opacity-75">
          Preparation spends nothing. Provider work begins only after you approve an exact
          integer-cent ceiling and a worker leases the queued operation.
        </p>
      </div>
      {!prepared ? (
        <div className="flex items-end gap-2">
          <label className="text-[11px]">
            Work time (minutes)
            <input
              aria-label="Collective execution duration minutes"
              className="ml-2 w-20 rounded border px-2 py-1 text-xs"
              type="number"
              min={1}
              max={10080}
              value={duration}
              onChange={(event) => setDuration(Number(event.target.value))}
            />
          </label>
          <button type="button" disabled={busy != null} onClick={() => void prepare()}>
            {busy === "prepare" ? "Preparing…" : "Review execution budget"}
          </button>
        </div>
      ) : (
        <div className="space-y-2 text-[11px] font-mono">
          <p>State: {shownState.replaceAll("_", " ")}</p>
          <p>Job: {prepared.job_id}</p>
          <p>
            Server recommendation: ${(prepared.recommended_ceiling_cents / 100).toFixed(2)}
          </p>
          {shownState === "consent_required" ? (
            <div className="flex items-end gap-2">
              <label>
                Approved ceiling (cents)
                <input
                  aria-label="Approved collective execution ceiling cents"
                  className="ml-2 w-28 rounded border px-2 py-1"
                  type="number"
                  min={1}
                  step={1}
                  value={ceilingCents ?? ""}
                  onChange={(event) => setCeilingCents(Number(event.target.value))}
                />
              </label>
              <button
                type="button"
                disabled={busy != null || !Number.isSafeInteger(ceilingCents) || (ceilingCents ?? 0) < 1}
                onClick={() => void consentAndQueue()}
              >
                {busy === "consent" ? "Authorizing…" : "Approve ceiling and queue"}
              </button>
            </div>
          ) : null}
          {shownState === "consent_issued" ? (
            <button type="button" disabled={busy != null} onClick={() => void recoverConsent()}>
              {busy === "consent" ? "Reconciling…" : "Reconcile unqueued consent"}
            </button>
          ) : null}
          {status ? (
            <p role="status">
              Phase: {status.phase.replaceAll("_", " ")} · provider calls started:{" "}
              {status.provider_calls_started ? "yes" : "no"} · context ready:{" "}
              {status.context_ready ? "yes" : "no"}
            </p>
          ) : null}
          {lifecycle ? (
            <p data-testid="collective-execution-spend">
              Confirmed spend: ${(lifecycle.confirmed_spent_cents / 100).toFixed(2)} · held:{" "}
              ${(lifecycle.reserved_cents / 100).toFixed(2)} · remaining:{" "}
              {lifecycle.remaining_cents == null
                ? "unknown"
                : `$${(lifecycle.remaining_cents / 100).toFixed(2)}`}
              {lifecycle.unknown_outcome ? " · unknown provider outcome" : ""}
            </p>
          ) : null}
        </div>
      )}
      {error ? <p role="alert" className="text-xs text-red-700">{error}</p> : null}
    </section>
  );
}
