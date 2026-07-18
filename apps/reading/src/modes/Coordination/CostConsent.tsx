import { useCallback, useEffect, useState } from "react";

import { LemonCard, LemonTable, LemonTag } from "../../components/lemon";
import type { LemonColumn } from "../../components/lemon";
import { apiFetch } from "../../lib/api";
import { emitWernerExperience } from "../../werner/reactionBus";

/**
 * CostConsent — one operator view of money + permissions across the four
 * workflows (antiek-unified SPR-07). Read-only.
 *
 * Two views, both derived on read from canonical sources this mode never
 * writes:
 *
 *  - Cost: per-workflow + aggregate realized inference cost summed from the
 *    DispatchCall event log (incl. SPR-02 remote-exec), GET /coordination/cost.
 *    Margins shown only where the economics matrix is built; honestly stubbed
 *    otherwise — no fabricated margin on a money screen.
 *  - Escrow / consent: per-IP-holder consent state, escrow balance (accruing),
 *    and servability, GET /coordination/consent. Accrual ≠ disbursement: every
 *    balance is labeled with its disbursement gate (read from the SPR-05 gate
 *    ledger), a zero-buyer balance is honestly $0, and NOTHING here disburses.
 *
 * Slots into the SPR-04 shared/operator bucket, beside the SPR-05 Coordination
 * mode. There is NO disbursement control on this surface — payout activation is
 * operator-only after G2+G3, and lives nowhere in this mode. (Proven absent by
 * tests/test_cost_consent_no_disbursement.py, which greps this file.)
 */

// ── Wire shapes (mirror the coordination API response models) ────────────────

export interface WorkflowCostView {
  workflow: string; // research | read | write | speak | unmapped
  raw_cost_usd: string;
  call_count: number;
  remote_exec_cost_usd: string;
  margin_status: string; // applied | stubbed
  margin_rate: string | null;
  margined_cost_usd: string | null;
  margin_note: string;
}

export interface CostView {
  per_workflow: WorkflowCostView[];
  aggregate_raw_cost_usd: string;
  aggregate_call_count: number;
  aggregate_remote_exec_cost_usd: string;
  has_unmapped_spend: boolean;
  events_dir: string;
}

export interface DisbursementGateView {
  disbursable: boolean; // always false on this surface
  open_gate_ids: string[];
  holder_claimed: boolean;
  fully_unlocked: boolean;
  label: string;
}

export interface IpHolderConsentView {
  ip_holder_id: string;
  display_name: string;
  status: string;
  escrow_balance_usd: string;
  gate: DisbursementGateView;
  serves_full_text: boolean | null;
  servability_note: string | null;
}

export interface EscrowReportView {
  pre_onboarded: number;
  invited: number;
  claimed: number;
  opted_out: number;
  claim_rate: number;
  total_escrow_accrued_cents: number;
  total_escrow_paid_cents: number;
  unclaimed_escrow_cents: number;
  publishers_with_nontrivial_accrual: number;
}

export interface ConsentView {
  holders: IpHolderConsentView[];
  escrow_report: EscrowReportView;
  disbursement_gates_open: string[];
  total_escrow_accruing_usd: string;
  any_disbursable: boolean;
  gate_source_path: string;
}

// ── Formatting helpers ───────────────────────────────────────────────────────

/** Render a stringified-Decimal USD amount as $X.XXXX (keeps the ledger's
 *  micro-cent precision visible — these are realized costs, not rounded). */
function usd(s: string): string {
  const n = Number(s);
  if (!Number.isFinite(n)) return `$${s}`;
  // Up to 4 decimals so a $0.0001 dispatch cost is not rounded to $0.00.
  return `$${n.toFixed(n < 1 ? 4 : 2)}`;
}

function centsToUsd(c: number): string {
  return `$${(c / 100).toFixed(2)}`;
}

const workflowLabel: Record<string, string> = {
  research: "Research",
  read: "Read",
  write: "Write",
  speak: "Speak",
  unmapped: "Unclassified",
};

// ── Cost view (presentational) ───────────────────────────────────────────────

export function CostSection({ cost }: { cost: CostView }) {
  const columns: LemonColumn<WorkflowCostView>[] = [
    {
      key: "workflow",
      header: "Workflow",
      width: "20%",
      render: (w) => (
        <span className="flex items-center gap-2">
          <LemonTag colour={w.workflow === "unmapped" ? "danger" : "default"}>
            {workflowLabel[w.workflow] ?? w.workflow}
          </LemonTag>
        </span>
      ),
    },
    {
      key: "raw",
      header: "Realized cost",
      width: "18%",
      render: (w) => (
        <span className="font-mono text-sm text-ink dark:text-bright">
          {usd(w.raw_cost_usd)}
        </span>
      ),
    },
    {
      key: "calls",
      header: "Calls",
      width: "10%",
      render: (w) => (
        <span className="font-mono text-xs text-shadow-2 dark:text-moonlight">
          {w.call_count}
        </span>
      ),
    },
    {
      key: "remote",
      header: "of which remote-exec",
      width: "20%",
      render: (w) =>
        Number(w.remote_exec_cost_usd) > 0 ? (
          <span className="font-mono text-xs text-ink dark:text-bright">
            {usd(w.remote_exec_cost_usd)}
          </span>
        ) : (
          <span className="text-xs text-shadow-1 dark:text-moonlight">—</span>
        ),
    },
    {
      key: "margin",
      header: "Margin",
      render: (w) =>
        w.margin_status === "applied" && w.margined_cost_usd !== null ? (
          <span className="flex flex-col">
            <span className="font-mono text-sm text-ink dark:text-bright">
              {usd(w.margined_cost_usd)}
            </span>
            <span className="text-[11px] text-shadow-1 dark:text-moonlight">
              {w.margin_rate !== null
                ? `+${(Number(w.margin_rate) * 100).toFixed(0)}%`
                : "applied"}
            </span>
          </span>
        ) : (
          <span className="flex items-center gap-2">
            <LemonTag colour="sun">stubbed</LemonTag>
            <span className="text-[11px] italic text-shadow-1 dark:text-moonlight">
              raw cost only
            </span>
          </span>
        ),
    },
  ];

  return (
    <section className="space-y-4">
      <header className="space-y-1">
        <h2 className="text-lg font-serif text-ink dark:text-bright">
          Inference cost
        </h2>
        <p className="text-sm text-ink-soft dark:text-starlight leading-relaxed">
          Per-workflow and aggregate realized spend, summed from the dispatch
          event log — including remote-exec fan-out. Every figure is real cost,
          never an estimate. An idle instance reads $0. Margins are shown only
          where the economics matrix is built; the rest are honestly stubbed
          rather than fabricated on a money screen.
        </p>
      </header>

      {/* Aggregate banner — the operator's "what am I spending in total". */}
      <LemonCard colour="glacial" elevation="z1">
        <div className="p-4 flex flex-wrap items-baseline gap-x-8 gap-y-2">
          <div className="space-y-0.5">
            <p className="text-[10px] font-mono uppercase tracking-wide text-shadow-1 dark:text-moonlight">
              Aggregate realized cost
            </p>
            <p className="text-xl font-mono text-ink dark:text-bright">
              {usd(cost.aggregate_raw_cost_usd)}
            </p>
          </div>
          <div className="space-y-0.5">
            <p className="text-[10px] font-mono uppercase tracking-wide text-shadow-1 dark:text-moonlight">
              Dispatch calls
            </p>
            <p className="text-sm font-mono text-ink dark:text-bright">
              {cost.aggregate_call_count}
            </p>
          </div>
          <div className="space-y-0.5">
            <p className="text-[10px] font-mono uppercase tracking-wide text-shadow-1 dark:text-moonlight">
              of which remote-exec
            </p>
            <p className="text-sm font-mono text-ink dark:text-bright">
              {usd(cost.aggregate_remote_exec_cost_usd)}
            </p>
          </div>
        </div>
      </LemonCard>

      <LemonTable<WorkflowCostView>
        rows={cost.per_workflow}
        columns={columns}
        rowKey={(w) => w.workflow}
        dense
        emptyState={
          <span className="text-xs italic text-shadow-1 dark:text-moonlight">
            No dispatch events — idle instance, $0 spend.
          </span>
        }
      />

      {cost.has_unmapped_spend && (
        <p className="text-xs text-emperor dark:text-emperor">
          Some spend could not be attributed to a workflow (Unclassified above).
          It is still counted in the aggregate; the role→workflow map needs an
          entry for the dispatch role(s) involved.
        </p>
      )}
    </section>
  );
}

// ── Escrow / consent view (presentational) ───────────────────────────────────

export function ConsentSection({ consent }: { consent: ConsentView }) {
  const gatesOpen = consent.disbursement_gates_open;

  const columns: LemonColumn<IpHolderConsentView>[] = [
    {
      key: "holder",
      header: "IP holder",
      width: "22%",
      render: (h) => (
        <span className="text-sm text-ink dark:text-bright">
          {h.display_name}
        </span>
      ),
    },
    {
      key: "status",
      header: "Opt-in state",
      width: "16%",
      render: (h) => (
        <LemonTag colour={h.status === "claimed" ? "aurora" : "muted"}>
          {h.status.replace(/_/g, " ")}
        </LemonTag>
      ),
    },
    {
      key: "escrow",
      header: "Escrow (accruing)",
      width: "16%",
      render: (h) => (
        <span className="font-mono text-sm text-ink dark:text-bright">
          {usd(h.escrow_balance_usd)}
        </span>
      ),
    },
    {
      key: "gate",
      header: "Disbursement",
      render: (h) => (
        <span className="flex flex-col gap-1">
          <LemonTag colour={h.gate.fully_unlocked ? "sun" : "muted"} dot>
            {h.gate.disbursable ? "disbursable" : "not disbursable"}
          </LemonTag>
          <span className="text-[11px] text-shadow-2 dark:text-moonlight leading-snug">
            {h.gate.label}
          </span>
        </span>
      ),
    },
    {
      key: "servability",
      header: "Servability",
      width: "18%",
      render: (h) =>
        h.serves_full_text === null ? (
          <span className="text-[11px] italic text-shadow-1 dark:text-moonlight">
            not surfaced here
          </span>
        ) : (
          <span className="flex flex-col gap-0.5">
            <LemonTag colour={h.serves_full_text ? "aurora" : "muted"}>
              {h.serves_full_text ? "serves full text" : "gated"}
            </LemonTag>
            {h.servability_note && (
              <span className="text-[11px] text-shadow-2 dark:text-moonlight leading-snug">
                {h.servability_note}
              </span>
            )}
          </span>
        ),
    },
  ];

  return (
    <section className="space-y-4">
      <header className="space-y-1">
        <h2 className="text-lg font-serif text-ink dark:text-bright">
          Escrow &amp; consent
        </h2>
        <p className="text-sm text-ink-soft dark:text-starlight leading-relaxed">
          Revenue accrues into per-IP-holder escrow from day one — even with
          zero buyers, where a balance is honestly $0. Disbursement is blocked
          until the legal gate clears (G2 lawyer review + G3 publisher opt-in,
          read live from the gate ledger) and the holder claims. This surface
          reports that gated reality; it has no control that disburses.
        </p>
      </header>

      {/* The gated-reality banner — the load-bearing honesty of this surface. */}
      <LemonCard colour={gatesOpen.length > 0 ? "card" : "glacial"} elevation="z1">
        <div className="p-4 space-y-2">
          <div className="flex flex-wrap items-center gap-3">
            <LemonTag colour={gatesOpen.length > 0 ? "danger" : "muted"} dot>
              {gatesOpen.length > 0
                ? `disbursement gated on ${gatesOpen.join("+")}`
                : "legal gate clear"}
            </LemonTag>
            {!consent.any_disbursable && (
              <span className="text-xs text-ink-soft dark:text-starlight">
                Nothing is disbursable on this surface.
              </span>
            )}
          </div>
          <div className="flex flex-wrap items-baseline gap-x-8 gap-y-1">
            <div>
              <span className="text-[10px] font-mono uppercase tracking-wide text-shadow-1 dark:text-moonlight">
                Total accruing
              </span>
              <p className="font-mono text-lg text-ink dark:text-bright">
                {usd(consent.total_escrow_accruing_usd)}
              </p>
            </div>
            <div>
              <span className="text-[10px] font-mono uppercase tracking-wide text-shadow-1 dark:text-moonlight">
                Disbursed
              </span>
              <p className="font-mono text-lg text-ink dark:text-bright">
                {centsToUsd(consent.escrow_report.total_escrow_paid_cents)}
              </p>
            </div>
            <div>
              <span className="text-[10px] font-mono uppercase tracking-wide text-shadow-1 dark:text-moonlight">
                Claim rate
              </span>
              <p className="font-mono text-sm text-ink dark:text-bright">
                {(consent.escrow_report.claim_rate * 100).toFixed(0)}%
              </p>
            </div>
          </div>
          <p className="text-[11px] font-mono text-shadow-1 dark:text-moonlight">
            gate state from {consent.gate_source_path}
          </p>
        </div>
      </LemonCard>

      <LemonTable<IpHolderConsentView>
        rows={consent.holders}
        columns={columns}
        rowKey={(h) => h.ip_holder_id}
        dense
        emptyState={
          <span className="text-xs italic text-shadow-1 dark:text-moonlight">
            No IP holders yet — escrow accrues once attribution events route
            revenue to a holder.
          </span>
        }
      />
    </section>
  );
}

// ── The mode (data-fetching shell) ───────────────────────────────────────────

export default function CostConsent() {
  const [cost, setCost] = useState<CostView | null>(null);
  const [consent, setConsent] = useState<ConsentView | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [costResp, consentResp] = await Promise.all([
        apiFetch("/coordination/cost"),
        apiFetch("/coordination/consent"),
      ]);
      if (!costResp.ok) {
        throw new Error(`GET /coordination/cost failed: HTTP ${costResp.status}`);
      }
      if (!consentResp.ok) {
        throw new Error(
          `GET /coordination/consent failed: HTTP ${consentResp.status}`,
        );
      }
      setCost((await costResp.json()) as CostView);
      setConsent((await consentResp.json()) as ConsentView);
      emitWernerExperience("highlight");
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
      emitWernerExperience("fail");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  return (
    <div className="flex flex-col h-screen">
      <main className="flex-1 overflow-y-auto bg-ice-0 dark:bg-charcoal-2">
        <div className="max-w-4xl mx-auto px-8 py-10 space-y-10">
          <header className="space-y-2">
            <h1 className="text-2xl font-serif text-ink dark:text-bright">
              Cost &amp; consent
            </h1>
            <p className="text-sm text-ink-soft dark:text-starlight leading-relaxed">
              What you are spending, what is accruing, what is gated, and who
              consented — one read-only surface across the four workflows. Every
              number traces to a canonical source: cost to the dispatch event
              log, escrow to the IP-holder ledger, gate state to the operator
              gate file. Nothing here disburses money.
            </p>
          </header>

          {loading && (
            <p className="text-sm text-shadow-1 dark:text-moonlight">
              Loading cost &amp; consent view…
            </p>
          )}
          {error && <p className="text-sm text-emperor">{error}</p>}

          {cost && <CostSection cost={cost} />}
          {consent && <ConsentSection consent={consent} />}
        </div>
      </main>
    </div>
  );
}
