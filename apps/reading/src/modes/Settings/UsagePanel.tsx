import { useEffect, useState } from "react";
import LemonCard from "../../components/lemon/LemonCard";
import { LemonButton, LemonInput } from "../../components/lemon";
import {
  fetchKeyBalance,
  fetchSettingsUsage,
  setKeyLimit,
  type KeyBalanceResponse,
  type KeyUsageEntry,
} from "../../api/settingsUsage";
import { fetchUserModels, type UserModelRow } from "../../api/settingsModels";

// Per-key BYOT usage + balance surface (backend: byot_usage_routes.py).
//
// Honesty: a null limit renders "no cap" and a null remaining renders
// "unknown" — the UI never invents $0.00 for a ledger that has no number.
// The balance line shows the adapter's own figure per kind; when the
// adapter degrades (kind "unavailable") its note is shown verbatim.

const usd = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 4,
});

export function formatCents(cents: number): string {
  return usd.format(cents / 100);
}

const KIND_LABELS: Record<KeyBalanceResponse["kind"], string> = {
  balance_native: "native balance",
  spend_history: "spend history",
  quota_pct: "quota %",
  meter_only: "meter only",
  unavailable: "unavailable",
};

export default function UsagePanel() {
  const [keys, setKeys] = useState<KeyUsageEntry[] | null>(null);
  const [usageError, setUsageError] = useState<string | null>(null);
  const [names, setNames] = useState<Map<string, UserModelRow>>(new Map());

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetchSettingsUsage();
        if (!cancelled) setKeys(res.keys);
      } catch (e) {
        if (!cancelled)
          setUsageError(e instanceof Error ? e.message : String(e));
      }
    })();
    // Names are a convenience: the raw api_key_id is always the fallback.
    (async () => {
      try {
        const res = await fetchUserModels();
        if (!cancelled)
          setNames(new Map(res.models.map((m) => [m.id, m])));
      } catch {
        // Unresolvable names degrade to the raw id, never a fake label.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  function onLimitUpdated(updated: KeyUsageEntry) {
    setKeys((current) =>
      current
        ? current.map((k) =>
            k.api_key_id === updated.api_key_id ? updated : k,
          )
        : current,
    );
  }

  return (
    <LemonCard title="BYOT usage" elevation="z1">
      <div className="p-4 space-y-3">
        <p className="text-xs text-ink-soft dark:text-starlight">
          Per-key spend from the usage ledger and live balance from each
          provider. Unknown numbers stay unknown — nothing is invented here.
        </p>
        {usageError && (
          <p className="text-sm text-red-700 dark:text-red-300 font-mono">
            {usageError}
          </p>
        )}
        {keys === null && !usageError && (
          <p className="text-sm text-ink-soft dark:text-starlight">
            Loading usage…
          </p>
        )}
        {keys && keys.length === 0 && (
          <p className="text-sm text-ink-soft dark:text-starlight">
            No BYOT keys yet — add one below.
          </p>
        )}
        {keys && keys.length > 0 && (
          <ul className="space-y-1">
            {keys.map((key) => (
              <UsageRow
                key={key.api_key_id}
                entry={key}
                model={names.get(key.api_key_id)}
                onLimitUpdated={onLimitUpdated}
              />
            ))}
          </ul>
        )}
      </div>
    </LemonCard>
  );
}

function UsageRow({
  entry,
  model,
  onLimitUpdated,
}: {
  entry: KeyUsageEntry;
  model: UserModelRow | undefined;
  onLimitUpdated: (updated: KeyUsageEntry) => void;
}) {
  const [balance, setBalance] = useState<KeyBalanceResponse | null>(null);
  const [balanceError, setBalanceError] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [limitError, setLimitError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setBalance(null);
    setBalanceError(null);
    void fetchKeyBalance(entry.api_key_id).then(
      (res) => {
        if (!cancelled) setBalance(res);
      },
      (caught) => {
        if (!cancelled)
          setBalanceError(caught instanceof Error ? caught.message : String(caught));
      },
    );
    return () => {
      cancelled = true;
    };
  }, [entry.api_key_id]);

  const label = model
    ? `${model.display_name} · ${model.model_id}`
    : entry.api_key_id;

  async function onSetLimit() {
    const dollars = Number(draft);
    if (!Number.isFinite(dollars) || dollars <= 0) {
      setLimitError("Enter a positive dollar amount.");
      return;
    }
    setBusy(true);
    setLimitError(null);
    try {
      const updated = await setKeyLimit(
        entry.api_key_id,
        Math.round(dollars * 100),
      );
      setDraft("");
      onLimitUpdated(updated);
    } catch (e) {
      setLimitError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function onClearLimit() {
    setBusy(true);
    setLimitError(null);
    try {
      const updated = await setKeyLimit(entry.api_key_id, null);
      setDraft("");
      onLimitUpdated(updated);
    } catch (e) {
      setLimitError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <li className="border-b border-ink/10 dark:border-bright/10 py-3">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <span className="text-ink dark:text-bright font-semibold break-words">
          {label}
        </span>
        <span className="flex flex-wrap gap-x-3 font-mono text-[12px] text-ink dark:text-bright">
          <span>used {formatCents(entry.used_cents)}</span>
          <span>
            limit{" "}
            {entry.limit_cents === null
              ? "no cap"
              : formatCents(entry.limit_cents)}
          </span>
          <span>
            remaining{" "}
            {entry.remaining_cents === null
              ? "unknown"
              : formatCents(entry.remaining_cents)}
          </span>
        </span>
      </div>

      <BalanceLine balance={balance} error={balanceError} />

      <div className="mt-2 flex flex-wrap items-center gap-2">
        <LemonInput
          sizing="sm"
          type="number"
          min={0}
          step={0.01}
          iconLeft={<span>$</span>}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder={
            entry.limit_cents === null ? "set a cap" : "new cap"
          }
          aria-label={`Set limit for ${label}`}
          className="w-28"
        />
        <LemonButton
          type="button"
          variant="secondary"
          size="sm"
          disabled={busy || draft.trim() === ""}
          onClick={() => void onSetLimit()}
        >
          {busy ? "Saving…" : "Set"}
        </LemonButton>
        {entry.limit_cents !== null && (
          <LemonButton
            type="button"
            variant="tertiary"
            size="sm"
            disabled={busy}
            onClick={() => void onClearLimit()}
          >
            Clear cap
          </LemonButton>
        )}
      </div>
      {limitError && (
        <p
          role="alert"
          className="mt-1 text-xs text-red-700 dark:text-red-300 font-mono"
        >
          {limitError}
        </p>
      )}
    </li>
  );
}

function BalanceLine({
  balance,
  error,
}: {
  balance: KeyBalanceResponse | null;
  error: string | null;
}) {
  // Fetch failure: the note is the honest reason, shown verbatim.
  if (error) {
    return (
      <p
        data-testid="balance-unavailable"
        className="text-xs font-mono text-amber-700 dark:text-amber-300"
      >
        unavailable · {error}
      </p>
    );
  }
  if (balance === null) {
    return (
      <p
        role="status"
        className="text-xs font-mono text-ink-soft dark:text-starlight"
      >
        Checking balance…
      </p>
    );
  }

  const badge = KIND_LABELS[balance.kind];
  let value: string;
  switch (balance.kind) {
    case "balance_native":
      value =
        balance.balance_usd === null ? "unknown" : usd.format(balance.balance_usd);
      break;
    case "spend_history": {
      const spend =
        balance.spend_usd === null ? "unknown" : usd.format(balance.spend_usd);
      value =
        balance.budget_usd === null
          ? `spent ${spend}`
          : `spent ${spend} of ${usd.format(balance.budget_usd)}`;
      break;
    }
    case "quota_pct":
    case "meter_only":
      value =
        balance.utilization === null
          ? "unknown"
          : `${Math.round(balance.utilization * 100)}% used`;
      break;
    case "unavailable":
      // Adapter degraded: its note is the only honest figure, verbatim.
      return (
        <p
          data-testid="balance-unavailable"
          className="text-xs font-mono text-amber-700 dark:text-amber-300"
        >
          {badge}
          {balance.note ? ` · ${balance.note}` : ""}
        </p>
      );
  }

  const extras: string[] = [];
  if (balance.window_label) extras.push(balance.window_label);
  if (balance.resets_at !== null) {
    extras.push(
      `resets ${new Date(balance.resets_at * 1000).toLocaleDateString("en-US", {
        year: "numeric",
        month: "short",
        day: "numeric",
      })}`,
    );
  }
  if (balance.note) extras.push(balance.note);

  return (
    <p
      data-testid="balance-line"
      className="text-xs font-mono text-ink-soft dark:text-starlight"
    >
      <span className="uppercase tracking-wider">{badge}</span>
      {" · "}
      {value}
      {extras.map((extra) => (
        <span key={extra}> · {extra}</span>
      ))}
    </p>
  );
}
