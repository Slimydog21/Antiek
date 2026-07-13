import { useEffect, useRef, useState } from "react";

import {
  getCollectiveExecutionStatus,
  prepareCollectiveExecution,
  previewCollectiveExecutionReadiness,
  type CollectivePublicationReadinessPreview,
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

type ReadinessSubstackSource = Extract<
  CollectivePublicationReadinessPreview["sources"][number],
  { kind: "substack" }
>;
type ReadinessChoice = ReadinessSubstackSource["available_reviews"][number];

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
  const [readiness, setReadiness] =
    useState<CollectivePublicationReadinessPreview | null>(null);
  const [overlaySelections, setOverlaySelections] = useState<Record<string, string>>({});
  const [reviewChoices, setReviewChoices] = useState<
    Array<{ refId: string; choice: ReadinessChoice }>
  >([]);
  const [prepared, setPrepared] = useState<CollectiveExecutionPreparation | null>(null);
  const [status, setStatus] = useState<CollectiveExecutionStatus | null>(null);
  const [lifecycle, setLifecycle] = useState<MidnightOilLifecycleStatus | null>(null);
  const [ceilingCents, setCeilingCents] = useState<number | null>(null);
  const [busy, setBusy] = useState<"readiness" | "prepare" | "consent" | null>(null);
  const [error, setError] = useState("");
  const readinessGeneration = useRef(0);
  const operationGeneration = useRef(0);

  useEffect(() => {
    readinessGeneration.current += 1;
    operationGeneration.current += 1;
    key.current = idempotencyKey();
    setReadiness(null);
    setOverlaySelections({});
    setReviewChoices([]);
    setPrepared(null);
    setStatus(null);
    setLifecycle(null);
    setCeilingCents(null);
    setBusy(null);
    setError("");
  }, [props.modelId, props.previewSha256, props.researchTier, props.sessionId, props.unitId]);

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

  const reviewReadiness = async () => {
    const generation = ++readinessGeneration.current;
    const requestedDuration = duration;
    setBusy("readiness");
    setError("");
    setReadiness(null);
    try {
      const makeSelections = (selected: Record<string, string>, choices = reviewChoices) =>
        Object.entries(selected)
        .map(([refId, overlayId]) => {
          const overlay = choices.find(
            (item) => item.refId === refId && item.choice.overlay_id === overlayId,
          );
          return overlay
            ? {
                ref_id: refId,
                overlay_id: overlay.choice.overlay_id,
                overlay_sha256: overlay.choice.overlay_sha256,
              }
            : null;
        })
        .filter((item): item is NonNullable<typeof item> => item != null)
        .sort((left, right) =>
          `${left.ref_id}:${left.overlay_id}`.localeCompare(`${right.ref_id}:${right.overlay_id}`),
        );
      const requestPreview = (selections: ReturnType<typeof makeSelections>) =>
        previewCollectiveExecutionReadiness(props.unitId, {
        schema_version: 1,
        expected_collective_preview_sha256: props.previewSha256,
        duration_minutes: requestedDuration,
        substack_overlays: selections,
      });
      let next = await requestPreview(makeSelections(overlaySelections));
      const nextSelections = { ...overlaySelections };
      const nextChoices = next.sources.flatMap((source) =>
        source.kind === "substack"
          ? source.available_reviews.map((choice) => ({ refId: source.ref_id, choice }))
          : [],
      );
      for (const source of next.sources) {
        if (source.kind !== "substack" || nextSelections[source.ref_id]) continue;
        if (source.available_reviews.length === 1) {
          nextSelections[source.ref_id] = source.available_reviews[0].overlay_id;
        }
      }
      if (JSON.stringify(nextSelections) !== JSON.stringify(overlaySelections)) {
        next = await requestPreview(makeSelections(nextSelections, nextChoices));
      }
      if (
        generation !== readinessGeneration.current ||
        requestedDuration !== duration ||
        next.collective_unit_id !== props.unitId ||
        next.collective_preview_sha256 !== props.previewSha256 ||
        next.duration_minutes !== requestedDuration
      ) {
        return;
      }
      setOverlaySelections(nextSelections);
      setReviewChoices(nextChoices);
      setReadiness(next);
    } catch (cause) {
      if (generation === readinessGeneration.current) {
        setError(cause instanceof Error ? cause.message : "Readiness preview failed");
      }
    } finally {
      if (generation === readinessGeneration.current) setBusy(null);
    }
  };

  const prepare = async () => {
    const generation = ++operationGeneration.current;
    const requestedUnitId = props.unitId;
    const requestedPreview = props.previewSha256;
    const requestedSessionId = props.sessionId;
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
      if (
        generation !== operationGeneration.current ||
        next.collective_unit_id !== requestedUnitId ||
        next.collective_preview_sha256 !== requestedPreview ||
        next.session_id !== requestedSessionId
      ) {
        return;
      }
      setPrepared(next);
      setCeilingCents(next.recommended_ceiling_cents);
    } catch (cause) {
      if (generation === operationGeneration.current) {
        setError(cause instanceof Error ? cause.message : "Preparation failed");
      }
    } finally {
      if (generation === operationGeneration.current) setBusy(null);
    }
  };

  const consentAndQueue = async () => {
    if (!prepared || ceilingCents == null) return;
    const generation = ++operationGeneration.current;
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
      if (generation !== operationGeneration.current) return;
      setStatus(next);
      setLifecycle(spend);
    } catch (cause) {
      if (generation !== operationGeneration.current) return;
      try {
        const reconciled = await getCollectiveExecutionStatus(
          props.unitId,
          prepared.execution_id,
        );
        if (generation !== operationGeneration.current) return;
        setStatus(reconciled);
        setError(
          reconciled.state === "consent_issued"
            ? "Consent was issued but delivery is unconfirmed. Reconcile before reissuing."
            : "The response was ambiguous; durable execution state is shown below.",
        );
      } catch {
        if (generation === operationGeneration.current) {
          setError(cause instanceof Error ? cause.message : "Consent or queue failed");
        }
      }
    } finally {
      if (generation === operationGeneration.current) setBusy(null);
    }
  };

  const recoverConsent = async () => {
    if (!prepared) return;
    const generation = ++operationGeneration.current;
    setBusy("consent");
    setError("");
    try {
      const reconciled = await getCollectiveExecutionStatus(
        props.unitId,
        prepared.execution_id,
      );
      if (generation !== operationGeneration.current) return;
      if (reconciled.state !== "consent_issued") {
        setStatus(reconciled);
        return;
      }
      await resetMidnightOilSpendConsent(prepared.job_id);
      if (generation !== operationGeneration.current) return;
      setStatus(null);
      setPrepared({ ...prepared, state: "consent_required", operation_state: "none" });
    } catch (cause) {
      if (generation === operationGeneration.current) {
        setError(cause instanceof Error ? cause.message : "Consent recovery failed");
      }
    } finally {
      if (generation === operationGeneration.current) setBusy(null);
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
        <div className="space-y-3">
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
                onChange={(event) => {
                  readinessGeneration.current += 1;
                  setReadiness(null);
                  setDuration(Number(event.target.value));
                }}
              />
            </label>
            <button
              type="button"
              disabled={
                busy != null ||
                !Number.isSafeInteger(duration) ||
                duration < 1 ||
                duration > 10_080
              }
              onClick={() => void reviewReadiness()}
            >
              {busy === "readiness"
                ? "Checking…"
                : readiness
                  ? "Refresh live readiness"
                  : "Review source readiness"}
            </button>
          </div>
          {[...new Set(reviewChoices.map((item) => item.refId))].map((refId) => {
              const choices = reviewChoices
                .filter((item) => item.refId === refId)
                .map((item) => item.choice);
              return choices.length > 1 ? (
                <label key={refId} className="block text-[11px]">
                  Private excerpt authority for {refId}
                  <select
                    aria-label={`Private excerpt authority ${refId}`}
                    value={overlaySelections[refId] ?? ""}
                    onChange={(event) => {
                      readinessGeneration.current += 1;
                      setReadiness(null);
                      setOverlaySelections((current) => ({
                        ...current,
                        [refId]: event.target.value,
                      }));
                    }}
                  >
                    <option value="">Choose reviewed excerpt</option>
                    {choices.map((item) => (
                      <option key={item.overlay_id} value={item.overlay_id}>
                        Review {item.overlay_id.slice(-8)} · valid through{" "}
                        {new Date(item.expires_at_ms).toISOString()}
                      </option>
                    ))}
                  </select>
                </label>
              ) : null;
            })}
          {readiness ? (
            <div
              className="space-y-2 rounded border border-black/15 p-2 text-[11px] dark:border-white/15"
              data-testid="collective-readiness-preview"
              data-request-fingerprint-sha256={readiness.request_fingerprint_sha256}
              data-confers-execution-authority="false"
              role="status"
              aria-live="polite"
            >
              <p className="font-semibold">Publication readiness snapshot</p>
              <p>
                Checked {new Date(readiness.checked_at_ms).toISOString()} for authority through{" "}
                {new Date(readiness.required_until_ms).toISOString()}. Live revalidation is always
                required.
              </p>
              <ul className="space-y-1">
                {readiness.sources.map((source) => (
                  <li key={`${source.kind}:${source.ref_id}`}>
                    <span className="font-semibold uppercase">{source.kind}</span> · Reviewed: yes ·
                    Bound: {source.binding_state === "bound" ? "yes" : "no"} · Live:{" "}
                    {source.live_state.replaceAll("_", " ")} · Executable: no
                    {source.kind === "arxiv"
                      ? " · remote abstract egress"
                      : source.kind === "substack"
                        ? " · owner-supplied local private excerpt; no Substack network fetch"
                        : ""}
                    {source.reason_codes.length
                      ? ` · ${source.reason_codes.join(", ").replaceAll("_", " ")}`
                      : ""}
                  </li>
                ))}
              </ul>
              {readiness.applicability === "mixed_v2" ? (
                <p>
                  Consent unavailable — mixed-source execution is not implemented.
                </p>
              ) : readiness.legacy_prepare_available ? (
                <button type="button" disabled={busy != null} onClick={() => void prepare()}>
                  {busy === "prepare" ? "Preparing…" : "Prepare execution budget"}
                </button>
              ) : (
                <p>Preparation unavailable — reviewed publication scope is not live-ready.</p>
              )}
            </div>
          ) : null}
        </div>
      ) : (
        <div className="space-y-2 text-[11px] font-mono">
          <p>State: {shownState.replaceAll("_", " ")}</p>
          <p>Job: {prepared.job_id}</p>
          <p>
            Server recommendation: ${(prepared.recommended_ceiling_cents / 100).toFixed(2)}
          </p>
          <div
            className="space-y-1 rounded border border-black/15 p-2 font-sans dark:border-white/15"
            data-testid="collective-execution-source-scope"
            data-source-manifest-sha256={prepared.source_scope.manifest_sha256}
            data-publication-capability-sha256={
              prepared.source_scope.capability_sha256 ?? "corpus-only"
            }
          >
            <p className="font-semibold">
              Reviewed publication scope ({prepared.source_scope.required_count})
            </p>
            {prepared.source_scope.entries.length ? (
              <ul className="list-disc pl-4">
                {prepared.source_scope.entries.map((entry) => (
                  <li key={entry.ref_id}>
                    <span className="uppercase">{entry.kind}</span> · {entry.external_id} ·{" "}
                    {entry.acquisition_mode.replaceAll("_", " ")} · cap{" "}
                    {entry.max_excerpt_bytes} bytes
                  </li>
                ))}
              </ul>
            ) : (
              <p>No external publications; this execution remains corpus-only.</p>
            )}
            <p className="opacity-75">
              Rights policy: {prepared.source_scope.rights_policy_id}. Generic web and PDFs are
              outside this signed scope. Connector and rights checks run before publication bytes
              may reach a model.
            </p>
            {prepared.source_scope.capability_sha256 ? (
              <p className="opacity-75" data-testid="collective-execution-source-attestation">
                Egress attestation: {prepared.source_scope.capability_sha256.slice(0, 12)}… · valid
                through {new Date(prepared.source_scope.capability_expires_at_ms ?? 0).toISOString()}
              </p>
            ) : null}
          </div>
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
                disabled={
                  busy != null ||
                  !Number.isSafeInteger(ceilingCents) ||
                  (ceilingCents ?? 0) < 1 ||
                  prepared.source_scope.acquirable_count !==
                    prepared.source_scope.required_count ||
                  prepared.source_scope.exclusions.length > 0
                }
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
