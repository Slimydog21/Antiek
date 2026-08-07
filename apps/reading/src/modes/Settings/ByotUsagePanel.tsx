import { useCallback, useEffect, useState } from "react";

import {
  fetchKeyBalance,
  fetchKeyUsage,
  type KeyBalanceResponse,
  type KeyUsageEntry,
} from "../../api/settingsModels";
import LemonCard from "../../components/lemon/LemonCard";
import { LemonButton } from "../../components/lemon";

type BalanceState =
  | { status: "loading" }
  | { status: "ready"; value: KeyBalanceResponse }
  | { status: "error"; message: string };

function dollarsFromCents(cents: number): string {
  return `$${(cents / 100).toFixed(2)}`;
}

function dollars(value: number): string {
  return `$${value.toFixed(2)}`;
}

function BalanceValue({ state }: { state: BalanceState | undefined }) {
  if (!state || state.status === "loading") return <span>checking…</span>;
  if (state.status === "error") {
    return <span title={state.message}>unavailable</span>;
  }

  const balance = state.value;
  if (balance.kind === "balance_native" && balance.balance_usd != null) {
    return (
      <span title={balance.note ?? "Provider-reported balance"}>
        {dollars(balance.balance_usd)} provider balance
      </span>
    );
  }
  if (balance.kind === "quota_pct" && balance.utilization != null) {
    return (
      <span title={balance.note ?? undefined}>
        {(balance.utilization * 100).toFixed(0)}% quota used
      </span>
    );
  }
  if (balance.kind === "spend_history" && balance.spend_usd != null) {
    return (
      <span title={balance.note ?? undefined}>
        {dollars(balance.spend_usd)} provider spend
      </span>
    );
  }
  if (balance.kind === "meter_only") {
    return <span title={balance.note ?? undefined}>local meter only</span>;
  }
  return <span title={balance.note ?? undefined}>unavailable</span>;
}

export default function ByotUsagePanel() {
  const [rows, setRows] = useState<KeyUsageEntry[] | null>(null);
  const [balances, setBalances] = useState<Record<string, BalanceState>>({});
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    setRefreshing(true);
    setError(null);
    try {
      const snapshot = await fetchKeyUsage();
      setRows(snapshot.keys);
      setBalances(Object.fromEntries(snapshot.keys.map((row) => [row.api_key_id, { status: "loading" }])));
      await Promise.all(snapshot.keys.map(async (row) => {
        try {
          const value = await fetchKeyBalance(row.api_key_id);
          setBalances((current) => ({ ...current, [row.api_key_id]: { status: "ready", value } }));
        } catch (cause) {
          const message = cause instanceof Error ? cause.message : String(cause);
          setBalances((current) => ({ ...current, [row.api_key_id]: { status: "error", message } }));
        }
      }));
    } catch (cause) {
      setRows(null);
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setRefreshing(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  return (
    <LemonCard
      title="Key usage ledger"
      elevation="z1"
      footer={(
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-[11px] text-ink-soft dark:text-starlight">
            Ledger spend is local. Provider balance is queried separately and may be unavailable.
          </p>
          <LemonButton size="sm" variant="tertiary" onClick={() => void load()} disabled={refreshing}>
            {refreshing ? "Refreshing…" : "Refresh balances"}
          </LemonButton>
        </div>
      )}
    >
      <div className="space-y-3">
        {error && <p role="alert" className="text-sm font-mono text-red-700 dark:text-red-300">Usage unavailable: {error}</p>}
        {rows === null && !error && <p className="text-sm text-ink-soft dark:text-starlight">Loading key usage…</p>}
        {rows?.length === 0 && <p className="text-sm text-ink-soft dark:text-starlight">No metered keys yet.</p>}
        {rows && rows.length > 0 && (
          <div className="divide-y divide-ink/10 dark:divide-bright/10">
            <div aria-hidden="true" className="hidden sm:grid sm:grid-cols-[minmax(0,1.5fr)_repeat(4,minmax(0,1fr))] gap-3 pb-2 text-[11px] uppercase tracking-wider text-ink-soft dark:text-starlight">
              <span>Key</span><span>Ledger spend</span><span>Ceiling</span><span>Remaining</span><span>Provider signal</span>
            </div>
            {rows.map((row) => (
              <div key={row.api_key_id} className="grid grid-cols-2 sm:grid-cols-[minmax(0,1.5fr)_repeat(4,minmax(0,1fr))] gap-x-3 gap-y-2 py-3 font-mono text-[12px]">
                <div className="col-span-2 sm:col-span-1 min-w-0">
                  <span className="sm:hidden text-[10px] uppercase tracking-wider text-ink-soft dark:text-starlight block">Key</span>
                  <span className="block truncate font-semibold text-ink dark:text-bright" title={row.api_key_id}>{row.api_key_id}</span>
                </div>
                <LedgerCell label="Ledger spend" value={dollarsFromCents(row.used_cents)} />
                <LedgerCell label="Ceiling" value={row.limit_cents == null ? "unset" : dollarsFromCents(row.limit_cents)} />
                <LedgerCell label="Remaining" value={row.remaining_cents == null ? "unknown" : dollarsFromCents(row.remaining_cents)} />
                <div className="col-span-2 sm:col-span-1 min-w-0 text-ink dark:text-bright">
                  <span className="sm:hidden text-[10px] uppercase tracking-wider text-ink-soft dark:text-starlight block">Provider signal</span>
                  <BalanceValue state={balances[row.api_key_id]} />
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </LemonCard>
  );
}

function LedgerCell({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0 text-ink dark:text-bright">
      <span className="sm:hidden text-[10px] uppercase tracking-wider text-ink-soft dark:text-starlight block">{label}</span>
      <span>{value}</span>
    </div>
  );
}
