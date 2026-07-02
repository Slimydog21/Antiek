import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { apiFetch } from "../../lib/api";

interface PublisherSummary {
  ip_holder_id: string;
  display_name: string;
  legal_contact_email: string | null;
  status: string;
  escrow_balance_usd: string;
  notification_sent_at: string | null;
  claimed_at: string | null;
  opted_out_at: string | null;
}

interface StatsResponse {
  counts: Record<string, number>;
  warnings: string[];
}

interface PayoutTransfer {
  status: string;
  amount_usd_cents: number;
  initiated_at: string | null;
}

interface CompositeSnapshot {
  stats: StatsResponse | null;
  pendingDeletions: number;
  recentPayouts: PayoutTransfer[];
  coordination: CoordinationSummary | null;
  marketplace: MarketplaceSummary | null;
  federation: FederationSummary | null;
  trust: TrustSummary | null;
  billing: BillingSummary | null;
  investigations: InvestigationSummary | null;
  outcomes: OutcomeSummary | null;
}

interface OutcomeSummary {
  total: number;
  operator_reviews: number;
  other_reviews: number;
  dated_reviews: number;
}

interface InvestigationSummary {
  total: number;
  in_progress: number;
  completed: number;
  failed: number;
  total_cost_usd: number;
}

interface BillingSummary {
  period: string;
  free_tokens_consumed: number;
  free_tokens_remaining: number;
  total_margin_usd: string;
  total_billable_usd: string;
  record_count: number;
}

interface TrustSummary {
  privacy_budget_total: number;
  deletion_sla_days: number;
  substrate_control_count: number;
  compliance_framework_count: number;
  loop_3_checked_count: number;
  loop_3_total_count: number;
  loop_3_all_evidence_passed: boolean;
}

interface FederationSummary {
  allowed_partner_substrates: string[];
  require_opt_in_for_outbound_citations: boolean;
  require_attribution_for_outbound_citations: boolean;
}

interface MarketplaceSummary {
  health: "healthy" | "watch" | "unhealthy";
  health_signals: string[];
  creators: {
    creator_count: number;
    total_paid_cents: number;
  };
  publishers: {
    claim_rate: number;
    total_escrow_accrued_cents: number;
    unclaimed_escrow_cents: number;
  };
  advertisers: {
    advertiser_count_current: number;
    retention_rate: number;
    total_spend_current_cents: number;
    crosses_self_service_threshold: boolean;
  };
}

interface CoordinationSummary {
  operatorGate: {
    gate_id: string;
    title: string;
    status_raw: string;
    owner: string | null;
    blocks: string | null;
  } | null;
  operatorActions: {
    open_count: number;
    total_actions: number;
    closeable_count: number;
    source_path: string | null;
    closeable_action: {
      action_id: string;
      title: string;
      status_raw: string;
      blocks: string;
      owner: string;
    } | null;
    next_action: {
      action_id: string;
      title: string;
      status_raw: string;
      blocks: string;
      owner: string;
    } | null;
  } | null;
  engineeringDeferrals: {
    open_count: number;
    total_deferrals: number;
    first_open: {
      deferral_id: string;
      title: string;
      unlock_criterion: string | null;
    } | null;
  } | null;
  loop3: {
    manual_met_count: number;
    evidence_passed_count: number;
    total_criteria: number;
    env_unlocked: boolean;
    fully_unlocked: boolean;
    first_failing_evidence: {
      criterion: string;
      evidence_summary: string;
    } | null;
  } | null;
  sourceGate: {
    state: string;
    source_count: number;
    blocked_count: number;
    reference_source: string;
    error: string | null;
    first_blocked: {
      source: string;
      failures: string[];
    } | null;
  } | null;
  readActivation: {
    valid_sessions: number;
    total_sessions: number;
    live_provider_sessions: number;
    citation_trace_sessions: number;
    non_library_sessions: number;
    final_verdict: string | null;
    closure_ready: boolean;
    remaining_requirements: Record<string, number>;
    invalid_session_count: number;
  } | null;
}

function nonNegativeFiniteNumber(value: unknown): number | null {
  const parsed =
    typeof value === "number"
      ? value
      : typeof value === "string" && value.trim() !== ""
        ? Number(value)
        : Number.NaN;
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : null;
}

function record(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function nonEmptyString(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

function nullableString(value: unknown): string | null {
  return value == null ? null : nonEmptyString(value);
}

function centsToUsd(value: unknown): string {
  const cents = nonNegativeFiniteNumber(value) ?? 0;
  return `$${(cents / 100).toFixed(2)}`;
}

function fourDecimalUsd(value: string): string {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= 0 ? `$${parsed.toFixed(4)}` : "$0.0000";
}

function decimalUsd(value: string): string {
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed >= 0 ? `$${parsed.toFixed(2)}` : "$0.00";
}

function countLabel(value: unknown): string {
  return Math.floor(nonNegativeFiniteNumber(value) ?? 0).toLocaleString();
}

function safeCount(value: unknown): number {
  return Math.floor(nonNegativeFiniteNumber(value) ?? 0);
}

function safeCounts(value: unknown): Record<string, number> {
  const counts = record(value);
  if (!counts) return {};
  return Object.fromEntries(
    Object.entries(counts).flatMap(([key, value]) => {
      const safeKey = nonEmptyString(key);
      return safeKey ? [[safeKey, safeCount(value)]] : [];
    }),
  );
}

function safeWarnings(value: unknown): string[] {
  return Array.isArray(value)
    ? value.flatMap((warning) => {
        const message = nonEmptyString(warning);
        return message ? [message] : [];
      })
    : [];
}

function safeStringArray(value: unknown): string[] {
  return Array.isArray(value)
    ? value.flatMap((item) => {
        const text = nonEmptyString(item);
        return text ? [text] : [];
      })
    : [];
}

function safePartnerList(value: unknown): string[] {
  const seen = new Set<string>();
  if (!Array.isArray(value)) return [];
  return value.flatMap((item) => {
    const partner = nonEmptyString(item);
    if (!partner || seen.has(partner)) return [];
    seen.add(partner);
    return [partner];
  });
}

function safeStatsResponse(value: unknown): StatsResponse {
  const body = record(value);
  return {
    counts: safeCounts(body?.counts),
    warnings: safeWarnings(body?.warnings),
  };
}

function safeFederationSummary(value: unknown): FederationSummary {
  const body = record(value);
  return {
    allowed_partner_substrates: safePartnerList(
      body?.allowed_partner_substrates,
    ),
    require_opt_in_for_outbound_citations:
      body?.require_opt_in_for_outbound_citations === false ? false : true,
    require_attribution_for_outbound_citations:
      body?.require_attribution_for_outbound_citations === false ? false : true,
  };
}

function safeUsdString(value: unknown): string {
  return String(nonNegativeFiniteNumber(value) ?? 0);
}

function currentPeriod(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
}

function safeBillingSummary(value: unknown): BillingSummary {
  const body = record(value);
  return {
    period: nonEmptyString(body?.period) ?? currentPeriod(),
    free_tokens_consumed: safeCount(body?.free_tokens_consumed),
    free_tokens_remaining: safeCount(body?.free_tokens_remaining),
    total_margin_usd: safeUsdString(body?.total_margin_usd),
    total_billable_usd: safeUsdString(body?.total_billable_usd),
    record_count: safeCount(body?.record_count),
  };
}

function safeInvestigationSummary(value: unknown): InvestigationSummary {
  const body = record(value);
  const rows = Array.isArray(body?.investigations) ? body.investigations : [];
  const summary: InvestigationSummary = {
    total: 0,
    in_progress: 0,
    completed: 0,
    failed: 0,
    total_cost_usd: 0,
  };
  for (const item of rows) {
    const row = record(item);
    if (!nonEmptyString(row?.investigation_id)) continue;
    summary.total += 1;
    const status = nonEmptyString(row?.status) ?? "in_progress";
    if (status === "completed") summary.completed += 1;
    else if (status === "failed") summary.failed += 1;
    else summary.in_progress += 1;
    summary.total_cost_usd += nonNegativeFiniteNumber(row?.cost_usd_total) ?? 0;
  }
  return summary;
}

function safeOutcomeSummary(value: unknown): OutcomeSummary {
  const body = record(value);
  const rows = Array.isArray(body?.outcomes) ? body.outcomes : [];
  const summary: OutcomeSummary = {
    total: 0,
    operator_reviews: 0,
    other_reviews: 0,
    dated_reviews: 0,
  };
  for (const item of rows) {
    const row = record(item);
    if (!nonEmptyString(row?.outcome_id) || !nonEmptyString(row?.synthesis_id)) {
      continue;
    }
    summary.total += 1;
    if (nonEmptyString(row?.observer) === "__operator__") {
      summary.operator_reviews += 1;
    } else {
      summary.other_reviews += 1;
    }
    if (nonEmptyString(row?.observed_at)) {
      summary.dated_reviews += 1;
    }
  }
  return summary;
}

function safeNumberMapTotal(value: unknown): number {
  const body = record(value);
  if (!body) return 0;
  return Object.entries(body).reduce(
    (sum, [key, raw]) =>
      nonEmptyString(key) ? sum + (nonNegativeFiniteNumber(raw) ?? 0) : sum,
    0,
  );
}

function safeTrustSummary(value: unknown): TrustSummary {
  const body = record(value);
  const evidence = record(body?.loop_3_evidence_status);
  const evidenceValues = evidence ? Object.values(evidence) : [];
  return {
    privacy_budget_total: safeNumberMapTotal(
      body?.differential_privacy_epsilon_budgets,
    ),
    deletion_sla_days: safeCount(body?.deletion_sla_days),
    substrate_control_count: safeStringArray(body?.substrate_controls).length,
    compliance_framework_count: safeStringArray(body?.compliance_frameworks).length,
    loop_3_checked_count: evidenceValues.filter((value) => value === true).length,
    loop_3_total_count: evidenceValues.length,
    loop_3_all_evidence_passed: body?.loop_3_all_evidence_passed === true,
  };
}

function safeRate(value: unknown): number {
  return nonNegativeFiniteNumber(value) ?? 0;
}

function safeMarketplaceSummary(value: unknown): MarketplaceSummary {
  const body = record(value);
  const creators = record(body?.creators);
  const publishers = record(body?.publishers);
  const publisherCounts = record(publishers?.status_counts);
  const advertisers = record(body?.advertisers);
  const rawHealth = nonEmptyString(body?.health);
  return {
    health:
      rawHealth === "healthy" || rawHealth === "unhealthy" ? rawHealth : "watch",
    health_signals: safeStringArray(body?.health_signals),
    creators: {
      creator_count: safeCount(creators?.creator_count),
      total_paid_cents: safeCount(creators?.total_paid_cents),
    },
    publishers: {
      claim_rate: safeRate(publisherCounts?.claim_rate),
      total_escrow_accrued_cents: safeCount(
        publishers?.total_escrow_accrued_cents,
      ),
      unclaimed_escrow_cents: safeCount(publishers?.unclaimed_escrow_cents),
    },
    advertisers: {
      advertiser_count_current: safeCount(advertisers?.advertiser_count_current),
      retention_rate: safeRate(advertisers?.retention_rate),
      total_spend_current_cents: safeCount(advertisers?.total_spend_current_cents),
      crosses_self_service_threshold:
        advertisers?.crosses_self_service_threshold === true,
    },
  };
}

function safePublisher(value: unknown): PublisherSummary | null {
  const publisher = record(value);
  const ipHolderId = nonEmptyString(publisher?.ip_holder_id);
  if (!publisher || !ipHolderId) return null;
  const escrow = nonNegativeFiniteNumber(publisher.escrow_balance_usd) ?? 0;
  return {
    ip_holder_id: ipHolderId,
    display_name: nonEmptyString(publisher.display_name) ?? ipHolderId,
    legal_contact_email: nullableString(publisher.legal_contact_email),
    status: nonEmptyString(publisher.status) ?? "pre_onboarded",
    escrow_balance_usd: escrow.toFixed(2),
    notification_sent_at: nullableString(publisher.notification_sent_at),
    claimed_at: nullableString(publisher.claimed_at),
    opted_out_at: nullableString(publisher.opted_out_at),
  };
}

function safePublishers(value: unknown): PublisherSummary[] {
  const body = record(value);
  const publishers = Array.isArray(body?.publishers) ? body.publishers : [];
  return publishers.flatMap((item) => {
    const publisher = safePublisher(item);
    return publisher ? [publisher] : [];
  });
}

function safePendingDeletionCount(value: unknown): number {
  const body = record(value);
  const requests = Array.isArray(body?.requests) ? body.requests : [];
  return requests.filter((item) => {
    const request = record(item);
    return nonEmptyString(request?.status) === "pending";
  }).length;
}

function safePayoutTransfer(value: unknown): PayoutTransfer | null {
  const transfer = record(value);
  if (!transfer) return null;
  return {
    status: nonEmptyString(transfer.status) ?? "unknown",
    amount_usd_cents: safeCount(transfer.amount_usd_cents),
    initiated_at: nullableString(transfer.initiated_at),
  };
}

function safePayoutTransfers(value: unknown): PayoutTransfer[] {
  const body = record(value);
  const transfers = Array.isArray(body?.transfers) ? body.transfers : [];
  return transfers.flatMap((item) => {
    const transfer = safePayoutTransfer(item);
    return transfer ? [transfer] : [];
  });
}

function numberRecord(value: unknown): Record<string, number> {
  const body = record(value);
  if (!body) return {};
  return Object.fromEntries(
    Object.entries(body).map(([key, raw]) => [key, safeCount(raw)]),
  );
}

function safeCoordinationSummary(value: unknown): CoordinationSummary {
  const body = record(value);
  const operatorGate = record(body?.operator_gate_focus);
  const operatorActions = record(body?.operator_actions);
  const engineeringDeferrals = record(body?.engineering_deferrals);
  const loop3 = record(body?.loop3);
  const sourceGate = record(body?.source_gate);
  const readActivation = record(body?.read_activation);
  const gateId = nonEmptyString(operatorGate?.gate_id);
  const safeAction = (value: unknown) => {
    const action = record(value);
    const actionId = nonEmptyString(action?.action_id);
    return action && actionId
      ? {
          action_id: actionId,
          title: nonEmptyString(action.title) ?? actionId,
          status_raw: nonEmptyString(action.status_raw) ?? "",
          blocks: nonEmptyString(action.blocks) ?? "—",
          owner: nonEmptyString(action.owner) ?? "Operator",
        }
      : null;
  };
  return {
    operatorGate:
      operatorGate && gateId
        ? {
            gate_id: gateId,
            title: nonEmptyString(operatorGate.title) ?? gateId,
            status_raw: nonEmptyString(operatorGate.status_raw) ?? "",
            owner: nullableString(operatorGate.owner),
            blocks: nullableString(operatorGate.blocks),
          }
        : null,
    operatorActions: operatorActions
      ? {
          open_count: safeCount(operatorActions.open_count),
          total_actions: safeCount(operatorActions.total_actions),
          closeable_count: safeCount(operatorActions.closeable_count),
          source_path: nullableString(operatorActions.source_path),
          closeable_action: safeAction(operatorActions.closeable_action),
          next_action: safeAction(operatorActions.next_action),
        }
      : null,
    engineeringDeferrals: engineeringDeferrals
      ? {
          open_count: safeCount(engineeringDeferrals.open_count),
          total_deferrals: safeCount(engineeringDeferrals.total_deferrals),
          first_open: (() => {
            const firstOpen = record(engineeringDeferrals.first_open);
            const deferralId = nonEmptyString(firstOpen?.deferral_id);
            return firstOpen && deferralId
              ? {
                  deferral_id: deferralId,
                  title: nonEmptyString(firstOpen.title) ?? deferralId,
                  unlock_criterion: nullableString(firstOpen.unlock_criterion),
                }
              : null;
          })(),
        }
      : null,
    loop3: loop3
      ? {
          manual_met_count: safeCount(loop3.manual_met_count),
          evidence_passed_count: safeCount(loop3.evidence_passed_count),
          total_criteria: safeCount(loop3.total_criteria),
          env_unlocked: loop3.env_unlocked === true,
          fully_unlocked: loop3.fully_unlocked === true,
          first_failing_evidence: (() => {
            const failing = record(loop3.first_failing_evidence);
            const criterion = nonEmptyString(failing?.criterion);
            return failing && criterion
              ? {
                  criterion,
                  evidence_summary:
                    nonEmptyString(failing.evidence_summary) ?? "not checked",
                }
              : null;
          })(),
        }
      : null,
    sourceGate: sourceGate
      ? {
          state: nonEmptyString(sourceGate.state) ?? "missing",
          source_count: safeCount(sourceGate.source_count),
          blocked_count: safeCount(sourceGate.blocked_count),
          reference_source: nonEmptyString(sourceGate.reference_source) ?? "arxiv",
          error: nullableString(sourceGate.error),
          first_blocked: (() => {
            const rows = Array.isArray(sourceGate.rows) ? sourceGate.rows : [];
            for (const item of rows) {
              const row = record(item);
              const source = nonEmptyString(row?.source);
              if (row?.blocked === true && source) {
                return {
                  source,
                  failures: Array.isArray(row.failures)
                    ? row.failures.flatMap((failure) => {
                        const message = nonEmptyString(failure);
                        return message ? [message] : [];
                      })
                    : [],
                };
              }
            }
            return null;
          })(),
        }
      : null,
    readActivation: readActivation
      ? {
          valid_sessions: safeCount(readActivation.valid_sessions),
          total_sessions: safeCount(readActivation.total_sessions),
          live_provider_sessions: safeCount(readActivation.live_provider_sessions),
          citation_trace_sessions: safeCount(readActivation.citation_trace_sessions),
          non_library_sessions: safeCount(readActivation.non_library_sessions),
          final_verdict: nullableString(readActivation.final_verdict),
          closure_ready: readActivation.closure_ready === true,
          remaining_requirements: numberRecord(readActivation.remaining_requirements),
          invalid_session_count: safeCount(readActivation.invalid_session_count),
        }
      : null,
  };
}

/**
 * Operator dashboard (master-spec §9.10 + §13.7).
 *
 * Single-pane view of:
 * - Pre-onboarded IP holder escrow (per §9.10)
 * - Notification status + claim state machine
 * - First-cohort outreach progress (MIT Press / Cambridge / Princeton)
 * - Quality-gate / Phase 8 verdict review
 *
 * Operator-only surface. Bound to the operator user_id via the
 * existing auth path; cross-user access not exposed here.
 */
export default function OperatorDashboard() {
  const [publishers, setPublishers] = useState<PublisherSummary[]>([]);
  const [snapshot, setSnapshot] = useState<CompositeSnapshot>({
    stats: null,
    pendingDeletions: 0,
    recentPayouts: [],
    coordination: null,
    marketplace: null,
    federation: null,
    trust: null,
    billing: null,
    investigations: null,
    outcomes: null,
  });
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [
        publishersResp,
        statsResp,
        deletionsResp,
        payoutsResp,
        coordinationResp,
        marketplaceResp,
        federationResp,
        trustResp,
        billingResp,
        investigationsResp,
        outcomesResp,
      ] = await Promise.all([
        apiFetch("/publishers"),
        apiFetch("/stats").catch(() => null),
        apiFetch("/trust-center/deletion-requests").catch(() => null),
        apiFetch("/payouts/transfers?limit=5").catch(() => null),
        apiFetch("/coordination/roadmap").catch(() => null),
        apiFetch("/marketplace/snapshot").catch(() => null),
        apiFetch("/federation/config").catch(() => null),
        apiFetch("/trust-center").catch(() => null),
        apiFetch(`/billing/summary/__operator__/${currentPeriod()}`).catch(() => null),
        apiFetch("/investigations?limit=200").catch(() => null),
        apiFetch("/outcomes?limit=200").catch(() => null),
      ]);

      if (!publishersResp.ok) {
        throw new Error(`GET /publishers failed: HTTP ${publishersResp.status}`);
      }
      setPublishers(safePublishers(await publishersResp.json()));

      let stats: StatsResponse | null = null;
      if (statsResp?.ok) stats = safeStatsResponse(await statsResp.json());

      let pendingDeletions = 0;
      if (deletionsResp?.ok) {
        pendingDeletions = safePendingDeletionCount(await deletionsResp.json());
      }

      let recentPayouts: PayoutTransfer[] = [];
      if (payoutsResp?.ok) {
        recentPayouts = safePayoutTransfers(await payoutsResp.json());
      }

      let coordination: CoordinationSummary | null = null;
      if (coordinationResp?.ok) {
        coordination = safeCoordinationSummary(await coordinationResp.json());
      }

      let marketplace: MarketplaceSummary | null = null;
      if (marketplaceResp?.ok) {
        marketplace = safeMarketplaceSummary(await marketplaceResp.json());
      }

      let federation: FederationSummary | null = null;
      if (federationResp?.ok) {
        federation = safeFederationSummary(await federationResp.json());
      }

      let trust: TrustSummary | null = null;
      if (trustResp?.ok) {
        trust = safeTrustSummary(await trustResp.json());
      }

      let billing: BillingSummary | null = null;
      if (billingResp?.ok) {
        billing = safeBillingSummary(await billingResp.json());
      }

      let investigations: InvestigationSummary | null = null;
      if (investigationsResp?.ok) {
        investigations = safeInvestigationSummary(await investigationsResp.json());
      }

      let outcomes: OutcomeSummary | null = null;
      if (outcomesResp?.ok) {
        outcomes = safeOutcomeSummary(await outcomesResp.json());
      }

      setSnapshot({
        stats,
        pendingDeletions,
        recentPayouts,
        coordination,
        marketplace,
        federation,
        trust,
        billing,
        investigations,
        outcomes,
      });
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  const handleNotify = async (id: string) => {
    try {
      const resp = await apiFetch(
        `/publishers/${encodeURIComponent(id)}/notify`,
        { method: "POST", headers: { "Content-Type": "application/json" } },
      );
      if (!resp.ok) {
        throw new Error(`POST notify failed: HTTP ${resp.status}`);
      }
      await reload();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const byStatus = {
    pre_onboarded: publishers.filter((p) => p.status === "pre_onboarded"),
    invited: publishers.filter((p) => p.status === "invited"),
    claimed: publishers.filter((p) => p.status === "claimed"),
    opted_out: publishers.filter((p) => p.status === "opted_out"),
  };

  return (
    <div className="flex flex-col h-screen">
      <main className="flex-1 overflow-y-auto bg-ice-0 dark:bg-charcoal-2">
        <div className="max-w-5xl mx-auto px-8 py-10 space-y-8">
          <header className="space-y-2">
            <h1 className="text-2xl font-serif text-ink dark:text-bright">
              Operator dashboard
            </h1>
            <p className="text-sm text-ink-soft dark:text-starlight leading-relaxed">
              Composite operator surface — substrate snapshot,
              pre-onboarded IP holder escrow review, recent payouts,
              pending deletion requests. Per master-spec §9.10:
              'lawyer involved before first notification email
              sends.' The Notify action records that the operator has
              sent the canonical notification email externally;
              this dashboard does NOT send email itself.
            </p>
          </header>

          {loading && (
            <p className="text-sm text-shadow-1 dark:text-moonlight">Loading publishers…</p>
          )}
          {error && (
            <p className="text-sm text-emperor">{error}</p>
          )}

          <CompositeSnapshotSection snapshot={snapshot} />

          <PublisherSection
            title="Pre-onboarded (no notification sent)"
            description={`§9.10 first-cohort targets are MIT Press, Cambridge University Press, Princeton University Press. Big Five last.`}
            publishers={byStatus.pre_onboarded}
            actionLabel="Mark notified"
            onAction={handleNotify}
          />

          <PublisherSection
            title="Invited (notification email sent)"
            description="Escrow accrues; payouts gate strictly on claim. No money has moved."
            publishers={byStatus.invited}
            actionLabel={null}
            onAction={null}
          />

          <PublisherSection
            title="Claimed (payouts unlocked)"
            description="Publisher opted in via documented process. Stripe Connect can route the accrued escrow."
            publishers={byStatus.claimed}
            actionLabel={null}
            onAction={null}
          />

          <PublisherSection
            title="Opted out (content removal scheduled)"
            description="30-day SLA for removal per §9.10 implementation requirement 4."
            publishers={byStatus.opted_out}
            actionLabel={null}
            onAction={null}
          />
        </div>
      </main>
    </div>
  );
}

function CompositeSnapshotSection({ snapshot }: { snapshot: CompositeSnapshot }) {
  const counts = snapshot.stats?.counts ?? {};
  const headlineKeys: [string, string][] = [
    ["investigations", "Investigations"],
    ["notebooks", "Notebooks"],
    ["outcomes", "Outcomes"],
    ["skill_rules", "Skill rules"],
    ["payout_transfers", "Payouts"],
    ["ip_holders", "IP holders"],
  ];
  return (
    <section className="border border-rule dark:border-charcoal-1 rounded-md p-5 space-y-4">
      <div className="flex items-baseline justify-between gap-3">
        <h2 className="text-base font-serif text-ink dark:text-bright">
          Substrate snapshot
        </h2>
        <Link
          to="/stats"
          className="text-xs font-mono text-shadow-1 dark:text-moonlight hover:text-ink dark:text-bright"
        >
          full stats →
        </Link>
      </div>
      <div className="grid grid-cols-3 sm:grid-cols-6 gap-3">
        {headlineKeys.map(([k, label]) => (
          <div
            key={k}
            className="border border-rule dark:border-charcoal-1 rounded-md px-2 py-2 text-center"
          >
            <p className="text-xl font-serif text-ink dark:text-bright">
              {countLabel(counts[k])}
            </p>
            <p className="text-[10px] font-mono text-shadow-1 dark:text-moonlight uppercase">
              {label}
            </p>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="border border-rule dark:border-charcoal-1 rounded-md px-3 py-2">
          <p className="text-[10px] font-mono uppercase text-shadow-1 dark:text-moonlight">
            Pending deletion requests
          </p>
          <p className="text-lg font-serif text-ink dark:text-bright">
            {snapshot.pendingDeletions}
            {snapshot.pendingDeletions > 0 && (
              <Link
                to="/privacy"
                className="ml-2 text-xs font-mono text-shadow-1 dark:text-moonlight hover:underline"
              >
                review →
              </Link>
            )}
          </p>
        </div>
        <div className="border border-rule dark:border-charcoal-1 rounded-md px-3 py-2">
          <p className="text-[10px] font-mono uppercase text-shadow-1 dark:text-moonlight">
            Recent payouts
          </p>
          {snapshot.recentPayouts.length === 0 ? (
            <p className="text-sm italic text-shadow-1 dark:text-moonlight">No transfers yet.</p>
          ) : (
            <ul className="text-xs font-mono text-ink dark:text-bright space-y-0.5">
              {snapshot.recentPayouts.slice(0, 3).map((p, i) => (
                <li
                  key={i}
                  className="flex justify-between gap-2 truncate"
                >
                  <span>{p.status.replace(/_/g, " ")}</span>
                  <span>{centsToUsd(p.amount_usd_cents)}</span>
                </li>
              ))}
            </ul>
          )}
          <Link
            to="/payouts"
            className="text-[11px] font-mono text-shadow-1 dark:text-moonlight hover:underline"
          >
            full audit →
          </Link>
        </div>
      </div>
      <CoordinationTile coordination={snapshot.coordination} />
      <InvestigationsTile investigations={snapshot.investigations} />
      <OutcomesTile outcomes={snapshot.outcomes} />
      <BillingTile billing={snapshot.billing} />
      <TrustTile trust={snapshot.trust} />
      <MarketplaceTile marketplace={snapshot.marketplace} />
      <FederationTile federation={snapshot.federation} />
    </section>
  );
}

function OutcomesTile({ outcomes }: { outcomes: OutcomeSummary | null }) {
  if (!outcomes) {
    return (
      <div className="border border-rule dark:border-charcoal-1 rounded-md px-3 py-3">
        <div className="flex items-baseline justify-between gap-3">
          <h3 className="text-sm font-serif text-ink dark:text-bright">
            Outcome reviews
          </h3>
          <Link
            to="/outcomes"
            className="text-[11px] font-mono text-shadow-1 dark:text-moonlight hover:underline"
          >
            open →
          </Link>
        </div>
        <p className="mt-2 text-xs italic text-shadow-1 dark:text-moonlight">
          Outcome review history unavailable.
        </p>
      </div>
    );
  }
  return (
    <div className="border border-rule dark:border-charcoal-1 rounded-md px-3 py-3 space-y-2">
      <div className="flex items-baseline justify-between gap-3">
        <h3 className="text-sm font-serif text-ink dark:text-bright">
          Outcome reviews
        </h3>
        <Link
          to="/outcomes"
          className="text-[11px] font-mono text-shadow-1 dark:text-moonlight hover:underline"
        >
          open →
        </Link>
      </div>
      <p className="text-xs font-mono text-ink dark:text-bright">
        {outcomes.total} reviews · {outcomes.operator_reviews} operator ·{" "}
        {outcomes.other_reviews} collaborator
      </p>
      <p className="text-xs text-ink-soft dark:text-starlight">
        {outcomes.dated_reviews}/{outcomes.total} reviews have timestamps.
      </p>
    </div>
  );
}

function InvestigationsTile({
  investigations,
}: {
  investigations: InvestigationSummary | null;
}) {
  if (!investigations) {
    return (
      <div className="border border-rule dark:border-charcoal-1 rounded-md px-3 py-3">
        <div className="flex items-baseline justify-between gap-3">
          <h3 className="text-sm font-serif text-ink dark:text-bright">
            Research workload
          </h3>
          <Link
            to="/investigations"
            className="text-[11px] font-mono text-shadow-1 dark:text-moonlight hover:underline"
          >
            open →
          </Link>
        </div>
        <p className="mt-2 text-xs italic text-shadow-1 dark:text-moonlight">
          Investigation workload unavailable.
        </p>
      </div>
    );
  }
  return (
    <div className="border border-rule dark:border-charcoal-1 rounded-md px-3 py-3 space-y-2">
      <div className="flex items-baseline justify-between gap-3">
        <h3 className="text-sm font-serif text-ink dark:text-bright">
          Research workload
        </h3>
        <Link
          to="/investigations"
          className="text-[11px] font-mono text-shadow-1 dark:text-moonlight hover:underline"
        >
          open →
        </Link>
      </div>
      <p className="text-xs font-mono text-ink dark:text-bright">
        {investigations.total} visible · {investigations.in_progress} in progress ·{" "}
        {investigations.completed} completed · {investigations.failed} failed
      </p>
      <p className="text-xs text-ink-soft dark:text-starlight">
        Visible research cost ${investigations.total_cost_usd.toFixed(4)}.
      </p>
    </div>
  );
}

function BillingTile({ billing }: { billing: BillingSummary | null }) {
  if (!billing) {
    return (
      <div className="border border-rule dark:border-charcoal-1 rounded-md px-3 py-3">
        <div className="flex items-baseline justify-between gap-3">
          <h3 className="text-sm font-serif text-ink dark:text-bright">
            Billing usage
          </h3>
          <Link
            to="/billing"
            className="text-[11px] font-mono text-shadow-1 dark:text-moonlight hover:underline"
          >
            open →
          </Link>
        </div>
        <p className="mt-2 text-xs italic text-shadow-1 dark:text-moonlight">
          Billing summary unavailable.
        </p>
      </div>
    );
  }
  return (
    <div className="border border-rule dark:border-charcoal-1 rounded-md px-3 py-3 space-y-2">
      <div className="flex items-baseline justify-between gap-3">
        <h3 className="text-sm font-serif text-ink dark:text-bright">
          Billing usage
        </h3>
        <Link
          to="/billing"
          className="text-[11px] font-mono text-shadow-1 dark:text-moonlight hover:underline"
        >
          open →
        </Link>
      </div>
      <p className="text-xs font-mono text-ink dark:text-bright">
        {billing.period} · billable {fourDecimalUsd(billing.total_billable_usd)} · margin{" "}
        {fourDecimalUsd(billing.total_margin_usd)}
      </p>
      <p className="text-xs text-ink-soft dark:text-starlight">
        Free tier {billing.free_tokens_consumed.toLocaleString()} consumed ·{" "}
        {billing.free_tokens_remaining.toLocaleString()} remaining.
      </p>
      <p className="text-xs text-ink-soft dark:text-starlight">
        {billing.record_count.toLocaleString()} usage records aggregated.
      </p>
    </div>
  );
}

function TrustTile({ trust }: { trust: TrustSummary | null }) {
  if (!trust) {
    return (
      <div className="border border-rule dark:border-charcoal-1 rounded-md px-3 py-3">
        <div className="flex items-baseline justify-between gap-3">
          <h3 className="text-sm font-serif text-ink dark:text-bright">
            Privacy controls
          </h3>
          <Link
            to="/privacy"
            className="text-[11px] font-mono text-shadow-1 dark:text-moonlight hover:underline"
          >
            open →
          </Link>
        </div>
        <p className="mt-2 text-xs italic text-shadow-1 dark:text-moonlight">
          Trust publication unavailable.
        </p>
      </div>
    );
  }
  return (
    <div className="border border-rule dark:border-charcoal-1 rounded-md px-3 py-3 space-y-2">
      <div className="flex items-baseline justify-between gap-3">
        <h3 className="text-sm font-serif text-ink dark:text-bright">
          Privacy controls
        </h3>
        <Link
          to="/privacy"
          className="text-[11px] font-mono text-shadow-1 dark:text-moonlight hover:underline"
        >
          open →
        </Link>
      </div>
      <p className="text-xs font-mono text-ink dark:text-bright">
        Privacy budget {trust.privacy_budget_total.toFixed(2)}/10.00 · deletion SLA{" "}
        {trust.deletion_sla_days} days
      </p>
      <p className="text-xs text-ink-soft dark:text-starlight">
        {trust.substrate_control_count} controls · {trust.compliance_framework_count} frameworks.
      </p>
      <p className="text-xs text-ink-soft dark:text-starlight">
        Training evidence {trust.loop_3_checked_count}/{trust.loop_3_total_count} ·{" "}
        {trust.loop_3_all_evidence_passed ? "all evidence passed" : "evidence incomplete"}.
      </p>
    </div>
  );
}

function FederationTile({
  federation,
}: {
  federation: FederationSummary | null;
}) {
  const openLink = (
    <Link
      to="/federation"
      className="text-[11px] font-mono text-shadow-1 dark:text-moonlight hover:underline"
    >
      open →
    </Link>
  );
  if (!federation) {
    return (
      <div className="border border-rule dark:border-charcoal-1 rounded-md px-3 py-3">
        <div className="flex items-baseline justify-between gap-3">
          <h3 className="text-sm font-serif text-ink dark:text-bright">
            Federation status
          </h3>
          {openLink}
        </div>
        <p className="mt-2 text-xs italic text-shadow-1 dark:text-moonlight">
          Federation config unavailable.
        </p>
      </div>
    );
  }
  const partnerCount = federation.allowed_partner_substrates.length;
  const strictDefault =
    partnerCount === 0 &&
    federation.require_opt_in_for_outbound_citations &&
    federation.require_attribution_for_outbound_citations;
  const firstPartners = federation.allowed_partner_substrates.slice(0, 3).join(", ");
  return (
    <div className="border border-rule dark:border-charcoal-1 rounded-md px-3 py-3 space-y-2">
      <div className="flex items-baseline justify-between gap-3">
        <h3 className="text-sm font-serif text-ink dark:text-bright">
          Federation status
        </h3>
        {openLink}
      </div>
      <p className="text-xs font-mono text-ink dark:text-bright">
        {strictDefault ? "STRICT DEFAULT" : "CONFIGURED"} · {partnerCount} partner
        {partnerCount === 1 ? "" : "s"}
      </p>
      <p className="text-xs text-ink-soft dark:text-starlight">
        Outbound citations require opt-in:{" "}
        {federation.require_opt_in_for_outbound_citations ? "yes" : "no"} ·
        attribution:{" "}
        {federation.require_attribution_for_outbound_citations ? "yes" : "no"}.
      </p>
      <p className="text-xs text-ink-soft dark:text-starlight">
        {partnerCount > 0
          ? `Partners: ${firstPartners}${partnerCount > 3 ? "…" : ""}.`
          : "No partner substrates are currently allowed."}
      </p>
    </div>
  );
}

function MarketplaceTile({
  marketplace,
}: {
  marketplace: MarketplaceSummary | null;
}) {
  if (!marketplace) {
    return (
      <div className="border border-rule dark:border-charcoal-1 rounded-md px-3 py-3">
        <div className="flex items-baseline justify-between gap-3">
          <h3 className="text-sm font-serif text-ink dark:text-bright">
            Marketplace health
          </h3>
          <Link
            to="/marketplace"
            className="text-[11px] font-mono text-shadow-1 dark:text-moonlight hover:underline"
          >
            open →
          </Link>
        </div>
        <p className="mt-2 text-xs italic text-shadow-1 dark:text-moonlight">
          Marketplace snapshot unavailable.
        </p>
      </div>
    );
  }
  const firstSignal = marketplace.health_signals[0] ?? "no health signals reported";
  return (
    <div className="border border-rule dark:border-charcoal-1 rounded-md px-3 py-3 space-y-2">
      <div className="flex items-baseline justify-between gap-3">
        <h3 className="text-sm font-serif text-ink dark:text-bright">
          Marketplace health
        </h3>
        <Link
          to="/marketplace"
          className="text-[11px] font-mono text-shadow-1 dark:text-moonlight hover:underline"
        >
          open →
        </Link>
      </div>
      <p className="text-xs font-mono text-ink dark:text-bright">
        {marketplace.health.toUpperCase()} · {marketplace.creators.creator_count} creators ·{" "}
        {marketplace.advertisers.advertiser_count_current} advertisers
      </p>
      <p className="text-xs text-ink-soft dark:text-starlight">
        Paid {centsToUsd(marketplace.creators.total_paid_cents)} · escrow{" "}
        {centsToUsd(marketplace.publishers.total_escrow_accrued_cents)} · ad spend{" "}
        {centsToUsd(marketplace.advertisers.total_spend_current_cents)}.
      </p>
      <p className="text-xs text-ink-soft dark:text-starlight">
        Publisher claims {(marketplace.publishers.claim_rate * 100).toFixed(1)}% ·
        advertiser retention {(marketplace.advertisers.retention_rate * 100).toFixed(1)}% ·
        self-service {marketplace.advertisers.crosses_self_service_threshold ? "crossed" : "not crossed"}.
      </p>
      <p className="text-xs text-ink-soft dark:text-starlight">
        Signal: {firstSignal}.
      </p>
    </div>
  );
}

function CoordinationTile({
  coordination,
}: {
  coordination: CoordinationSummary | null;
}) {
  const activation = coordination?.readActivation ?? null;
  const operatorActions = coordination?.operatorActions ?? null;
  const engineeringDeferrals = coordination?.engineeringDeferrals ?? null;
  const loop3 = coordination?.loop3 ?? null;
  const sourceGate = coordination?.sourceGate ?? null;
  const actionFocus =
    operatorActions?.closeable_action ?? operatorActions?.next_action ?? null;
  const remaining = activation?.remaining_requirements ?? {};
  const remainingText = [
    ["valid", remaining.valid_sessions],
    ["live-provider", remaining.live_provider_sessions],
    ["citation-traced", remaining.citation_trace_sessions],
    ["non-library", remaining.non_library_sessions],
  ]
    .filter(([, value]) => Number(value) > 0)
    .map(([label, value]) => `${value} ${label}`)
    .join(", ");
  return (
    <div className="border border-rule dark:border-charcoal-1 rounded-md px-3 py-3 space-y-2">
      <div className="flex items-baseline justify-between gap-3">
        <h3 className="text-sm font-serif text-ink dark:text-bright">
          Coordination focus
        </h3>
        <Link
          to="/coordination"
          className="text-[11px] font-mono text-shadow-1 dark:text-moonlight hover:underline"
        >
          open →
        </Link>
      </div>
      {coordination?.operatorGate ? (
        <div className="space-y-0.5">
          <p className="text-xs font-mono text-ink dark:text-bright">
            {coordination.operatorGate.gate_id} · {coordination.operatorGate.title}
          </p>
          <p className="text-xs text-ink-soft dark:text-starlight">
            {coordination.operatorGate.status_raw || "open"}
            {coordination.operatorGate.owner ? ` · ${coordination.operatorGate.owner}` : ""}
          </p>
          {coordination.operatorGate.blocks && (
            <p className="text-xs text-ink-soft dark:text-starlight">
              Blocks: {coordination.operatorGate.blocks}
            </p>
          )}
        </div>
      ) : (
        <p className="text-xs italic text-shadow-1 dark:text-moonlight">
          No open operator gate focus reported.
        </p>
      )}
      {activation ? (
        <div className="space-y-0.5 border-t border-rule dark:border-charcoal-1 pt-2">
          <p className="text-xs font-mono text-ink dark:text-bright">
            Read dogfood {activation.valid_sessions}/{activation.total_sessions} valid ·{" "}
            {activation.live_provider_sessions} live-provider ·{" "}
            {activation.citation_trace_sessions} citation-traced
          </p>
          <p className="text-xs text-ink-soft dark:text-starlight">
            {activation.closure_ready
              ? `Mechanically ready · verdict=${activation.final_verdict || "missing"}`
              : remainingText
                ? `Remaining: ${remainingText}.`
                : "No closure evidence ready yet."}
            {activation.invalid_session_count > 0
              ? ` ${activation.invalid_session_count} invalid session${activation.invalid_session_count === 1 ? "" : "s"} need repair.`
              : ""}
          </p>
          <Link
            to="/coordination/cost-consent"
            className="text-[11px] font-mono text-shadow-1 dark:text-moonlight hover:underline"
          >
            cost + consent →
          </Link>
        </div>
      ) : (
        <p className="text-xs italic text-shadow-1 dark:text-moonlight">
          Activation dogfood status unavailable.
        </p>
      )}
      {operatorActions ? (
        <div className="space-y-0.5 border-t border-rule dark:border-charcoal-1 pt-2">
          <p className="text-xs font-mono text-ink dark:text-bright">
            Operator actions {operatorActions.open_count}/{operatorActions.total_actions} not closed
            {operatorActions.closeable_count > 0
              ? ` · ${operatorActions.closeable_count} awaiting operator test`
              : ""}
          </p>
          {actionFocus ? (
            <p className="text-xs text-ink-soft dark:text-starlight">
              {operatorActions.closeable_action ? "Closeable now" : "Next"}:{" "}
              {actionFocus.action_id} · {actionFocus.title}. Blocks:{" "}
              {actionFocus.blocks}.
            </p>
          ) : (
            <p className="text-xs italic text-shadow-1 dark:text-moonlight">
              No operator actions reported.
            </p>
          )}
        </div>
      ) : (
        <p className="text-xs italic text-shadow-1 dark:text-moonlight">
          Operator action status unavailable.
        </p>
      )}
      {engineeringDeferrals ? (
        <div className="space-y-0.5 border-t border-rule dark:border-charcoal-1 pt-2">
          <p className="text-xs font-mono text-ink dark:text-bright">
            Deferrals {engineeringDeferrals.open_count}/{engineeringDeferrals.total_deferrals} not closed
          </p>
          {engineeringDeferrals.first_open ? (
            <p className="text-xs text-ink-soft dark:text-starlight">
              Do not pre-build {engineeringDeferrals.first_open.deferral_id} ·{" "}
              {engineeringDeferrals.first_open.title}. Unlock:{" "}
              {engineeringDeferrals.first_open.unlock_criterion || "not specified"}.
            </p>
          ) : (
            <p className="text-xs italic text-shadow-1 dark:text-moonlight">
              No open deferrals reported.
            </p>
          )}
        </div>
      ) : (
        <p className="text-xs italic text-shadow-1 dark:text-moonlight">
          Deferral status unavailable.
        </p>
      )}
      {loop3 ? (
        <div className="space-y-0.5 border-t border-rule dark:border-charcoal-1 pt-2">
          <p className="text-xs font-mono text-ink dark:text-bright">
            Loop 3 manual {loop3.manual_met_count}/{loop3.total_criteria} · evidence{" "}
            {loop3.evidence_passed_count}/{loop3.total_criteria} · env=
            {loop3.env_unlocked ? "unlocked" : "locked"}
          </p>
          {loop3.first_failing_evidence ? (
            <p className="text-xs text-ink-soft dark:text-starlight">
              First failing evidence: {loop3.first_failing_evidence.criterion} ·{" "}
              {loop3.first_failing_evidence.evidence_summary}.
            </p>
          ) : (
            <p className="text-xs text-ink-soft dark:text-starlight">
              Fully unlocked: {loop3.fully_unlocked ? "yes" : "no"}.
            </p>
          )}
        </div>
      ) : (
        <p className="text-xs italic text-shadow-1 dark:text-moonlight">
          Loop 3 status unavailable.
        </p>
      )}
      {sourceGate ? (
        <div className="space-y-0.5 border-t border-rule dark:border-charcoal-1 pt-2">
          <p className="text-xs font-mono text-ink dark:text-bright">
            Source gate {sourceGate.state} · {sourceGate.blocked_count}/{sourceGate.source_count} blocked
          </p>
          <p className="text-xs text-ink-soft dark:text-starlight">
            {sourceGate.first_blocked
              ? `${sourceGate.first_blocked.source}: ${sourceGate.first_blocked.failures[0] || "blocked"}`
              : sourceGate.error || `Reference source: ${sourceGate.reference_source}.`}
          </p>
        </div>
      ) : (
        <p className="text-xs italic text-shadow-1 dark:text-moonlight">
          Source gate status unavailable.
        </p>
      )}
    </div>
  );
}

function PublisherSection({
  title,
  description,
  publishers,
  actionLabel,
  onAction,
}: {
  title: string;
  description: string;
  publishers: PublisherSummary[];
  actionLabel: string | null;
  onAction: ((id: string) => void) | null;
}) {
  return (
    <section className="border border-rule dark:border-charcoal-1 rounded-md p-5 space-y-3">
      <div className="space-y-1">
        <h2 className="text-base font-serif text-ink dark:text-bright">{title}</h2>
        <p className="text-xs text-ink-soft dark:text-starlight">{description}</p>
      </div>
      {publishers.length === 0 ? (
        <p className="text-xs italic text-shadow-1 dark:text-moonlight">No publishers in this bucket.</p>
      ) : (
        <ul className="divide-y divide-rule dark:divide-charcoal-1">
          {publishers.map((p) => (
            <li key={p.ip_holder_id} className="py-2 flex items-center justify-between gap-4">
              <div className="min-w-0 flex-1">
                <p className="text-sm font-serif text-ink dark:text-bright truncate">
                  {p.display_name}
                </p>
                <p className="text-xs font-mono text-shadow-1 dark:text-moonlight truncate">
                  {p.ip_holder_id} · escrow {decimalUsd(p.escrow_balance_usd)}
                  {p.legal_contact_email && (
                    <span> · {p.legal_contact_email}</span>
                  )}
                </p>
              </div>
              {actionLabel && onAction && (
                <button
                  type="button"
                  onClick={() => onAction(p.ip_holder_id)}
                  className="px-2.5 py-1 rounded-md bg-ink text-white text-xs font-medium hover:bg-shadow-2 transition-colors shrink-0"
                >
                  {actionLabel}
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
