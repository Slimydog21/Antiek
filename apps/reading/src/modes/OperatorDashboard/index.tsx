import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { ErrorBanner } from "../../components/lemon/ErrorBanner";
import LemonButton from "../../components/lemon/LemonButton";
import { ApiError, apiFetch } from "../../lib/api";
import { describeFailure, type DescribedFailure } from "../../shared/failure";

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

interface DeletionRequest {
  request_id: string;
  status: string;
  requested_at: string;
}

interface PayoutTransfer {
  status: string;
  amount_usd_cents: number;
  initiated_at: string | null;
}

/**
 * One read's state. A failed read is never shown as a zero or an empty list
 * (F-09: the three snapshot reads were `.catch(() => null)` and rendered as
 * 0 counts, "0" pending deletion requests and "No transfers yet.").
 */
type Read<T> =
  | { state: "loading" }
  | { state: "ok"; data: T }
  | { state: "failed"; failure: DescribedFailure };

const LOADING = { state: "loading" } as const;

interface CompositeSnapshot {
  stats: Read<StatsResponse>;
  pendingDeletions: Read<number>;
  recentPayouts: Read<PayoutTransfer[]>;
}

/** GET a JSON body; each read settles on its own so one failure leaves the
 *  others standing. `what` is the operator's intent, used for the title. */
async function read<T>(path: string, what: string): Promise<Read<T>> {
  try {
    const resp = await apiFetch(path);
    if (!resp.ok) {
      throw new ApiError(`GET ${path} failed: HTTP ${resp.status}`, resp.status, await resp.text());
    }
    return { state: "ok", data: (await resp.json()) as T };
  } catch (e: unknown) {
    console.warn(`[OperatorDashboard] ${what} failed`, e);
    return { state: "failed", failure: describeFailure(e, { what }) };
  }
}

function mapRead<T, U>(r: Read<T>, f: (data: T) => U): Read<U> {
  return r.state === "ok" ? { state: "ok", data: f(r.data) } : r;
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
  const [publishersRead, setPublishersRead] = useState<Read<PublisherSummary[]>>(LOADING);
  const [snapshot, setSnapshot] = useState<CompositeSnapshot>({
    stats: LOADING,
    pendingDeletions: LOADING,
    recentPayouts: LOADING,
  });
  const [notifyFailure, setNotifyFailure] = useState<{
    failure: DescribedFailure;
    retry: () => void;
  } | null>(null);

  const reload = useCallback(async () => {
    setPublishersRead(LOADING);
    setSnapshot({ stats: LOADING, pendingDeletions: LOADING, recentPayouts: LOADING });
    const [pubData, stats, drData, pData] = await Promise.all([
      read<{ publishers?: PublisherSummary[] }>("/publishers", "load publishers"),
      read<StatsResponse>("/stats", "load substrate counts"),
      read<{ requests?: DeletionRequest[] }>(
        "/trust-center/deletion-requests",
        "load deletion requests",
      ),
      read<{ transfers?: PayoutTransfer[] }>("/payouts/transfers?limit=5", "load transfers"),
    ]);
    setPublishersRead(mapRead(pubData, (d) => d.publishers ?? []));
    setSnapshot({
      stats,
      pendingDeletions: mapRead(
        drData,
        (d) => (d.requests ?? []).filter((r) => r.status === "pending").length,
      ),
      recentPayouts: mapRead(pData, (d) => d.transfers ?? []),
    });
  }, []);

  const loading = publishersRead.state === "loading";
  const publishers = publishersRead.state === "ok" ? publishersRead.data : [];

  useEffect(() => {
    void reload();
  }, [reload]);

  const handleNotify = async (id: string) => {
    setNotifyFailure(null);
    try {
      const resp = await apiFetch(
        `/publishers/${encodeURIComponent(id)}/notify`,
        { method: "POST", headers: { "Content-Type": "application/json" } },
      );
      if (!resp.ok) {
        throw new ApiError(`POST notify failed: HTTP ${resp.status}`, resp.status, await resp.text());
      }
      await reload();
    } catch (e: unknown) {
      console.warn("[OperatorDashboard] notify failed", e);
      setNotifyFailure({
        failure: describeFailure(e, { what: "mark that publisher notified" }),
        retry: () => void handleNotify(id),
      });
    }
  };

  const byStatus = {
    pre_onboarded: publishers.filter((p) => p.status === "pre_onboarded"),
    invited: publishers.filter((p) => p.status === "invited"),
    claimed: publishers.filter((p) => p.status === "claimed"),
    opted_out: publishers.filter((p) => p.status === "opted_out"),
  };

  return (
    <div className="flex flex-col h-full">
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
          {publishersRead.state === "failed" && (
            <FailureNotice failure={publishersRead.failure} onRetry={() => void reload()} />
          )}
          {notifyFailure && (
            <FailureNotice failure={notifyFailure.failure} onRetry={notifyFailure.retry} />
          )}

          <CompositeSnapshotSection snapshot={snapshot} onRetry={() => void reload()} />

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

function FailureNotice({
  failure,
  onRetry,
}: {
  failure: DescribedFailure;
  onRetry: () => void;
}) {
  return (
    <ErrorBanner className="space-y-2">
      <p className="font-medium">{failure.title}</p>
      <p>{failure.detail}</p>
      {failure.retryable && (
        <LemonButton variant="secondary" size="sm" type="button" onClick={onRetry}>
          Try again
        </LemonButton>
      )}
    </ErrorBanner>
  );
}

/** "…" while loading, "—" when the read failed or the key is absent. */
function unknownMark(r: Read<unknown>): string {
  return r.state === "loading" ? "…" : "—";
}

function CompositeSnapshotSection({
  snapshot,
  onRetry,
}: {
  snapshot: CompositeSnapshot;
  onRetry: () => void;
}) {
  const { stats, pendingDeletions, recentPayouts } = snapshot;
  // A key /stats did not report is unknown too, not zero.
  const countFor = (k: string): string => {
    const v = stats.state === "ok" ? stats.data.counts?.[k] : undefined;
    return typeof v === "number" ? v.toLocaleString() : unknownMark(stats);
  };
  const failed = [stats, pendingDeletions, recentPayouts].filter(
    (r): r is { state: "failed"; failure: DescribedFailure } => r.state === "failed",
  );
  const canRetry = failed.some((r) => r.failure.retryable);
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
              {countFor(k)}
            </p>
            <p className="text-xxs font-mono text-shadow-1 dark:text-moonlight uppercase">
              {label}
            </p>
          </div>
        ))}
      </div>
      {stats.state === "failed" && (
        <p className="text-sm text-emperor">{stats.failure.title}</p>
      )}

      <div className="grid grid-cols-2 gap-3">
        <div className="border border-rule dark:border-charcoal-1 rounded-md px-3 py-2">
          <p className="text-xxs font-mono uppercase text-shadow-1 dark:text-moonlight">
            Pending deletion requests
          </p>
          <p className="text-lg font-serif text-ink dark:text-bright">
            {pendingDeletions.state === "ok"
              ? pendingDeletions.data
              : unknownMark(pendingDeletions)}
            {/* The review link stays when the count is unknown: a pending
                request may exist and the operator must be able to check. */}
            {(pendingDeletions.state !== "ok" || pendingDeletions.data > 0) && (
              <Link
                to="/privacy"
                className="ml-2 text-xs font-mono text-shadow-1 dark:text-moonlight hover:underline"
              >
                review →
              </Link>
            )}
          </p>
          {pendingDeletions.state === "failed" && (
            <p className="text-sm text-emperor">{pendingDeletions.failure.title}</p>
          )}
        </div>
        <div className="border border-rule dark:border-charcoal-1 rounded-md px-3 py-2">
          <p className="text-xxs font-mono uppercase text-shadow-1 dark:text-moonlight">
            Recent payouts
          </p>
          {recentPayouts.state === "loading" ? (
            <p className="text-sm italic text-shadow-1 dark:text-moonlight">…</p>
          ) : recentPayouts.state === "failed" ? (
            <p className="text-sm text-emperor">{recentPayouts.failure.title}</p>
          ) : recentPayouts.data.length === 0 ? (
            <p className="text-sm italic text-shadow-1 dark:text-moonlight">No transfers yet.</p>
          ) : (
            <ul className="text-xs font-mono text-ink dark:text-bright space-y-0.5">
              {recentPayouts.data.slice(0, 3).map((p, i) => (
                <li
                  key={i}
                  className="flex justify-between gap-2 truncate"
                >
                  <span>{p.status.replace(/_/g, " ")}</span>
                  <span>${(p.amount_usd_cents / 100).toFixed(2)}</span>
                </li>
              ))}
            </ul>
          )}
          <Link
            to="/payouts"
            className="text-xs font-mono text-shadow-1 dark:text-moonlight hover:underline"
          >
            full audit →
          </Link>
        </div>
      </div>
      {failed.length > 0 && (
        <div className="flex flex-wrap items-center gap-3">
          <p className="text-sm text-ink-soft dark:text-starlight">{failed[0].failure.detail}</p>
          {canRetry && (
            <LemonButton variant="secondary" size="sm" type="button" onClick={onRetry}>
              Try again
            </LemonButton>
          )}
        </div>
      )}
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
                  {p.ip_holder_id} · escrow ${p.escrow_balance_usd}
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
