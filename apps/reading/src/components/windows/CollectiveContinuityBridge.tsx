import { useEffect, useMemo, useRef, useState } from "react";

import {
  fetchCollectiveCouncilReference,
  fetchCollectiveManifestReference,
  projectCollectiveManifest,
  runCollectiveCouncil,
} from "../../api/engagement";
import { useAuth } from "../../lib/auth";
import { sanitizeHostedHtml } from "../../lib/sanitizeHostedHtml";
import {
  getAncestryContinuationOptions,
  getReasoningAncestryInterrogation,
  launchAncestryContinuation,
  quoteAncestryContinuation,
  type AncestryContinuationCommand,
  type AncestryContinuationLaunch,
  type AncestryContinuationOptions,
  type AncestryContinuationQuote,
  type ReasoningAncestryInterrogationResponse,
} from "../../lib/api";

type Ref = { manifest_id: string } | { plan_id: string };
type InterrogationRef = { investigation_id: string; receipt_id: string };
type CouncilProjection = {
  schema_version: 1;
  plan: { plan_id: string; shared_prompt: string; state: string; approved_ceiling_cents: number };
  result: null | { state: string; spent_cents: number; held_cents: number; html: string | null };
  view_format: "html";
};

function identifier(value: unknown): value is string {
  return typeof value === "string" && value.length > 0 && value.length <= 512 && value === value.trim() && !/[\u0000-\u001f\u007f]/u.test(value);
}

function parse(value: unknown): Ref | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const object = value as Record<string, unknown>;
  const keys = Object.keys(object);
  if (keys.length !== 1) return null;
  if (identifier(object.manifest_id)) return { manifest_id: object.manifest_id };
  if (identifier(object.plan_id)) return { plan_id: object.plan_id };
  return null;
}

function parseInterrogation(value: unknown): InterrogationRef | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const object = value as Record<string, unknown>;
  if (Object.keys(object).length !== 2 || !identifier(object.investigation_id) || !identifier(object.receipt_id)) return null;
  return { investigation_id: object.investigation_id, receipt_id: object.receipt_id };
}

function council(value: unknown): CouncilProjection | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const row = value as Record<string, unknown>;
  if (row.schema_version !== 1 || row.view_format !== "html" || !row.plan || typeof row.plan !== "object") return null;
  const plan = row.plan as Record<string, unknown>;
  if (!identifier(plan.plan_id) || typeof plan.shared_prompt !== "string" || typeof plan.state !== "string" || typeof plan.approved_ceiling_cents !== "number") return null;
  return value as CouncilProjection;
}

function validContinuationChoice(value: unknown): boolean {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const row = value as Record<string, unknown>;
  return row.role === "synthesizer"
    && row.projection_scope === "selected_synthesizer_call_only"
    && identifier(row.provider_id) && identifier(row.model_id)
    && identifier(row.route_identity) && identifier(row.pricing_fingerprint)
    && typeof row.fallback_index === "number" && Number.isInteger(row.fallback_index) && row.fallback_index >= 0
    && typeof row.estimated_usd_low === "number" && Number.isFinite(row.estimated_usd_low) && row.estimated_usd_low >= 0
    && typeof row.estimated_usd_high === "number" && Number.isFinite(row.estimated_usd_high) && row.estimated_usd_high >= row.estimated_usd_low
    && (row.remaining_after_high_usd === null || typeof row.remaining_after_high_usd === "number" && Number.isFinite(row.remaining_after_high_usd))
    && (row.would_exceed_budget === null || typeof row.would_exceed_budget === "boolean")
    && typeof row.boot_ready === "boolean" && typeof row.available === "boolean"
    && typeof row.reason === "string" && typeof row.pricing_source_url === "string"
    && validWholeRunEnvelope(row.whole_run_envelope)
    && typeof row.pricing_verified_at === "string" && typeof row.pricing_expires_at === "string";
}

function validWholeRunEnvelope(value: unknown): boolean {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const row = value as Record<string, unknown>;
  if (row.schema_version !== 1 || row.projection_kind !== "admission_upper_bound"
    || !identifier(row.plan_sha256) || typeof row.maximum_usd !== "string"
    || !Number.isFinite(Number(row.maximum_usd)) || Number(row.maximum_usd) <= 0
    || row.forecast_usd_low !== null || row.forecast_usd_high !== null
    || row.forecast_status !== "not_measured" || !Array.isArray(row.roles)) return false;
  const expectedRoles = ["decomposer", "evidence_retriever", "parameter_extractor", "connector", "synthesizer", "knowledge_extractor"];
  let summedMaximum = 0;
  const valid = row.roles.length === expectedRoles.length && row.roles.every((item, index) => {
    if (!item || typeof item !== "object" || Array.isArray(item)) return false;
    const role = item as Record<string, unknown>;
    const routeMaximum = Number(role.route_max_usd);
    const roleMaximum = Number(role.role_max_usd);
    const selectedRouteOnly = role.role === "synthesizer";
    summedMaximum += roleMaximum;
    return role.role === expectedRoles[index]
      && Number.isInteger(role.mandatory_calls) && Number(role.mandatory_calls) >= 0
      && Number.isInteger(role.conditional_calls) && Number(role.conditional_calls) >= 0
      && Number.isInteger(role.max_calls)
      && Number(role.max_calls) === Number(role.mandatory_calls) + Number(role.conditional_calls)
      && role.selected_route_only === selectedRouteOnly
      && typeof role.route_max_usd === "string" && Number.isFinite(routeMaximum) && routeMaximum > 0
      && typeof role.role_max_usd === "string" && Number.isFinite(roleMaximum) && roleMaximum > 0
      && Math.abs(roleMaximum - routeMaximum * Number(role.max_calls)) < 0.00000002
      && Array.isArray(role.pricing_fingerprints) && role.pricing_fingerprints.length > 0
      && role.pricing_fingerprints.every((value) => typeof value === "string" && /^[a-f0-9]{64}$/u.test(value));
  });
  return valid && /^[a-f0-9]{64}$/u.test(String(row.plan_sha256))
    && Math.abs(summedMaximum - Number(row.maximum_usd)) < 0.00000002;
}

function validContinuationQuote(value: unknown, command: AncestryContinuationCommand, contextSha256: string, planSha256: string, maximumUsd: string): value is AncestryContinuationQuote {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const row = value as Record<string, unknown>;
  return identifier(row.quote_token) && identifier(row.quote_id)
    && row.context_sha256 === contextSha256
    && row.receipt_sha256 === command.expected_receipt_sha256
    && row.selected_driver_role === "synthesizer"
    && row.selected_driver_provider === command.provider_id
    && row.selected_driver_model === command.model_id
    && row.selected_driver_pricing_fingerprint === command.pricing_fingerprint
    && row.workload_plan_sha256 === planSha256
    && row.whole_run_maximum_usd === maximumUsd
    && row.approved_run_ceiling_usd === command.approved_run_ceiling_usd.toFixed(2)
    && typeof row.issued_at_ms === "number" && Number.isInteger(row.issued_at_ms)
    && typeof row.expires_at_ms === "number" && Number.isInteger(row.expires_at_ms) && row.expires_at_ms > Date.now()
    && row.view_format === "html" && row.spend_performed === false;
}

function validContinuationLaunch(value: unknown, command: AncestryContinuationCommand, investigationId: string, receiptId: string): value is AncestryContinuationLaunch {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const row = value as Record<string, unknown>;
  return identifier(row.investigation_id) && identifier(row.start_event_id)
    && row.status === "started" && row.view_format === "html"
    && row.parent_investigation_id === investigationId
    && row.ancestry_interrogation_receipt_id === receiptId
    && row.selected_driver_provider === command.provider_id
    && row.selected_driver_model === command.model_id;
}

export default function CollectiveContinuityBridge(props: { resume_ref?: unknown; interrogation_ref?: unknown }) {
  const reference = useMemo(() => parse(props.resume_ref), [props.resume_ref]);
  const interrogationReference = useMemo(() => parseInterrogation(props.interrogation_ref), [props.interrogation_ref]);
  const invalidInterrogationReference = props.interrogation_ref !== undefined && !interrogationReference;
  const { state: auth, sessionGeneration } = useAuth();
  const identity = reference && ("manifest_id" in reference
    ? `m:${reference.manifest_id}:${interrogationReference ? `${interrogationReference.investigation_id}:${interrogationReference.receipt_id}` : "ordinary"}`
    : `p:${reference.plan_id}`);
  const current = useRef({ sessionGeneration, identity });
  const decision = useRef("");
  current.current = { sessionGeneration, identity };
  const [projection, setProjection] = useState<unknown>(null);
  const [unavailable, setUnavailable] = useState(false);
  const [running, setRunning] = useState(false);
  const [selectedRoute, setSelectedRoute] = useState<string | null>(null);
  const [researchTier, setResearchTier] = useState<"fast" | "deep" | "wrestle">("deep");
  const [ceiling, setCeiling] = useState("2.00");
  const [quote, setQuote] = useState<AncestryContinuationQuote | null>(null);
  const [started, setStarted] = useState<AncestryContinuationLaunch | null>(null);

  const load = (signal?: AbortSignal) => {
    if (!reference || invalidInterrogationReference) return Promise.reject(new Error("invalid reference"));
    return "manifest_id" in reference
      ? Promise.all([
        fetchCollectiveManifestReference(reference.manifest_id, signal).then((manifest) =>
          projectCollectiveManifest(reference.manifest_id, signal).then((unit) => ({ manifest, unit }))),
        interrogationReference
          ? getReasoningAncestryInterrogation(interrogationReference.investigation_id, interrogationReference.receipt_id, signal)
          : Promise.resolve(null),
        interrogationReference
          ? getAncestryContinuationOptions(interrogationReference.investigation_id, interrogationReference.receipt_id, signal)
          : Promise.resolve(null),
      ])
      : fetchCollectiveCouncilReference(reference.plan_id, signal);
  };

  useEffect(() => {
    const abort = new AbortController();
    const request = { sessionGeneration, identity };
    setProjection(null); setUnavailable(false); setRunning(false); setSelectedRoute(null); setQuote(null); setStarted(null);
    if (!reference || invalidInterrogationReference || auth.status !== "authenticated") { setUnavailable(true); return () => abort.abort(); }
    void load(abort.signal).then((value) => {
      if (!abort.signal.aborted && current.current.sessionGeneration === request.sessionGeneration && current.current.identity === request.identity) setProjection(value);
    }).catch((error: unknown) => {
      if (!abort.signal.aborted && !(error instanceof DOMException && error.name === "AbortError") && current.current.sessionGeneration === request.sessionGeneration && current.current.identity === request.identity) setUnavailable(true);
    });
    return () => abort.abort();
  // `load` is deliberately scoped to the exact identity below.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [auth.status, identity, invalidInterrogationReference, reference, sessionGeneration]);

  if (unavailable) return <div role="alert" data-testid="collective-continuity-unavailable">This collective is unavailable under the current account.</div>;
  if (projection === null) return <div role="status" data-testid="collective-continuity-loading">Loading current collective…</div>;

  if (reference && "plan_id" in reference) {
    const safe = council(projection);
    if (!safe) return <div role="alert">The council reference failed validation.</div>;
    return <article className="grid gap-3 p-4" data-testid="collective-continuity-ready">
      <h2>Research council</h2>
      <p className="whitespace-pre-wrap">{safe.plan.shared_prompt}</p>
      <p className="font-mono text-xs">{safe.plan.state} · approved ceiling {safe.plan.approved_ceiling_cents}¢</p>
      {safe.plan.state === "approved" && !safe.result ? <button disabled={running} onClick={() => {
        const operation = { sessionGeneration, identity };
        setRunning(true);
        void runCollectiveCouncil(safe.plan.plan_id).then(() => load()).then((value) => {
          if (current.current.sessionGeneration === operation.sessionGeneration && current.current.identity === operation.identity) setProjection(value);
        }).catch(() => {
          if (current.current.sessionGeneration === operation.sessionGeneration && current.current.identity === operation.identity) setUnavailable(true);
        }).finally(() => {
          if (current.current.sessionGeneration === operation.sessionGeneration && current.current.identity === operation.identity) setRunning(false);
        });
      }}>Run approved council · maximum {safe.plan.approved_ceiling_cents}¢</button> : null}
      {safe.result ? <><p>Result: {safe.result.state} · spent {safe.result.spent_cents}¢ · held {safe.result.held_cents}¢</p>{safe.result.html ? <div dangerouslySetInnerHTML={{ __html: sanitizeHostedHtml(safe.result.html) }} /> : null}</> : null}
    </article>;
  }

  const manifestId = reference && "manifest_id" in reference ? reference.manifest_id : null;
  if (!manifestId) return <div role="alert">The collective reference failed validation.</div>;
  const [collectiveProjection, interrogation, continuationOptions] = projection as [unknown, ReasoningAncestryInterrogationResponse | null, AncestryContinuationOptions | null];
  const bundle = collectiveProjection as { manifest?: Record<string, unknown>; unit?: unknown };
  const unit = bundle.unit as { collective_id?: unknown; ordered_spawn_ids?: unknown; prompt_block?: unknown };
  if (typeof unit.collective_id !== "string" || !Array.isArray(unit.ordered_spawn_ids) || typeof unit.prompt_block !== "string") return <div role="alert">The collective reference failed validation.</div>;
  if (interrogation && (
    interrogation.status !== "accepted"
    || interrogation.manifest.manifest_id !== manifestId
    || interrogation.receipt.manifest_id !== manifestId
    || interrogation.receipt.collective_id !== unit.collective_id
    || interrogation.manifest.collective_id !== unit.collective_id
    || JSON.stringify(interrogation.receipt.ordered_spawn_ids) !== JSON.stringify(unit.ordered_spawn_ids)
    || JSON.stringify(interrogation.manifest.ordered_spawn_ids) !== JSON.stringify(unit.ordered_spawn_ids)
    || bundle.manifest?.collective_id !== unit.collective_id
    || bundle.manifest?.membership_sha256 !== interrogation.receipt.membership_sha256
    || bundle.manifest?.membership_sha256 !== interrogation.manifest.membership_sha256
    || interrogation.receipt.question.trim() !== interrogation.receipt.question
    || !interrogation.receipt.question
  )) return <div role="alert">The interrogation reference failed validation.</div>;
  if (interrogation && (
    !continuationOptions
    || continuationOptions.schema_version !== 1
    || continuationOptions.view_format !== "html"
    || continuationOptions.action_authority !== false
    || continuationOptions.whole_run_cost_projected !== true
    || continuationOptions.investigation_id !== interrogationReference?.investigation_id
    || continuationOptions.receipt_id !== interrogationReference.receipt_id
    || continuationOptions.receipt_sha256 !== interrogation.receipt.receipt_sha256
    || !identifier(continuationOptions.context_sha256)
    || !Array.isArray(continuationOptions.choices)
    || continuationOptions.choices.some((choice) => !validContinuationChoice(choice))
  )) return <div role="alert">The continuation options failed validation.</div>;
  const options = continuationOptions?.choices ?? [];
  const usable = options.filter((choice) => choice.available && choice.boot_ready && choice.role === "synthesizer");
  const routeId = selectedRoute ?? usable[0]?.route_identity ?? null;
  const choice = usable.find((row) => row.route_identity === routeId) ?? null;
  const ceilingNumber = Number(ceiling);
  const command: AncestryContinuationCommand | null = interrogation && choice && Number.isFinite(ceilingNumber) && ceilingNumber > 0 && ceilingNumber <= 100 ? {
    expected_receipt_sha256: interrogation.receipt.receipt_sha256,
    provider_id: choice.provider_id,
    model_id: choice.model_id,
    pricing_fingerprint: choice.pricing_fingerprint,
    research_tier: researchTier,
    approved_run_ceiling_usd: ceilingNumber,
  } : null;
  const decisionFingerprint = JSON.stringify(command);
  decision.current = decisionFingerprint;
  const remainingBudget = typeof continuationOptions?.budget.remaining_usd === "number" && Number.isFinite(continuationOptions.budget.remaining_usd) ? continuationOptions.budget.remaining_usd : null;
  const ceilingOverBudget = command !== null && remainingBudget !== null && command.approved_run_ceiling_usd > remainingBudget;
  const wholeRunMaximum = choice ? Number(choice.whole_run_envelope.maximum_usd) : null;
  const ceilingBelowEnvelope = command !== null && wholeRunMaximum !== null && command.approved_run_ceiling_usd < wholeRunMaximum;
  return <article className="grid gap-3 p-4" data-testid="collective-continuity-ready">
    <h2>{interrogation ? "Reasoning ancestry collective" : "Collective research"}</h2>
    <p className="font-mono text-xs">{unit.collective_id} · {unit.ordered_spawn_ids.length} members</p>
    {interrogation ? <section aria-label="Immutable interrogation question" className="rounded border border-rule bg-ice-1 p-3">
      <p className="text-[10px] font-semibold uppercase tracking-wide text-ocean">Owner interrogation question</p>
      <p className="mt-1 whitespace-pre-wrap font-semibold">{interrogation.receipt.question}</p>
      <p className="mt-1 text-[10px] text-ink-mute">Exact ancestry closure {interrogation.receipt.closure_ordinals.join(", ")}{interrogation.stale ? " · historical claim head" : " · current claim head"} · no provider or spend authority.</p>
    </section> : null}
    <pre className="whitespace-pre-wrap">{interrogation ? `## Interrogation question\n${interrogation.receipt.question}\n\n${unit.prompt_block}` : unit.prompt_block}</pre>
    {interrogation && continuationOptions ? <section aria-label="Continuation decision tree" className="grid gap-3 rounded border border-rule p-3">
      <div><h3 className="font-semibold">Choose the exact synthesis model</h3><p className="text-xs text-ink-mute">This exact choice governs synthesis; the continuation is a multi-role research run whose other signed routes may use other models. Reviewing does not reserve, call, or spend.</p></div>
      {options.map((row) => <label key={row.route_identity} className="flex gap-2 rounded border border-rule p-2">
        <input type="radio" name={`continuation-${interrogation.receipt.receipt_id}`} disabled={!row.available} checked={routeId === row.route_identity} onChange={() => { setSelectedRoute(row.route_identity); setQuote(null); setStarted(null); }} />
        <span><strong>{row.model_id}</strong> · {row.provider_id}<br /><span className="text-xs">Selected synthesis call only: ${row.estimated_usd_low.toFixed(4)}–${row.estimated_usd_high.toFixed(4)}. Whole-run admission upper bound: ${Number(row.whole_run_envelope.maximum_usd).toFixed(4)}; this is not expected spend. · {row.reason}</span></span>
      </label>)}
      {choice ? <details><summary>Whole-run upper-bound breakdown</summary><ul className="mt-2 grid gap-1 text-xs">{choice.whole_run_envelope.roles.map((row) => <li key={row.role}><strong>{row.role}</strong>: {row.max_calls} calls maximum ({row.mandatory_calls} mandatory + {row.conditional_calls} conditional) · ${Number(row.role_max_usd).toFixed(4)}</li>)}</ul><p className="mt-2 text-xs">Forecast: NOT MEASURED. Actual spend is governed by per-call reservations and may be lower.</p></details> : null}
      <div className="flex flex-wrap gap-2"><label>Research depth <select value={researchTier} onChange={(event) => { setResearchTier(event.target.value as typeof researchTier); setQuote(null); setStarted(null); }}><option value="fast">Fast</option><option value="deep">Deep</option><option value="wrestle">Wrestle</option></select></label><label>Hard whole-run maximum USD <input aria-label="Maximum continuation spend in USD" type="number" min="0.01" max="100" step="0.01" value={ceiling} onChange={(event) => { setCeiling(event.target.value); setQuote(null); setStarted(null); }} /></label></div>
      <p className="text-xs">{remainingBudget === null
        ? "Remaining daily budget is unknown; the per-run ceiling still applies."
        : command === null
          ? `Known remaining daily budget: $${remainingBudget.toFixed(2)} · enter a valid whole-run maximum to project its impact.`
          : `Known remaining daily budget: $${remainingBudget.toFixed(2)} · after approved ceiling: $${(remainingBudget - command.approved_run_ceiling_usd).toFixed(2)}`}</p>
      {ceilingBelowEnvelope ? <p role="note" className="text-xs text-caution">Your hard ceiling is below the structural upper bound. The ledger may stop conditional work before the complete plan runs.</p> : null}
      {!quote ? <button disabled={!command || running || ceilingOverBudget} onClick={() => {
        if (!command || !interrogationReference || !choice) return;
        const selectedEnvelope = choice.whole_run_envelope;
        const operation = { sessionGeneration, identity, decisionFingerprint }; setRunning(true);
        void quoteAncestryContinuation(interrogationReference.investigation_id, interrogationReference.receipt_id, command).then((value) => {
          if (current.current.sessionGeneration === operation.sessionGeneration && current.current.identity === operation.identity && decision.current === operation.decisionFingerprint && validContinuationQuote(value, command, continuationOptions.context_sha256, selectedEnvelope.plan_sha256, selectedEnvelope.maximum_usd)) setQuote(value);
        }).catch(() => {
          if (current.current.sessionGeneration === operation.sessionGeneration && current.current.identity === operation.identity) setUnavailable(true);
        }).finally(() => {
          if (current.current.sessionGeneration === operation.sessionGeneration && current.current.identity === operation.identity) setRunning(false);
        });
      }}>Review exact quote</button> : <div className="grid gap-2 rounded bg-ice-1 p-2"><p className="text-xs">Quote expires {new Date(quote.expires_at_ms).toLocaleTimeString()} · ceiling ${quote.approved_run_ceiling_usd} · no spend yet.</p><button disabled={!command || running || Boolean(started)} onClick={() => {
        if (!command || !interrogationReference) return;
        const operation = { sessionGeneration, identity, decisionFingerprint }; setRunning(true);
        void launchAncestryContinuation(interrogationReference.investigation_id, interrogationReference.receipt_id, { ...command, research_quote_token: quote.quote_token }).then((value) => {
          if (current.current.sessionGeneration === operation.sessionGeneration && current.current.identity === operation.identity && decision.current === operation.decisionFingerprint && validContinuationLaunch(value, command, interrogationReference.investigation_id, interrogationReference.receipt_id)) setStarted(value);
        }).catch(() => {
          if (current.current.sessionGeneration === operation.sessionGeneration && current.current.identity === operation.identity && decision.current === operation.decisionFingerprint) setUnavailable(true);
        }).finally(() => {
          if (current.current.sessionGeneration === operation.sessionGeneration && current.current.identity === operation.identity) setRunning(false);
        });
      }}>Start quoted continuation</button></div>}
      {started ? <p role="status">Started <a className="underline" href={`/inv/${encodeURIComponent(started.investigation_id)}`}>open research workstation</a> · {started.selected_driver_model}</p> : null}
    </section> : null}
  </article>;
}
