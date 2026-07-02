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

function safeStatsResponse(value: unknown): StatsResponse {
  const body = record(value);
  return {
    counts: safeCounts(body?.counts),
    warnings: safeWarnings(body?.warnings),
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
      ] = await Promise.all([
        apiFetch("/publishers"),
        apiFetch("/stats").catch(() => null),
        apiFetch("/trust-center/deletion-requests").catch(() => null),
        apiFetch("/payouts/transfers?limit=5").catch(() => null),
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

      setSnapshot({ stats, pendingDeletions, recentPayouts });
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
    </section>
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
