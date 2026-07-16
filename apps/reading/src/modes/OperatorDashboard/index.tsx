import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import watchRoomEnvironment from "../../brand/werner/operator/operator_watch_room_environment_v1.webp";
import { apiFetch } from "../../lib/api";
import "./operator-watch-room.css";

export interface PublisherSummary {
  ip_holder_id: string;
  display_name: string;
  legal_contact_email: string | null;
  status: string;
  escrow_balance_usd: string;
  notification_sent_at: string | null;
  claimed_at: string | null;
  opted_out_at: string | null;
}

export interface StatsResponse {
  counts?: Record<string, number>;
  warnings?: unknown[];
}

interface DeletionRequest { status: string }

export interface PayoutTransfer {
  status: string;
  amount_usd_cents: number;
  initiated_at: string | null;
}

export interface OperatorSnapshot {
  stats: StatsResponse | null;
  pendingDeletions: number | null;
  recentPayouts: PayoutTransfer[] | null;
}

export interface OperatorDashboardProps {
  executionEnabled?: boolean;
  initialPublishers?: PublisherSummary[] | null;
  initialSnapshot?: OperatorSnapshot;
  initialLoading?: boolean;
  initialError?: boolean;
  initialNotifyingId?: string | null;
}

const EMPTY_SNAPSHOT: OperatorSnapshot = {
  stats: null,
  pendingDeletions: null,
  recentPayouts: null,
};
const SAFE_LOAD_ERROR = "The operator watch room could not be refreshed. Try again in a moment.";
const SAFE_RECORD_ERROR = "The external notice could not be recorded. Nothing was changed.";

export default function OperatorDashboard({
  executionEnabled = true,
  initialPublishers,
  initialSnapshot = EMPTY_SNAPSHOT,
  initialLoading,
  initialError = false,
  initialNotifyingId = null,
}: OperatorDashboardProps) {
  const [publishers, setPublishers] = useState<PublisherSummary[] | null>(
    initialPublishers !== undefined ? initialPublishers : (executionEnabled ? null : []),
  );
  const [snapshot, setSnapshot] = useState<OperatorSnapshot>(initialSnapshot);
  const [loading, setLoading] = useState(initialLoading ?? executionEnabled);
  const [error, setError] = useState<string | null>(initialError ? SAFE_LOAD_ERROR : null);
  const [notifyingIds, setNotifyingIds] = useState<ReadonlySet<string>>(
    () => new Set(initialNotifyingId ? [initialNotifyingId] : []),
  );
  const requestSequence = useRef(0);
  const notificationsInFlight = useRef(new Set<string>());

  const reload = useCallback(async () => {
    if (!executionEnabled) return;
    const requestId = ++requestSequence.current;
    setLoading(true);
    setError(null);
    try {
      const [publishersResp, statsResp, deletionsResp, payoutsResp] = await Promise.all([
        apiFetch("/publishers"),
        apiFetch("/stats").catch(() => null),
        apiFetch("/trust-center/deletion-requests").catch(() => null),
        apiFetch("/payouts/transfers?limit=5").catch(() => null),
      ]);
      if (!publishersResp.ok) throw new Error("publisher roster unavailable");

      const publisherData = await publishersResp.json();
      if (!Array.isArray(publisherData?.publishers) ||
          !publisherData.publishers.every(isPublisherSummary)) {
        throw new Error("invalid publisher roster");
      }
      const nextPublishers = publisherData.publishers as PublisherSummary[];
      let stats: StatsResponse | null = null;
      if (statsResp?.ok) {
        try { stats = await statsResp.json() as StatsResponse; } catch { stats = null; }
      }
      let pendingDeletions: number | null = null;
      if (deletionsResp?.ok) {
        try {
          const data = await deletionsResp.json();
          if (Array.isArray(data?.requests)) {
            pendingDeletions = (data.requests as DeletionRequest[]).filter((request) => request.status === "pending").length;
          }
        } catch { pendingDeletions = null; }
      }
      let recentPayouts: PayoutTransfer[] | null = null;
      if (payoutsResp?.ok) {
        try {
          const data = await payoutsResp.json();
          if (Array.isArray(data?.transfers) && data.transfers.every(isPayoutTransfer)) {
            recentPayouts = data.transfers;
          }
        } catch { recentPayouts = null; }
      }
      if (requestId === requestSequence.current) {
        setPublishers(nextPublishers);
        setSnapshot({ stats, pendingDeletions, recentPayouts });
      }
    } catch {
      if (requestId === requestSequence.current) setError(SAFE_LOAD_ERROR);
    } finally {
      if (requestId === requestSequence.current) setLoading(false);
    }
  }, [executionEnabled]);

  useEffect(() => {
    void reload();
    return () => { requestSequence.current += 1; };
  }, [reload]);

  const handleRecordNotice = async (id: string) => {
    if (!executionEnabled || notificationsInFlight.current.has(id)) return;
    notificationsInFlight.current.add(id);
    setNotifyingIds((current) => new Set(current).add(id));
    setError(null);
    let response: Response;
    try {
      response = await apiFetch(`/publishers/${encodeURIComponent(id)}/notify`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      });
      if (!response.ok) throw new Error("notice receipt unavailable");
    } catch {
      setError(SAFE_RECORD_ERROR);
      notificationsInFlight.current.delete(id);
      setNotifyingIds((current) => {
        const next = new Set(current);
        next.delete(id);
        return next;
      });
      return;
    }

    try {
      const recordedPublisher: unknown = await response.json();
      setPublishers((current) => current?.map((publisher) =>
        publisher.ip_holder_id === id
          ? (isPublisherSummary(recordedPublisher)
              ? { ...publisher, ...recordedPublisher }
              : { ...publisher, status: "invited" })
          : publisher,
      ) ?? current);
    } catch {
      // The 2xx response is the mutation authority. Keep the row non-actionable
      // even if its response body cannot be decoded; reload will reconcile it.
      setPublishers((current) => current?.map((publisher) =>
        publisher.ip_holder_id === id ? { ...publisher, status: "invited" } : publisher,
      ) ?? current);
    }

    try {
      await reload();
    } finally {
      notificationsInFlight.current.delete(id);
      setNotifyingIds((current) => {
        const next = new Set(current);
        next.delete(id);
        return next;
      });
    }
  };

  return (
    <main className="operator-watch-room">
      <img className="operator-watch-room__environment" src={watchRoomEnvironment} alt="" aria-hidden="true" draggable={false} />
      <div className="operator-watch-room__veil" aria-hidden="true" />
      <div className="operator-watch-room__content">
        <header className="operator-watch-room__hero">
          <div>
            <p className="operator-watch-room__eyebrow">Operator watch room · independent instruments</p>
            <h1>Keep watch without inventing certainty.</h1>
            <p className="operator-watch-room__lede">Publisher records are the primary roster. Substrate counts, deletion requests, and payout transfers report independently; an unavailable instrument never becomes zero.</p>
          </div>
          <button type="button" onClick={() => void reload()} disabled={!executionEnabled || loading} className="operator-watch-room__refresh">
            {loading ? "Refreshing…" : "Refresh watch room"}
          </button>
        </header>

        <aside className="operator-watch-room__boundary" aria-label="Authority boundary">
          <strong>This room observes and records.</strong> “Record external notice” confirms an email was sent outside Antiek. It does not send email, approve counsel, move escrow, execute a payout, or process a deletion.
        </aside>

        {error && <p className="operator-watch-room__alert" role="alert">{error}</p>}
        {loading && publishers === null && <p className="operator-watch-room__state" role="status">Opening the publisher ledger…</p>}

        <InstrumentDeck snapshot={snapshot} />
        <PublisherLedger publishers={publishers} notifyingIds={notifyingIds} onRecordNotice={handleRecordNotice} />
      </div>
    </main>
  );
}

function InstrumentDeck({ snapshot }: { snapshot: OperatorSnapshot }) {
  const headlineKeys: [string, string][] = [
    ["investigations", "Investigations"], ["notebooks", "Notebooks"], ["outcomes", "Outcomes"],
    ["skill_rules", "Skill rules"], ["payout_transfers", "Payout records"], ["ip_holders", "IP holders"],
  ];
  return (
    <section className="operator-instruments" aria-labelledby="operator-instruments-heading">
      <div className="operator-watch-room__section-heading"><div><p className="operator-watch-room__eyebrow">Four separate authorities</p><h2 id="operator-instruments-heading">Observation instruments</h2></div><Link to="/stats">Open substrate atlas →</Link></div>
      <div className="operator-instruments__grid">
        <article className="operator-instrument operator-instrument--wide"><header><span>01</span><h3>Substrate cardinality</h3><Availability available={snapshot.stats !== null} /></header><dl>{headlineKeys.map(([key, label]) => <div key={key}><dt>{label}</dt><dd>{formatKnownCount(snapshot.stats?.counts?.[key])}</dd></div>)}</dl>{Array.isArray(snapshot.stats?.warnings) && snapshot.stats.warnings.length > 0 && <p className="operator-instrument__note">{snapshot.stats.warnings.length} {snapshot.stats.warnings.length === 1 ? "area was" : "areas were"} not measured. Diagnostic details stay private.</p>}</article>
        <article className="operator-instrument"><header><span>02</span><h3>Deletion requests</h3><Availability available={snapshot.pendingDeletions !== null} /></header><p className="operator-instrument__value">{snapshot.pendingDeletions === null ? "Unknown" : snapshot.pendingDeletions.toLocaleString()}</p><p className="operator-instrument__note">Pending records only. Processing remains in Privacy.</p><Link to="/privacy">Review privacy queue →</Link></article>
        <article className="operator-instrument"><header><span>03</span><h3>Recent payouts</h3><Availability available={snapshot.recentPayouts !== null} /></header>{snapshot.recentPayouts === null ? <p className="operator-instrument__value">Unknown</p> : snapshot.recentPayouts.length === 0 ? <p className="operator-instrument__empty">No transfer records returned.</p> : <ul>{snapshot.recentPayouts.slice(0, 3).map((payout, index) => <li key={`${payout.initiated_at ?? "undated"}-${index}`}><span>{payout.status.replace(/_/g, " ")}</span><strong>{formatCents(payout.amount_usd_cents)}</strong></li>)}</ul>}<Link to="/payouts">Open payout audit →</Link></article>
      </div>
    </section>
  );
}

function Availability({ available }: { available: boolean }) {
  return <small className={available ? "is-available" : "is-unavailable"}>{available ? "Available" : "Unavailable"}</small>;
}

function PublisherLedger({ publishers, notifyingIds, onRecordNotice }: { publishers: PublisherSummary[] | null; notifyingIds: ReadonlySet<string>; onRecordNotice: (id: string) => Promise<void> }) {
  const buckets = [
    { status: "pre_onboarded", title: "Pre-onboarded", description: "No notification is recorded. Counsel review and external delivery happen outside this room.", action: true },
    { status: "invited", title: "Invited", description: "An external notification is recorded. Escrow and payout authority remain elsewhere.", action: false },
    { status: "claimed", title: "Claimed", description: "A claim is recorded. Inspect the payout audit for transfer facts.", action: false },
    { status: "opted_out", title: "Opted out", description: "An opt-out is recorded. Inspect Privacy for removal work.", action: false },
  ];
  const knownStatuses = new Set(buckets.map((bucket) => bucket.status));
  const unknown = publishers?.filter((publisher) => !knownStatuses.has(publisher.status)) ?? [];
  return (
    <section className="publisher-ledger" aria-labelledby="publisher-ledger-heading"><div className="operator-watch-room__section-heading"><div><p className="operator-watch-room__eyebrow">Primary roster</p><h2 id="publisher-ledger-heading">Publisher ledger</h2></div><span>{publishers === null ? "Unavailable" : `${publishers.length} records`}</span></div>
      {publishers === null ? <p className="operator-watch-room__state">The publisher roster is unavailable.</p> : <div className="publisher-ledger__grid">{buckets.map((bucket) => <PublisherBucket key={bucket.status} {...bucket} publishers={publishers.filter((publisher) => publisher.status === bucket.status)} notifyingIds={notifyingIds} onRecordNotice={onRecordNotice} />)}{unknown.length > 0 && <PublisherBucket status="other" title="Other recorded state" description="These records use a status this view does not interpret." action={false} publishers={unknown} notifyingIds={notifyingIds} onRecordNotice={onRecordNotice} />}</div>}
    </section>
  );
}

function PublisherBucket({ title, description, publishers, action, notifyingIds, onRecordNotice }: { status: string; title: string; description: string; publishers: PublisherSummary[]; action: boolean; notifyingIds: ReadonlySet<string>; onRecordNotice: (id: string) => Promise<void> }) {
  return <article className="publisher-bucket"><header><div><h3>{title}</h3><p>{description}</p></div><span aria-label={`${publishers.length} ${title} records`}>{publishers.length}</span></header>{publishers.length === 0 ? <p className="publisher-bucket__empty">No records in this state.</p> : <ul>{publishers.map((publisher) => { const pending = notifyingIds.has(publisher.ip_holder_id); return <li key={publisher.ip_holder_id}><div><strong>{publisher.display_name}</strong><code>{publisher.ip_holder_id}</code><small>Escrow recorded: {formatEscrow(publisher.escrow_balance_usd)}</small>{publisher.legal_contact_email && <small>Legal contact: {publisher.legal_contact_email}</small>}</div>{action && <button type="button" disabled={pending} onClick={() => void onRecordNotice(publisher.ip_holder_id)}>{pending ? "Recording…" : "Record external notice"}</button>}</li>; })}</ul>}</article>;
}

function isPayoutTransfer(value: unknown): value is PayoutTransfer {
  if (typeof value !== "object" || value === null) return false;
  const transfer = value as Record<string, unknown>;
  return typeof transfer.status === "string" &&
    typeof transfer.amount_usd_cents === "number" &&
    Number.isFinite(transfer.amount_usd_cents) &&
    (typeof transfer.initiated_at === "string" || transfer.initiated_at === null);
}

function isPublisherSummary(value: unknown): value is PublisherSummary {
  if (typeof value !== "object" || value === null) return false;
  const publisher = value as Record<string, unknown>;
  return typeof publisher.ip_holder_id === "string" &&
    typeof publisher.display_name === "string" &&
    typeof publisher.status === "string" &&
    typeof publisher.escrow_balance_usd === "string" &&
    isNullableString(publisher.legal_contact_email) &&
    isNullableString(publisher.notification_sent_at) &&
    isNullableString(publisher.claimed_at) &&
    isNullableString(publisher.opted_out_at);
}

function isNullableString(value: unknown): value is string | null {
  return typeof value === "string" || value === null;
}

function formatKnownCount(value: number | undefined): string {
  return typeof value === "number" && Number.isFinite(value) && value >= 0 ? value.toLocaleString() : "Unknown";
}
function formatCents(value: number): string {
  return Number.isFinite(value) ? new Intl.NumberFormat(undefined, { style: "currency", currency: "USD" }).format(value / 100) : "Unknown";
}
function formatEscrow(value: string): string {
  const amount = Number(value);
  return Number.isFinite(amount) ? new Intl.NumberFormat(undefined, { style: "currency", currency: "USD" }).format(amount) : "Unknown";
}
