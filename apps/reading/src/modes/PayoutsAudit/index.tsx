import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";

import Werner from "../../brand/Werner";
import environment from "../../brand/werner/payouts/payout_signal_house_environment_v1.webp";
import { apiFetch } from "../../lib/api";
import "./payout-signal-house.css";

export interface PayoutRow {
  transfer_attempt_id: string;
  decision_id: string;
  stripe_transfer_id: string | null;
  recipient_account_id: string | null;
  amount_usd_cents: number;
  status: string;
  note: string | null;
  initiated_at: string | null;
}

export const PAYOUT_STATUSES = ["all", "transferred", "skipped_escrow", "skipped_platform", "failed", "pending"] as const;
export type PayoutStatusFilter = (typeof PAYOUT_STATUSES)[number];
export type PayoutAuditViewProps = {
  rows: PayoutRow[];
  state?: "ready" | "loading" | "error";
  filter: PayoutStatusFilter;
  recipientFilter: string;
  applied?: boolean;
  onFilterChange: (filter: PayoutStatusFilter) => void;
  onRecipientChange: (recipient: string) => void;
  onApply: () => void;
  onClear: () => void;
  onRetry: () => void;
};

const RESULT_LIMIT = 500;
const KNOWN_STATUSES = new Set<string>(PAYOUT_STATUSES.filter((status) => status !== "all"));
const boundedText = (value: unknown, fallback: string) =>
  typeof value === "string" && value.trim() ? value.trim().slice(0, 160) : fallback;
const isPayoutRow = (value: unknown): value is PayoutRow => {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const row = value as Record<string, unknown>;
  return typeof row.transfer_attempt_id === "string" && Boolean(row.transfer_attempt_id.trim()) &&
    typeof row.decision_id === "string" && Boolean(row.decision_id.trim()) &&
    typeof row.status === "string" && Boolean(row.status.trim()) &&
    Number.isInteger(row.amount_usd_cents) && (row.amount_usd_cents as number) >= 0 &&
    (row.stripe_transfer_id === null || typeof row.stripe_transfer_id === "string") &&
    (row.recipient_account_id === null || typeof row.recipient_account_id === "string") &&
    (row.note === null || typeof row.note === "string") &&
    (row.initiated_at === null || typeof row.initiated_at === "string");
};
const safePayload = (value: unknown): PayoutRow[] | null => {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const transfers = (value as Record<string, unknown>).transfers;
  return Array.isArray(transfers) && transfers.every(isPayoutRow) ? transfers : null;
};
const formatCents = (value: number) => new Intl.NumberFormat(undefined, { style: "currency", currency: "USD" }).format(value / 100);
const isProviderAccepted = (row: PayoutRow) =>
  row.status === "transferred" && Boolean(row.stripe_transfer_id?.trim());

function Timestamp({ value }: { value: unknown }) {
  if (typeof value !== "string" || !value.trim()) return <>Time not reported</>;
  const parsed = Date.parse(value);
  if (Number.isNaN(parsed)) return <>Time not reported</>;
  return <time dateTime={value}>{new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(parsed)}</time>;
}

const statusCopy: Record<string, { label: string; meaning: string }> = {
  transferred: { label: "Provider accepted", meaning: "Stripe returned a transfer identifier. Settlement and external reconciliation are not established here." },
  skipped_escrow: { label: "Held in escrow", meaning: "No provider transfer fired; the recorded decision amount remains held for a pre-onboarded publisher." },
  skipped_platform: { label: "Platform residual", meaning: "No provider transfer fired; the amount is recorded as platform residual or a zero-amount skip." },
  failed: { label: "Provider failed", meaning: "The transfer attempt failed and no Stripe transfer identifier was recorded. Inspect protected transport diagnostics for detail." },
  pending: { label: "Pending", meaning: "The schema permits pending, although the current initiator normally writes terminal outcomes directly." },
};

function TransferCard({ row }: { row: PayoutRow }) {
  const known = KNOWN_STATUSES.has(row.status);
  const inconsistentTransfer = row.status === "transferred" && !isProviderAccepted(row);
  const copy = inconsistentTransfer
    ? { label: "Transfer unverified", meaning: "The row is marked transferred but has no provider transfer identifier, so provider acceptance is not established." }
    : statusCopy[row.status] ?? { label: "Unrecognized status", meaning: "The substrate returned a status this client does not classify." };
  return <li><article className={`psh-transfer psh-transfer--${inconsistentTransfer ? "unknown" : known ? row.status : "unknown"}`}>
    <header><div><p className="psh-overline">{copy.label}</p><h3>{formatCents(row.amount_usd_cents)}</h3></div><span>{boundedText(row.status, "unknown").replaceAll("_", " ")}</span></header>
    <p>{copy.meaning}</p>
    <dl><div><dt>Recipient account</dt><dd>{boundedText(row.recipient_account_id, "Not recorded")}</dd></div><div><dt>Decision</dt><dd>{boundedText(row.decision_id, "Unavailable")}</dd></div><div><dt>Stripe transfer</dt><dd>{boundedText(row.stripe_transfer_id, "Not recorded")}</dd></div><div><dt>Recorded</dt><dd><Timestamp value={row.initiated_at} /></dd></div></dl>
    <footer>Attempt {boundedText(row.transfer_attempt_id, "Unavailable")} · Raw provider exception text is intentionally not rendered here.</footer>
  </article></li>;
}

export function PayoutAuditView({ rows, state = "ready", filter, recipientFilter, applied = false, onFilterChange, onRecipientChange, onApply, onClear, onRetry }: PayoutAuditViewProps) {
  const validRows = useMemo(() => rows.filter(isPayoutRow), [rows]);
  const signals = useMemo(() => validRows.reduce((summary, row) => {
    if (isProviderAccepted(row)) summary.acceptedCents += row.amount_usd_cents;
    if (row.status === "skipped_escrow") summary.heldCents += row.amount_usd_cents;
    if (row.status === "failed") summary.failedCount += 1;
    return summary;
  }, { acceptedCents: 0, heldCents: 0, failedCount: 0 }), [validRows]);
  const submit = (event: FormEvent) => { event.preventDefault(); onApply(); };
  return <main className="psh-shell"><img className="psh-environment" src={environment} alt="" aria-hidden="true" /><div className="psh-veil" aria-hidden="true" /><div className="psh-content">
    <header className="psh-hero"><div><p className="psh-eyebrow">IP economics · read-only transfer signals</p><h1>Payout Signal House</h1><p>Inspect the substrate’s newest recorded transfer outcomes without turning a decision amount into a claim that money settled.</p></div><Werner mood={state === "error" ? "empty" : state === "loading" ? "thinking" : "idle"} size={58} label="Werner watches the payout signals" /></header>
    <aside className="psh-truth" aria-label="Audit boundary"><p className="psh-eyebrow">What this instrument establishes</p><p>This is a <strong>read-only substrate log</strong>, capped at {RESULT_LIMIT} newest matching rows. “Transferred” means the provider returned an identifier; it does not prove settlement, bank receipt, Stripe-dashboard reconciliation, or the completeness of all historical records. The current API can also collapse a database-read failure to an empty response.</p></aside>
    <form className="psh-filter" onSubmit={submit} role="search"><header><div><p className="psh-eyebrow">Tune the receiver</p><h2>Query window</h2></div>{applied && <button type="button" className="psh-clear" onClick={onClear}>Clear filters</button>}</header><div className="psh-filter__grid"><label><span>Status</span><select value={filter} onChange={(event) => onFilterChange(event.target.value as PayoutStatusFilter)}>{PAYOUT_STATUSES.map((status) => <option key={status} value={status}>{status.replaceAll("_", " ")}</option>)}</select></label><label><span>Exact recipient account</span><input value={recipientFilter} onChange={(event) => onRecipientChange(event.target.value)} placeholder="acct_…" /></label><button type="submit">Read signals</button></div><p>Totals below describe only this returned query window, never the whole payout substrate.</p></form>
    {state === "loading" && <section className="psh-state" aria-live="polite"><h2>Listening for transfer signals…</h2><p>No zero totals are inferred while the receiver responds.</p></section>}
    {state === "error" && <section className="psh-state psh-state--error" role="alert"><h2>Transfer signals unavailable</h2><p>The response was unavailable or malformed. No empty ledger or zero amount is inferred.</p><button type="button" onClick={onRetry}>Try again</button></section>}
    {state === "ready" && <><section className="psh-summary" aria-labelledby="signal-summary"><header><div><p className="psh-eyebrow">Current query · newest first</p><h2 id="signal-summary">{validRows.length} recorded outcomes</h2></div><strong>{formatCents(signals.acceptedCents)}</strong></header><p>The large amount is the sum of rows marked transferred with a provider identifier in this response—not an externally reconciled payout total.</p><div className="psh-measures"><div><span>{formatCents(signals.acceptedCents)}</span><p>Provider accepted</p></div><div><span>{formatCents(signals.heldCents)}</span><p>Recorded escrow holds</p></div><div><span>{signals.failedCount}</span><p>Failed rows</p></div></div>{validRows.length === RESULT_LIMIT && <p className="psh-cap" role="status">The {RESULT_LIMIT}-row cap was reached. Older matching records may exist beyond this view.</p>}</section>
      {validRows.length === 0 ? <section className="psh-state"><h2>No rows returned</h2><p>No transfer record matched this query, or the current API collapsed a read failure to an empty response. This view cannot distinguish those cases yet.</p></section> : <section className="psh-results" aria-labelledby="signal-ledger"><header><p className="psh-eyebrow">Recorded outcomes</p><h2 id="signal-ledger">Transfer ledger</h2></header><ul>{validRows.map((row) => <TransferCard key={row.transfer_attempt_id} row={row} />)}</ul></section>}
    </>}
  </div></main>;
}

export default function PayoutsAudit() {
  const [rows, setRows] = useState<PayoutRow[]>([]);
  const [state, setState] = useState<"ready" | "loading" | "error">("loading");
  const [filter, setFilter] = useState<PayoutStatusFilter>("all");
  const [recipientFilter, setRecipientFilter] = useState("");
  const [applied, setApplied] = useState(false);
  const requestRef = useRef(0);
  const load = useCallback(async (nextFilter = filter, nextRecipient = recipientFilter) => {
    const token = ++requestRef.current;
    setState("loading");
    try {
      const params = new URLSearchParams({ limit: String(RESULT_LIMIT) });
      if (nextFilter !== "all") params.set("status", nextFilter);
      if (nextRecipient.trim()) params.set("recipient_account_id", nextRecipient.trim());
      const response = await apiFetch(`/payouts/transfers?${params.toString()}`);
      if (!response.ok) throw new Error("load");
      const parsed = safePayload(await response.json());
      if (token !== requestRef.current) return;
      if (!parsed) throw new Error("shape");
      setRows(parsed); setState("ready"); setApplied(nextFilter !== "all" || Boolean(nextRecipient.trim()));
    } catch {
      if (token !== requestRef.current) return;
      setRows([]); setState("error");
    }
  }, [filter, recipientFilter]);
  useEffect(() => { void load("all", ""); return () => { requestRef.current += 1; }; }, []); // initial receiver tune only
  const clear = () => { setFilter("all"); setRecipientFilter(""); void load("all", ""); };
  return <PayoutAuditView rows={rows} state={state} filter={filter} recipientFilter={recipientFilter} applied={applied} onFilterChange={setFilter} onRecipientChange={setRecipientFilter} onApply={() => void load()} onClear={clear} onRetry={() => void load()} />;
}
