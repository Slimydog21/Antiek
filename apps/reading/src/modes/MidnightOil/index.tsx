import { useState } from "react";

import {
  preflightMidnightOil,
  type MidnightOilPreflight,
  type MidnightOilRouteMode,
  type MidnightOilSourcePolicy,
} from "../../api/midnightOil";
import LemonCard from "../../components/lemon/LemonCard";

const ROUTE_MODES: Array<{ value: MidnightOilRouteMode; label: string }> = [
  { value: "auto_balanced", label: "Balanced" },
  { value: "auto_quality", label: "Quality" },
  { value: "auto_cost", label: "Cost" },
  { value: "auto_latency", label: "Latency" },
];

const SOURCES: Array<{ value: MidnightOilSourcePolicy; label: string }> = [
  { value: "arxiv", label: "arXiv" },
  { value: "substack", label: "Substack" },
  { value: "web", label: "Web" },
  { value: "operator_corpus", label: "My corpus" },
];

export default function MidnightOil() {
  const [goal, setGoal] = useState("");
  const [workMinutes, setWorkMinutes] = useState(120);
  const [priceCeiling, setPriceCeiling] = useState(25);
  const [routeMode, setRouteMode] = useState<MidnightOilRouteMode>("auto_balanced");
  const [sourcePolicy, setSourcePolicy] = useState<MidnightOilSourcePolicy[]>([
    "arxiv",
    "substack",
    "operator_corpus",
  ]);
  const [ack, setAck] = useState(false);
  const [preflight, setPreflight] = useState<MidnightOilPreflight | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setPreflight(null);
    try {
      const result = await preflightMidnightOil({
        goal,
        work_minutes: workMinutes,
        price_ceiling_usd: priceCeiling,
        route_mode: routeMode,
        source_policy: sourcePolicy,
        deliverable: "html_research_asset",
        operator_acknowledged_spend: ack,
      });
      setPreflight(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  function toggleSource(source: MidnightOilSourcePolicy) {
    setSourcePolicy((current) => {
      if (current.includes(source)) {
        return current.length === 1 ? current : current.filter((s) => s !== source);
      }
      return [...current, source];
    });
  }

  return (
    <div className="h-full overflow-y-auto bg-ice-2 dark:bg-space-2">
      <div className="mx-auto max-w-4xl px-6 py-8 space-y-6">
        <header className="space-y-2">
          <h1 className="text-2xl font-serif text-ink dark:text-bright">Midnight oil</h1>
          <p className="text-sm font-serif text-ink-soft dark:text-starlight leading-relaxed">
            Preflight an autonomous research swarm with an approved time box, price ceiling,
            route policy, source policy, and HTML asset contract.
          </p>
        </header>

        <LemonCard title="Preflight" elevation="z1">
          <form className="p-4 space-y-4" onSubmit={onSubmit}>
            <label className="block space-y-1">
              <span className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                Goal
              </span>
              <textarea
                value={goal}
                onChange={(event) => setGoal(event.target.value)}
                rows={5}
                required
                className="w-full rounded-md border border-rule dark:border-charcoal-1 bg-ice-0 dark:bg-charcoal-2 px-3 py-2 text-sm font-serif text-ink dark:text-bright"
                placeholder="Research the bottlenecks in widebody engine supply chains."
              />
            </label>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <label className="space-y-1">
                <span className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                  Work minutes
                </span>
                <input
                  type="number"
                  min={15}
                  max={720}
                  value={workMinutes}
                  onChange={(event) => setWorkMinutes(Number(event.target.value) || 15)}
                  className="w-full rounded-md border border-rule dark:border-charcoal-1 bg-ice-0 dark:bg-charcoal-2 px-3 py-1.5 text-sm font-mono text-ink dark:text-bright"
                />
              </label>
              <label className="space-y-1">
                <span className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                  Price ceiling USD
                </span>
                <input
                  type="number"
                  min={0.01}
                  step={0.01}
                  value={priceCeiling}
                  onChange={(event) => setPriceCeiling(Number(event.target.value) || 0.01)}
                  className="w-full rounded-md border border-rule dark:border-charcoal-1 bg-ice-0 dark:bg-charcoal-2 px-3 py-1.5 text-sm font-mono text-ink dark:text-bright"
                />
              </label>
              <label className="space-y-1">
                <span className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                  Route mode
                </span>
                <select
                  value={routeMode}
                  onChange={(event) => setRouteMode(event.target.value as MidnightOilRouteMode)}
                  className="w-full rounded-md border border-rule dark:border-charcoal-1 bg-ice-0 dark:bg-charcoal-2 px-3 py-1.5 text-sm font-mono text-ink dark:text-bright"
                >
                  {ROUTE_MODES.map((mode) => (
                    <option key={mode.value} value={mode.value}>
                      {mode.label}
                    </option>
                  ))}
                </select>
              </label>
            </div>

            <fieldset className="space-y-2">
              <legend className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                Source policy
              </legend>
              <div className="flex flex-wrap gap-2">
                {SOURCES.map((source) => {
                  const active = sourcePolicy.includes(source.value);
                  return (
                    <button
                      key={source.value}
                      type="button"
                      role="checkbox"
                      aria-checked={active}
                      onClick={() => toggleSource(source.value)}
                      className={
                        "rounded-md border px-3 py-1.5 text-xs font-mono " +
                        (active
                          ? "border-ink bg-ink text-white dark:border-bright dark:bg-bright dark:text-space"
                          : "border-rule dark:border-charcoal-1 text-ink dark:text-bright")
                      }
                    >
                      {source.label}
                    </button>
                  );
                })}
              </div>
            </fieldset>

            <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
              <label className="flex items-start gap-2 text-[12px] font-serif text-ink-soft dark:text-starlight">
                <input
                  type="checkbox"
                  checked={ack}
                  onChange={(event) => setAck(event.target.checked)}
                  className="mt-0.5"
                />
                <span>I approve this ceiling for a future run; this preflight still launches nothing.</span>
              </label>
              <button
                type="submit"
                disabled={busy || goal.trim().length === 0}
                className="shrink-0 rounded-md bg-ink px-3 py-1.5 text-xs font-mono text-white disabled:cursor-not-allowed disabled:opacity-50 dark:bg-bright dark:text-charcoal-3"
              >
                {busy ? "Checking..." : "Preflight"}
              </button>
            </div>
          </form>
        </LemonCard>

        {error && (
          <p className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-emperor">
            {error}
          </p>
        )}

        {preflight && (
          <LemonCard title="Run contract" elevation="z1">
            <div className="p-4 space-y-4" aria-live="polite">
              <div className="grid grid-cols-1 md:grid-cols-5 gap-3 font-mono text-[13px]">
                <Metric label="Accepted" value={preflight.accepted ? "yes" : "no"} />
                <Metric label="Run id" value={preflight.run_id ?? "not issued"} />
                <Metric
                  label="Planned budget"
                  value={`$${preflight.planned_budget_usd.toFixed(2)}`}
                />
                <Metric
                  label="Unallocated"
                  value={`$${preflight.unallocated_budget_usd.toFixed(2)}`}
                />
                <Metric label="Final format" value={preflight.artifact_contract.final_format} />
              </div>

              {!preflight.accepted && preflight.denial_reason && (
                <p className="text-sm font-mono text-emperor">{preflight.denial_reason}</p>
              )}

              {preflight.role_plans.length > 0 && (
                <div>
                  <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                    Role allocation
                  </p>
                  <ul className="mt-2 grid grid-cols-1 md:grid-cols-2 gap-2">
                    {preflight.role_plans.map((plan) => (
                      <li
                        key={plan.role}
                        className="rounded-md border border-rule dark:border-charcoal-1 px-3 py-2 font-mono text-[12px]"
                      >
                        <div className="flex items-center justify-between gap-2">
                          <span className="font-semibold text-ink dark:text-bright">{plan.role}</span>
                          <span className="text-shadow-1 dark:text-moonlight">
                            ${plan.budget_usd.toFixed(2)} / {plan.max_minutes}m
                          </span>
                        </div>
                        <p className="mt-1 truncate text-shadow-1 dark:text-moonlight">
                          {plan.planned_route_receipt_id}
                        </p>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              <div className="grid grid-cols-1 md:grid-cols-3 gap-2 font-mono text-[12px]">
                <Metric
                  label="Twin notes"
                  value={preflight.artifact_contract.twin_note_document_required ? "required" : "not required"}
                />
                <Metric
                  label="Route receipts"
                  value={preflight.artifact_contract.route_receipt_links_required ? "required" : "not required"}
                />
                <Metric
                  label="Source receipts"
                  value={preflight.artifact_contract.source_receipt_links_required ? "required" : "not required"}
                />
              </div>

              {preflight.launch_packet && (
                <div className="rounded-md border border-rule dark:border-charcoal-1 px-3 py-2">
                  <div className="flex flex-col gap-1 md:flex-row md:items-center md:justify-between">
                    <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                      Launch packet
                    </p>
                    <p className="font-mono text-[12px] text-ink dark:text-bright">
                      {preflight.launch_packet.packet_id}
                    </p>
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-3 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Dispatch"
                      value={preflight.launch_packet.dispatch_allowed ? "enabled" : "disabled"}
                    />
                    <Metric
                      label="Budget reserve"
                      value={preflight.launch_packet.budget_reserved ? "reserved" : "not reserved"}
                    />
                    <Metric
                      label="Provider calls"
                      value={preflight.launch_packet.provider_calls_made ? "made" : "none"}
                    />
                  </div>
                  <p className="mt-2 text-[11px] text-ink-soft dark:text-starlight">
                    {preflight.launch_packet.role_count} roles inherit this packet and must attach route
                    and source receipts before the final HTML asset.
                  </p>
                </div>
              )}

              {preflight.approval_receipt && (
                <div className="rounded-md border border-rule dark:border-charcoal-1 px-3 py-2">
                  <div className="flex flex-col gap-1 md:flex-row md:items-center md:justify-between">
                    <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                      Approval receipt
                    </p>
                    <p className="font-mono text-[12px] text-ink dark:text-bright">
                      {preflight.approval_receipt.receipt_id}
                    </p>
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-3 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Scope"
                      value={preflight.approval_receipt.approval_scope.replaceAll("_", " ")}
                    />
                    <Metric
                      label="Runner apply"
                      value={preflight.approval_receipt.runner_apply_required ? "required" : "not required"}
                    />
                    <Metric
                      label="Approved ceiling"
                      value={`$${preflight.approval_receipt.approved_price_ceiling_usd.toFixed(2)}`}
                    />
                  </div>
                  <p className="mt-2 text-[11px] text-ink-soft dark:text-starlight">
                    Bound to {preflight.approval_receipt.launch_packet_id}; no dispatch, budget
                    reservation, provider calls, or graph mutation happens in this receipt.
                  </p>
                </div>
              )}

              {preflight.runner_handoff && (
                <div className="rounded-md border border-rule dark:border-charcoal-1 px-3 py-2">
                  <div className="flex flex-col gap-1 md:flex-row md:items-center md:justify-between">
                    <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                      Runner handoff
                    </p>
                    <p className="font-mono text-[12px] text-ink dark:text-bright">
                      {preflight.runner_handoff.handoff_id}
                    </p>
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-3 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Status"
                      value={preflight.runner_handoff.status.replaceAll("_", " ")}
                    />
                    <Metric
                      label="Dispatch"
                      value={preflight.runner_handoff.dispatch_performed ? "dispatched" : "not dispatched"}
                    />
                    <Metric
                      label="Graph"
                      value={preflight.runner_handoff.graph_mutated ? "mutated" : "unchanged"}
                    />
                  </div>
                  <p className="mt-2 text-[11px] text-ink-soft dark:text-starlight">
                    Requires {preflight.runner_handoff.prerequisite_receipt_ids.length} prior receipts;
                    no budget reservation or provider call has happened.
                  </p>
                </div>
              )}

              {preflight.applied_run_receipt && (
                <div className="rounded-md border border-rule dark:border-charcoal-1 px-3 py-2">
                  <div className="flex flex-col gap-1 md:flex-row md:items-center md:justify-between">
                    <p className="text-[11px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
                      Applied run
                    </p>
                    <p className="font-mono text-[12px] text-ink dark:text-bright">
                      {preflight.applied_run_receipt.receipt_id}
                    </p>
                  </div>
                  <div className="mt-2 grid grid-cols-1 md:grid-cols-3 gap-2 font-mono text-[12px]">
                    <Metric
                      label="Status"
                      value={preflight.applied_run_receipt.status.replaceAll("_", " ")}
                    />
                    <Metric
                      label="Retrieval"
                      value={preflight.applied_run_receipt.retrieval_performed ? "performed" : "not performed"}
                    />
                    <Metric
                      label="Artifact"
                      value={preflight.applied_run_receipt.final_artifact_created ? "created" : "not created"}
                    />
                  </div>
                  <p className="mt-2 text-[11px] text-ink-soft dark:text-starlight">
                    {preflight.applied_run_receipt.planned_role_count} planned roles; dry receipt only,
                    with no dispatch, budget reservation, provider call, retrieval, or graph mutation.
                  </p>
                </div>
              )}

              {preflight.notes.map((note) => (
                <p key={note} className="text-[11px] text-ink-soft dark:text-starlight">
                  {note}
                </p>
              ))}
            </div>
          </LemonCard>
        )}
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-rule dark:border-charcoal-1 px-3 py-2">
      <p className="text-[10px] uppercase tracking-wider text-shadow-1 dark:text-moonlight">
        {label}
      </p>
      <p className="mt-1 text-ink dark:text-bright">{value}</p>
    </div>
  );
}
