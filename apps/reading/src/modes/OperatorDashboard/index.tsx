import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { LemonButton } from "../../components/lemon";
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

// null: that request has not answered, or failed. The value is unknown and
// is never shown as a 0 or an empty list.
interface CompositeSnapshot {
  stats: StatsResponse | null;
  pendingDeletions: number | null;
  recentPayouts: PayoutTransfer[] | null;
}

/** GET a JSON body, or null when the request fails or answers non-ok. */
async function getJson<T>(path: string): Promise<T | null> {
  try {
    const resp = await apiFetch(path);
    return resp.ok ? ((await resp.json()) as T) : null;
  } catch {
    return null;
  }
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
  // null: not loaded (see CompositeSnapshot) — never "no publishers".
  const [publishers, setPublishers] = useState<PublisherSummary[] | null>(null);
  const [snapshot, setSnapshot] = useState<CompositeSnapshot>({
    stats: null,
    pendingDeletions: null,
    recentPayouts: null,
  });
  const [loading, setLoading] = useState<boolean>(true);
  const [notifyError, setNotifyError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    setLoading(true);
    // Each request settles on its own, so one failing leaves the others
    // standing; a failed one is recorded as unknown (null).
    const [pubData, stats, drData, pData] = await Promise.all([
      getJson<{ publishers?: PublisherSummary[] }>("/publishers"),
      getJson<StatsResponse>("/stats"),
      getJson<{ requests?: DeletionRequest[] }>("/trust-center/deletion-requests"),
      getJson<{ transfers?: PayoutTransfer[] }>("/payouts/transfers?limit=5"),
    ]);
    setPublishers(pubData ? (pubData.publishers ?? []) : null);
    setSnapshot({
      stats,
      pendingDeletions: drData
        ? (drData.requests ?? []).filter((r) => r.status === "pending").length
        : null,
      recentPayouts: pData ? (pData.transfers ?? []) : null,
    });
    setLoading(false);
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  const anyFailed =
    !loading &&
    (publishers === null ||
      snapshot.stats === null ||
      snapshot.pendingDeletions === null ||
      snapshot.recentPayouts === null);

  const handleNotify = async (id: string) => {
    setNotifyError(null);
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
      setNotifyError(e instanceof Error ? e.message : String(e));
    }
  };

  const listed = publishers ?? [];
  const byStatus = {
    pre_onboarded: listed.filter((p) => p.status === "pre_onboarded"),
    invited: listed.filter((p) => p.status === "invited"),
    claimed: listed.filter((p) => p.status === "claimed"),
    opted_out: listed.filter((p) => p.status === "opted_out"),
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
          {anyFailed && (
            <div role="alert" className="flex flex-wrap items-center gap-3">
              <p className="text-sm text-ink dark:text-bright">
                Part of this dashboard didn't load.
              </p>
              <LemonButton variant="secondary" size="sm" type="button" onClick={() => void reload()}>
                Try again
              </LemonButton>
            </div>
          )}
          {notifyError && (
            <p className="text-sm text-emperor" role="alert" title={notifyError}>
              Marking that publisher notified didn't go through.
            </p>
          )}

          <CompositeSnapshotSection snapshot={snapshot} loading={loading} />

          {publishers === null ? (
            !loading && (
              <section className="border border-rule dark:border-charcoal-1 rounded-md p-5">
                <p className="text-sm text-ink dark:text-bright">Publishers didn't load.</p>
              </section>
            )
          ) : (
            <>
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
            </>
          )}
        </div>
      </main>
    </div>
  );
}

function CompositeSnapshotSection({
  snapshot,
  loading,
}: {
  snapshot: CompositeSnapshot;
  loading: boolean;
}) {
  // A value the server didn't give is unknown: "…" while loading, "—" after.
  // /stats answers 200 with empty counts when its own read fails, so a
  // missing key is unknown too, not zero.
  const unknown = loading ? "…" : "—";
  const counts = snapshot.stats?.counts;
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
              {counts?.[k]?.toLocaleString() ?? unknown}
            </p>
            <p className="text-xxs font-mono text-shadow-1 dark:text-moonlight uppercase">
              {label}
            </p>
          </div>
        ))}
      </div>
      {!loading && snapshot.stats === null && (
        <p className="text-sm text-ink dark:text-bright">Substrate counts didn't load.</p>
      )}

      <div className="grid grid-cols-2 gap-3">
        <div className="border border-rule dark:border-charcoal-1 rounded-md px-3 py-2">
          <p className="text-xxs font-mono uppercase text-shadow-1 dark:text-moonlight">
            Pending deletion requests
          </p>
          <p className="text-lg font-serif text-ink dark:text-bright">
            {snapshot.pendingDeletions ?? unknown}
            {snapshot.pendingDeletions !== null && snapshot.pendingDeletions > 0 && (
              <Link
                to="/privacy"
                className="ml-2 text-xs font-mono text-shadow-1 dark:text-moonlight hover:underline"
              >
                review →
              </Link>
            )}
          </p>
          {!loading && snapshot.pendingDeletions === null && (
            <p className="text-xs text-ink dark:text-bright">Deletion requests didn't load.</p>
          )}
        </div>
        <div className="border border-rule dark:border-charcoal-1 rounded-md px-3 py-2">
          <p className="text-xxs font-mono uppercase text-shadow-1 dark:text-moonlight">
            Recent payouts
          </p>
          {snapshot.recentPayouts === null ? (
            <p className="text-sm text-ink dark:text-bright">
              {loading ? "Loading…" : "Transfers didn't load."}
            </p>
          ) : snapshot.recentPayouts.length === 0 ? (
            <p className="text-sm italic text-shadow-1 dark:text-moonlight">No transfers yet.</p>
          ) : (
            <ul className="text-xs font-mono text-ink dark:text-bright space-y-0.5">
              {snapshot.recentPayouts.slice(0, 3).map((p, i) => (
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
