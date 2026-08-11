import { useEffect, useMemo, useRef, useState } from "react";
import { fetchUserModels, type UserModelRow } from "../../api/settingsModels";
import {
  fetchKeyBalance,
  fetchUsageSnapshot,
  setKeyLimit,
  type KeyBalance,
  type KeyUsageEntry,
} from "../../api/byotUsage";
import { LemonButton, LemonCard, LemonInput } from "../../components/lemon";

type Row = {
  model: UserModelRow;
  usage: KeyUsageEntry | null;
  balance: KeyBalance | null;
  balanceError: string | null;
};

const usd = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 2 });

function dollars(cents: number): string {
  return usd.format(cents / 100);
}

function balancePresentation(balance: KeyBalance | null, error: string | null): {
  headline: string;
  authority: string;
  detail: string | null;
} {
  if (error || !balance || balance.kind === "unavailable") {
    return { headline: "Balance unavailable", authority: "No usable provider report", detail: null };
  }
  if (balance.kind === "balance_native") {
    return {
      headline: `${usd.format(balance.balance_usd!)} available`,
      authority: "Provider balance",
      detail: balance.granted_usd === null ? null : `${usd.format(balance.granted_usd)} granted or cash balance`,
    };
  }
  if (balance.kind === "spend_history") {
    return {
      headline: `${usd.format(balance.spend_usd!)} measured spend`,
      authority: "Antiek meter",
      detail: balance.budget_usd === null
        ? "No Antiek budget set"
        : `${usd.format(Math.max(0, balance.budget_usd - balance.spend_usd!))} of Antiek budget remains`,
    };
  }
  if (balance.kind === "quota_pct") {
    return {
      headline: `${Math.round(balance.utilization! * 100)}% quota used`,
      authority: "Provider quota",
      detail: balance.window_label,
    };
  }
  return {
    headline: `${usd.format(balance.spend_usd!)} measured spend`,
    authority: "Antiek meter",
    detail: balance.window_label,
  };
}

function parseDollarCents(value: string): number | null {
  if (value !== value.trim() || !/^(0|[1-9]\d*)(\.\d{1,2})?$/.test(value)) return null;
  const [whole, fraction = ""] = value.split(".");
  const cents = BigInt(whole) * 100n + BigInt(fraction.padEnd(2, "0"));
  if (cents > BigInt(Number.MAX_SAFE_INTEGER)) return null;
  return Number(cents);
}

export default function ByotUsagePanel() {
  const [rows, setRows] = useState<Row[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [editing, setEditing] = useState<string | null>(null);
  const [limitDollars, setLimitDollars] = useState("");
  const [saving, setSaving] = useState<string | null>(null);
  const [rowError, setRowError] = useState<Record<string, string>>({});
  const refreshVersion = useRef(0);
  const mounted = useRef(false);
  const editButtons = useRef<Record<string, HTMLButtonElement | null>>({});

  async function refresh() {
    const version = ++refreshVersion.current;
    setLoading(true);
    setLoadError(null);
    try {
      const [modelsResponse, usageResponse] = await Promise.all([
        fetchUserModels(),
        fetchUsageSnapshot(),
      ]);
      const usageById = new Map(usageResponse.keys.map((entry) => [entry.api_key_id, entry]));
      const balances = await Promise.all(modelsResponse.models.map(async (model) => {
        try {
          const balance = await fetchKeyBalance(model.id);
          if (model.provider_catalog_id !== null && balance.catalog_id !== model.provider_catalog_id) {
            return { balance: null, error: "Provider balance unavailable" };
          }
          return { balance, error: null };
        } catch {
          return { balance: null, error: "Provider balance unavailable" };
        }
      }));
      if (!mounted.current || version !== refreshVersion.current) return;
      setRows(modelsResponse.models.map((model, index) => ({
        model,
        usage: usageById.get(model.id) ?? null,
        balance: balances[index].balance,
        balanceError: balances[index].error,
      })));
    } catch {
      if (mounted.current && version === refreshVersion.current) {
        setLoadError(rows === null
          ? "Usage data could not be loaded."
          : "Usage data could not be refreshed. Previously shown values may be stale.");
      }
    } finally {
      if (mounted.current && version === refreshVersion.current) setLoading(false);
    }
  }

  useEffect(() => {
    mounted.current = true;
    void refresh();
    return () => {
      mounted.current = false;
      refreshVersion.current += 1;
    };
  }, []);

  const totalUsed = useMemo(
    () => rows?.reduce((sum, row) => sum + (row.usage?.used_cents ?? 0), 0) ?? 0,
    [rows],
  );
  const observedKeys = rows?.filter((row) => row.usage !== null).length ?? 0;

  function openLimit(row: Row) {
    if (saving !== null) return;
    setEditing(row.model.id);
    setLimitDollars(row.usage?.limit_cents == null ? "" : (row.usage.limit_cents / 100).toFixed(2));
    setRowError((current) => ({ ...current, [row.model.id]: "" }));
  }

  function closeLimit(returnFocus = true) {
    const id = editing;
    setEditing(null);
    setLimitDollars("");
    if (returnFocus && id) requestAnimationFrame(() => editButtons.current[id]?.focus());
  }

  async function saveLimit(row: Row, clear = false) {
    if (saving !== null) return;
    const cents = clear ? null : parseDollarCents(limitDollars);
    if (!clear && cents === null) {
      setRowError((current) => ({ ...current, [row.model.id]: "Enter a dollar amount with no more than two decimals." }));
      return;
    }
    setSaving(row.model.id);
    refreshVersion.current += 1;
    setLoading(false);
    setRowError((current) => ({ ...current, [row.model.id]: "" }));
    try {
      const updated = await setKeyLimit(row.model.id, cents);
      if (!mounted.current) return;
      setRows((current) => current?.map((item) => item.model.id === row.model.id ? { ...item, usage: updated } : item) ?? null);
      if (editing === row.model.id) closeLimit();
    } catch {
      if (mounted.current) setRowError((current) => ({ ...current, [row.model.id]: "The spending limit was not saved. Try again." }));
    } finally {
      if (mounted.current) setSaving(null);
    }
  }

  return (
    <LemonCard title="Usage & balances" elevation="z1">
      <section className="space-y-4 p-4" aria-label="BYOT usage and balances">
        <div className="flex flex-wrap items-start justify-between gap-3 border-b border-ink/15 pb-4 dark:border-bright/15">
          <div className="max-w-xl space-y-1">
            <p className="text-sm text-ink dark:text-bright">Antiek-measured spend and provider-reported balances stay separate.</p>
            <p className="text-xs text-ink-soft dark:text-starlight">A limit controls Antiek usage for one stored key. Provider balance is live when the provider exposes it; unavailable never means zero.</p>
          </div>
          <div className="text-right">
            <span className="block font-mono text-lg font-semibold text-ink dark:text-bright">{observedKeys > 0 ? dollars(totalUsed) : "Not measured yet"}</span>
            <span className="text-[11px] uppercase tracking-wider text-ink-soft dark:text-starlight">{observedKeys > 0 ? "Measured spend" : "No ledger observations"}</span>
          </div>
        </div>

        {loadError && <p role="alert" className="text-sm text-emperor">{loadError}</p>}
        {rows === null && !loadError && <p role="status" className="text-sm text-ink-soft dark:text-starlight">Loading usage…</p>}
        {rows?.length === 0 && <p className="text-sm text-ink-soft dark:text-starlight">Add a model key to start measuring usage.</p>}

        {rows && rows.length > 0 && (
          <ul className="divide-y divide-ink/10 dark:divide-bright/10">
            {rows.map((row) => {
              const capped = row.usage?.limit_cents != null;
              const exhausted = capped && row.usage?.remaining_cents === 0;
              const progress = capped && row.usage!.limit_cents! > 0
                ? Math.min(1, row.usage!.used_cents / row.usage!.limit_cents!)
                : null;
              const reported = balancePresentation(row.balance, row.balanceError);
              return (
                <li key={row.model.id} className="space-y-3 py-4 first:pt-0 last:pb-0">
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                    <div className="min-w-0">
                      <h3 className="truncate font-semibold text-ink dark:text-bright">{row.model.display_name}</h3>
                      <p className="truncate font-mono text-xs text-ink-soft dark:text-starlight">{row.model.model_id} · {row.model.provider_kind}</p>
                    </div>
                    <div className="grid grid-cols-2 gap-x-5 gap-y-1 text-left sm:text-right">
                      <div><span className="block font-mono text-sm font-semibold">{row.usage ? dollars(row.usage.used_cents) : "Not measured yet"}</span><span className="text-[11px] text-ink-soft dark:text-starlight">{row.usage ? "Antiek measured" : "No ledger observation"}</span></div>
                      <div><span className={`block text-sm font-semibold ${exhausted ? "text-emperor" : "text-ink dark:text-bright"}`}>{capped ? dollars(row.usage!.remaining_cents ?? 0) : "No limit"}</span><span className="text-[11px] text-ink-soft dark:text-starlight">{capped ? "Limit remaining" : "Antiek ceiling"}</span></div>
                    </div>
                  </div>

                  {progress !== null && (
                    <div className="space-y-1" aria-label={`${row.model.display_name} Antiek spending limit`}>
                      <div className="flex justify-between gap-3 text-[11px] text-ink-soft dark:text-starlight">
                        <span>Antiek limit used</span>
                        <span className="font-mono">{Math.round(progress * 100)}%</span>
                      </div>
                      <meter className="h-2 w-full" min={0} max={1} value={progress} aria-label={`${row.model.display_name} spending limit used`} />
                    </div>
                  )}

                  <div className="rounded-hog border border-ink/15 bg-ice-1 px-3 py-2 dark:border-bright/15 dark:bg-charcoal-2">
                    <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
                      <span className="font-semibold text-ink dark:text-bright">{reported.headline}</span>
                      <span className="font-mono text-ink-soft dark:text-starlight">{reported.authority}</span>
                    </div>
                    {reported.detail && <p className="mt-1 text-[11px] text-ink-soft dark:text-starlight">{reported.detail}</p>}
                    {row.balance?.resets_at != null && <p className="mt-1 text-[11px] text-ink-soft dark:text-starlight">Resets {new Date(row.balance.resets_at * 1000).toLocaleString()}</p>}
                  </div>

                  {editing === row.model.id ? (
                    <form className="flex flex-col gap-2 sm:flex-row sm:items-end" onSubmit={(event) => { event.preventDefault(); void saveLimit(row); }}>
                      <div className="flex-1 text-xs font-semibold text-ink-soft dark:text-starlight">
                        <label htmlFor={`limit-${row.model.id}`}>Spending limit (USD)</label>
                        <LemonInput id={`limit-${row.model.id}`} autoFocus required disabled={saving !== null} inputMode="decimal" value={limitDollars} onChange={(event) => setLimitDollars(event.target.value)} placeholder="25.00" sizing="lg" wrapperClassName="mt-1 w-full" aria-describedby={rowError[row.model.id] ? `limit-error-${row.model.id}` : undefined} />
                      </div>
                      <div className="flex flex-col gap-2 sm:flex-row">
                        <LemonButton type="submit" size="lg" variant="primary" disabled={saving !== null} fullWidth>{saving === row.model.id ? "Saving…" : "Save limit"}</LemonButton>
                        {capped && <LemonButton type="button" size="lg" variant="secondary" disabled={saving !== null} onClick={() => void saveLimit(row, true)} fullWidth>Clear limit</LemonButton>}
                        <LemonButton type="button" size="lg" variant="tertiary" disabled={saving !== null} onClick={() => closeLimit()} fullWidth>Cancel</LemonButton>
                      </div>
                    </form>
                  ) : (
                    <LemonButton ref={(node) => { editButtons.current[row.model.id] = node; }} type="button" size="lg" variant="tertiary" disabled={saving !== null} onClick={() => openLimit(row)}>{capped ? "Change limit" : "Set spending limit"}</LemonButton>
                  )}
                  {rowError[row.model.id] && <p id={`limit-error-${row.model.id}`} role="alert" className="text-sm text-emperor">{rowError[row.model.id]}</p>}
                </li>
              );
            })}
          </ul>
        )}

        <div className="flex justify-end border-t border-ink/15 pt-4 dark:border-bright/15">
          <LemonButton type="button" size="lg" variant="secondary" disabled={loading || saving !== null} onClick={() => void refresh()}>{loading ? "Refreshing…" : "Refresh balances"}</LemonButton>
        </div>
      </section>
    </LemonCard>
  );
}
