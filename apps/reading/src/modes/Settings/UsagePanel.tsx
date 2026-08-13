import { useEffect, useMemo, useRef, useState } from "react";
import LemonCard from "../../components/lemon/LemonCard";
import { LemonButton } from "../../components/lemon";
import { fetchSettingsModels, type ModelRow } from "../../api/settings";
import {
  fetchSettingsBalance,
  fetchSettingsUsage,
  setSettingsUsageLimit,
  type SettingsBalanceResponse,
  type SettingsUsageKeyEntry,
} from "../../api/settingsUsage";
import { fetchUserModels, type UserModelRow } from "../../api/settingsModels";

type BalanceState =
  | { state: "loading" }
  | { state: "ready"; value: SettingsBalanceResponse }
  | { state: "error" };

type PanelMessage =
  | { kind: "status"; keyId: string; text: string }
  | { kind: "error"; keyId: string; text: string }
  | null;

function formatCents(value: number | null): string {
  if (value == null) return "unknown";
  return `$${(value / 100).toFixed(2)}`;
}

function formatUsd(value: number): string {
  return `$${value.toFixed(2)}`;
}

function usageFallback(apiKeyId: string): SettingsUsageKeyEntry {
  return {
    api_key_id: apiKeyId,
    used_cents: 0,
    limit_cents: null,
    remaining_cents: null,
    held_cents: 0,
    available_cents: null,
  };
}

function toLimitDraft(limitCents: number | null): string {
  return limitCents == null ? "" : (limitCents / 100).toFixed(2);
}

function usageBadge(entry: SettingsUsageKeyEntry): string {
  return `used ${formatCents(entry.used_cents)} · cap ${formatCents(entry.limit_cents)} · remaining ${formatCents(entry.remaining_cents)} · held ${formatCents(entry.held_cents)} · available ${formatCents(entry.available_cents)}`;
}

function balanceLabel(
  balance: SettingsBalanceResponse,
  usage: SettingsUsageKeyEntry,
): {
  text: string;
  tone: "ok" | "unknown";
} {
  if (balance.kind === "unavailable") {
    return { text: "Live balance unavailable", tone: "unknown" };
  }
  if (
    typeof balance.balance_usd === "number" &&
    Number.isFinite(balance.balance_usd)
  ) {
    return {
      text: `Live balance ${formatUsd(balance.balance_usd)}`,
      tone: "ok",
    };
  }
  const usageAvailable = usage.available_cents;
  if (typeof usageAvailable === "number" && Number.isFinite(usageAvailable)) {
    return {
      text: `Live available ${formatCents(usageAvailable)}`,
      tone: "ok",
    };
  }
  if (
    typeof balance.budget_usd === "number" &&
    Number.isFinite(balance.budget_usd) &&
    typeof balance.spend_usd === "number" &&
    Number.isFinite(balance.spend_usd)
  ) {
    return {
      text: `Budget remaining ${formatUsd(balance.budget_usd - balance.spend_usd)}`,
      tone: "ok",
    };
  }
  if (
    typeof balance.utilization === "number" &&
    Number.isFinite(balance.utilization) &&
    balance.utilization >= 0 &&
    balance.utilization <= 1
  ) {
    return {
      text: `Quota remaining ${Math.max(0, (1 - balance.utilization) * 100).toFixed(1)}%`,
      tone: "ok",
    };
  }
  return { text: "Live balance unavailable", tone: "unknown" };
}

export default function UsagePanel() {
  const [keys, setKeys] = useState<UserModelRow[] | null>(null);
  const [usageByKey, setUsageByKey] = useState<Record<string, SettingsUsageKeyEntry>>({});
  const [modelsByProvider, setModelsByProvider] = useState<Record<string, ModelRow>>({});
  const [balances, setBalances] = useState<Record<string, BalanceState>>({});
  const [limitDrafts, setLimitDrafts] = useState<Record<string, string>>({});
  const [loadError, setLoadError] = useState<string | null>(null);
  const [busyKeyId, setBusyKeyId] = useState<string | null>(null);
  const [message, setMessage] = useState<PanelMessage>(null);
  const loadVersionRef = useRef(0);

  const rows = useMemo(() => {
    if (keys == null) return null;
    return keys
      .map((key) => {
        const usage = usageByKey[key.id] ?? usageFallback(key.id);
        const modelRow = modelsByProvider[key.id] ?? null;
        const models = [
          ...new Set(
            [key.model_id, modelRow?.primary_model]
              .filter((item): item is string => item != null && item.length > 0),
          ),
        ];
        return { id: key.id, key, usage, modelRow, models };
      })
      .sort((left, right) =>
        left.key.display_name.localeCompare(right.key.display_name),
      );
  }, [keys, usageByKey, modelsByProvider]);

  async function refresh() {
    const version = loadVersionRef.current + 1;
    loadVersionRef.current = version;
    setLoadError(null);
    const [userModelsResult, usageResult, settingsModelsResult] = await Promise.allSettled([
      fetchUserModels(),
      fetchSettingsUsage(),
      fetchSettingsModels(),
    ]);
    if (loadVersionRef.current !== version) return;

    if (userModelsResult.status === "rejected") {
      setLoadError("Can't load BYOT keys right now. Try again.");
      setKeys([]);
      setUsageByKey({});
      setModelsByProvider({});
      setBalances({});
      return;
    }

    const userModels = userModelsResult.value.models;
    setKeys(userModels);
    if (usageResult.status === "fulfilled") {
      const keyIds = new Set(userModels.map((item) => item.id));
      const filteredKeys = usageResult.value.keys.filter((entry) =>
        keyIds.has(entry.api_key_id),
      );
      const byKey = Object.fromEntries(
        filteredKeys.map((entry) => [entry.api_key_id, entry]),
      );
      setUsageByKey(byKey);
      setLimitDrafts((current) => {
        const next = { ...current };
        for (const entry of filteredKeys) {
          if (!(entry.api_key_id in next)) {
            next[entry.api_key_id] = toLimitDraft(entry.limit_cents);
          }
        }
        return next;
      });
    } else {
      setUsageByKey({});
    }

    if (settingsModelsResult.status === "fulfilled") {
      setModelsByProvider(
        Object.fromEntries(
          settingsModelsResult.value.models.map((item) => [item.provider_id, item]),
        ),
      );
    } else {
      setModelsByProvider({});
    }

    const keyIds = userModels.map((item) => item.id);
    if (keyIds.length === 0) {
      setBalances({});
      return;
    }
    setBalances(
      Object.fromEntries(keyIds.map((id) => [id, { state: "loading" as const }])),
    );

    const settled = await Promise.allSettled(
      keyIds.map((id) => fetchSettingsBalance(id)),
    );
    if (loadVersionRef.current !== version) return;

    setBalances(
      Object.fromEntries(
        keyIds.map((id, index) => {
          const result = settled[index];
          if (result.status === "fulfilled") {
            return [id, { state: "ready", value: result.value } satisfies BalanceState];
          }
          return [id, { state: "error" } satisfies BalanceState];
        }),
      ),
    );
  }

  useEffect(() => {
    void refresh();
    return () => {
      loadVersionRef.current += 1;
    };
  }, []);

  async function saveLimit(keyId: string) {
    const raw = (limitDrafts[keyId] ?? "").trim();
    if (!raw) {
      setMessage({
        kind: "error",
        keyId,
        text: "Enter a cap value or use Clear cap.",
      });
      return;
    }
    const asNumber = Number(raw);
    if (!Number.isFinite(asNumber) || asNumber < 0) {
      setMessage({
        kind: "error",
        keyId,
        text: "Cap must be a non-negative dollar value.",
      });
      return;
    }
    const cents = Math.round(asNumber * 100);
    setBusyKeyId(keyId);
    setMessage(null);
    try {
      const updated = await setSettingsUsageLimit(keyId, { limit_cents: cents });
      setUsageByKey((current) => ({
        ...current,
        [keyId]: {
          api_key_id: updated.api_key_id,
          used_cents: updated.used_cents,
          limit_cents: updated.limit_cents,
          remaining_cents: updated.remaining_cents,
          held_cents: updated.held_cents,
          available_cents: updated.available_cents,
        },
      }));
      setLimitDrafts((current) => ({
        ...current,
        [keyId]: toLimitDraft(updated.limit_cents),
      }));
      setMessage({ kind: "status", keyId, text: "Spend cap updated." });
    } catch {
      setMessage({
        kind: "error",
        keyId,
        text: "Couldn't update this spend cap. Try again.",
      });
    } finally {
      setBusyKeyId(null);
    }
  }

  async function clearLimit(keyId: string) {
    setBusyKeyId(keyId);
    setMessage(null);
    try {
      const updated = await setSettingsUsageLimit(keyId, { limit_cents: null });
      setUsageByKey((current) => ({
        ...current,
        [keyId]: {
          api_key_id: updated.api_key_id,
          used_cents: updated.used_cents,
          limit_cents: updated.limit_cents,
          remaining_cents: updated.remaining_cents,
          held_cents: updated.held_cents,
          available_cents: updated.available_cents,
        },
      }));
      setLimitDrafts((current) => ({ ...current, [keyId]: "" }));
      setMessage({ kind: "status", keyId, text: "Spend cap cleared." });
    } catch {
      setMessage({
        kind: "error",
        keyId,
        text: "Couldn't clear this spend cap. Try again.",
      });
    } finally {
      setBusyKeyId(null);
    }
  }

  return (
    <LemonCard title="Usage & balances (BYOT)" elevation="z1">
      <div className="p-4 space-y-4" data-testid="usage-panel">
        <p className="text-sm text-ink-soft dark:text-starlight">
          Per-key usage and live provider balance. Unknown or unavailable values
          stay unknown — never fabricated as $0.00.
        </p>

        {loadError && (
          <div role="alert" className="space-y-2 text-sm text-red-700 dark:text-red-300">
            <p>{loadError}</p>
            <LemonButton size="sm" variant="tertiary" onClick={() => void refresh()}>
              Retry
            </LemonButton>
          </div>
        )}

        {rows === null && !loadError && (
          <p role="status" className="text-sm text-ink-soft dark:text-starlight">
            Loading usage and balances…
          </p>
        )}

        {rows && rows.length === 0 && !loadError && (
          <p className="text-sm text-ink-soft dark:text-starlight">
            No BYOT keys registered yet.
          </p>
        )}

        {rows && rows.length > 0 && (
          <ul className="space-y-3" aria-label="BYOT usage rows">
            {rows.map((row) => {
              const balance = balances[row.id];
              const label =
                balance?.state === "ready"
                  ? balanceLabel(balance.value, row.usage)
                  : balance?.state === "loading"
                    ? { text: "Checking live balance…", tone: "unknown" as const }
                    : { text: "Live balance unavailable", tone: "unknown" as const };
              const capInputId = `usage-cap-${row.id}`;
              const panelMessage = message?.keyId === row.id ? message : null;
              return (
                <li
                  key={row.id}
                  data-testid={`usage-row-${row.id}`}
                  className="space-y-3 rounded-hog border border-ink/10 p-3 dark:border-bright/10"
                >
                  <div className="flex flex-wrap items-baseline justify-between gap-2">
                    <div>
                      <p className="font-semibold text-ink dark:text-bright">
                        {row.key?.display_name ?? row.id}
                      </p>
                      <p className="font-mono text-xs text-ink-soft dark:text-starlight">
                        {row.id}
                        {row.key?.provider_catalog_id
                          ? ` · ${row.key.provider_catalog_id}`
                          : ""}
                      </p>
                    </div>
                    <span
                      className={`text-xs ${
                        label.tone === "ok"
                          ? "text-emerald-700 dark:text-emerald-300"
                          : "text-ink-soft dark:text-starlight"
                      }`}
                    >
                      {label.text}
                    </span>
                  </div>

                  <p className="font-mono text-xs text-ink-soft dark:text-starlight">
                    {usageBadge(row.usage)}
                  </p>

                  <div className="space-y-1">
                    <p className="text-[11px] uppercase tracking-[0.14em] text-ink-soft dark:text-starlight">
                      Models
                    </p>
                    {row.models.length > 0 ? (
                      <ul className="flex flex-wrap gap-2 text-xs">
                        {row.models.map((model) => (
                          <li
                            key={model}
                            className="rounded-hog border border-ink/15 px-2 py-0.5 font-mono dark:border-bright/20"
                          >
                            {model}
                          </li>
                        ))}
                        {row.modelRow && row.modelRow.tier_bindings.length > 0 && (
                          <li className="rounded-hog border border-ink/15 px-2 py-0.5 text-ink-soft dark:border-bright/20 dark:text-starlight">
                            tiers: {row.modelRow.tier_bindings.join(", ")}
                          </li>
                        )}
                      </ul>
                    ) : (
                      <p className="text-xs text-ink-soft dark:text-starlight">
                        No model inventory row found.
                      </p>
                    )}
                  </div>

                  <div className="grid gap-2 min-[560px]:grid-cols-[minmax(0,1fr)_auto_auto] min-[560px]:items-end">
                    <label className="text-xs text-ink-soft dark:text-starlight" htmlFor={capInputId}>
                      Spend cap (USD)
                      <input
                        id={capInputId}
                        type="number"
                        inputMode="decimal"
                        min={0}
                        step="0.01"
                        value={limitDrafts[row.id] ?? toLimitDraft(row.usage.limit_cents)}
                        onChange={(event) =>
                          setLimitDrafts((current) => ({
                            ...current,
                            [row.id]: event.target.value,
                          }))
                        }
                        className="mt-1 block h-10 w-full rounded border border-ink/20 bg-transparent px-2 font-mono text-sm text-ink dark:border-bright/20 dark:text-bright"
                      />
                    </label>
                    <LemonButton
                      type="button"
                      size="sm"
                      variant="secondary"
                      disabled={busyKeyId !== null}
                      onClick={() => void saveLimit(row.id)}
                    >
                      {busyKeyId === row.id ? "Saving…" : "Save cap"}
                    </LemonButton>
                    <LemonButton
                      type="button"
                      size="sm"
                      variant="tertiary"
                      disabled={busyKeyId !== null}
                      onClick={() => void clearLimit(row.id)}
                    >
                      Clear cap
                    </LemonButton>
                  </div>

                  {panelMessage && (
                    <p
                      role={panelMessage.kind === "error" ? "alert" : "status"}
                      className={
                        panelMessage.kind === "error"
                          ? "text-xs text-red-700 dark:text-red-300"
                          : "text-xs text-ink-soft dark:text-starlight"
                      }
                    >
                      {panelMessage.text}
                    </p>
                  )}
                  {balance?.state === "ready" &&
                    balance.value.kind === "unavailable" &&
                    balance.value.note && (
                      <p className="text-xs text-ink-soft dark:text-starlight">
                        {balance.value.note}
                      </p>
                    )}
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </LemonCard>
  );
}
