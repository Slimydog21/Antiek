import { useCallback, useEffect, useMemo, useState } from "react";

import { LemonButton } from "../lemon";
import { LemonDropdown, LemonMenuItem } from "../lemon/LemonDropdown";
import {
  fetchUserModels,
  type UserModelRow,
} from "../../api/settingsModels";
import { userModelVariants } from "../../lib/userModelVariants";
import {
  fetchSettingsUsage,
  fetchSettingsBalance,
  type SettingsUsageKeyEntry,
  type SettingsBalanceResponse,
} from "../../api/settingsUsage";

/**
 * ModelUsagePicker — reusable BYOT model selector with usage + balance.
 *
 * Renders inside a LemonDropdown. Each row:
 *   provider/model label (from user model display_name or catalog+model)
 *   usage bar (spent / limit) from /settings/usage
 *   balance chip (from /settings/balance/{id}; "—" when unavailable or loading)
 *
 * One row per registered key. A key whose registration lists several
 * `model_ids` (one credential, one ledger row, several variants — e.g.
 * DeepSeek V4 Pro and V4 Flash) renders ONE key row with the usage bar and
 * balance chip once, and a variant sub-row per model_id beneath it; choosing
 * a sub-row reports `(rowId, modelId)`. A single-variant key renders flat.
 *
 * Mount sites (re-verify with git grep for the JSX tag, since a docstring
 * here once promised surfaces that never mounted it): AISidecar, CommandPalette,
 * BrainstormStation/ThoughtPartnerPanel, Reading/TalkToBook, Biography,
 * ResearchWorkstation/ChatInputArea, Write/ConnectResearch. Keeps the Lemon
 * idiom; no copy-paste of dropdown chrome.
 */

export interface ModelUsagePickerProps {
  /** Currently selected user model id (UserModelRow.id). */
  value: string | null;
  /** Currently selected variant under `value` (one of the row's
   *  `model_ids`); null/undefined means the row's primary `model_id`. */
  valueModelId?: string | null;
  /** Called with the chosen user model row id and, when the row lists
   *  several variants, the chosen variant's model id. Consumers that ignore
   *  the second argument keep driving the row's primary model_id. */
  onChange: (userModelId: string, modelId?: string) => void;
  /** Optional filter predicate (e.g. only route_eligible). */
  filter?: (m: UserModelRow) => boolean;
  /** Label for the trigger button. */
  triggerLabel?: string;
  /** Size for trigger. */
  size?: "sm" | "md";
  /** Show usage bars inside the menu (default true). */
  showUsage?: boolean;
  /** Show balance chips (default true). */
  showBalance?: boolean;
  /** Include a "Default (house route)" row at the top (value ""). */
  includeDefault?: boolean;
  /** Label for the default row (used with includeDefault). */
  defaultLabel?: string;
  /** Optional pre-fetched models (skips the internal fetch — single source
   *  of truth when the parent already loads the inventory). */
  models?: UserModelRow[];
  /** Accessible name for the trigger button. */
  triggerAriaLabel?: string;
  className?: string;
}

interface EnrichedModel extends UserModelRow {
  usage?: SettingsUsageKeyEntry;
  balance?: SettingsBalanceResponse | null; // null = loading or error → show "—"
  balanceLoading?: boolean;
}

function formatCents(cents: number | null | undefined): string {
  if (cents == null) return "—";
  const usd = cents / 100;
  return usd >= 1 ? `$${usd.toFixed(2)}` : `$${usd.toFixed(3)}`;
}

function usageBar(usage?: SettingsUsageKeyEntry): React.ReactNode {
  if (!usage || usage.limit_cents == null || usage.limit_cents <= 0) {
    return (
      <span className="text-xxs text-ink-mute dark:text-moonlight">
        {usage ? formatCents(usage.used_cents) : "—"} / uncapped
      </span>
    );
  }
  const pct = Math.min(
    100,
    Math.max(0, ((usage.used_cents || 0) / usage.limit_cents) * 100),
  );
  const over = (usage.used_cents || 0) > usage.limit_cents;
  return (
    <div className="flex items-center gap-1.5 min-w-[120px]">
      <div className="h-1.5 flex-1 bg-ice-2 dark:bg-charcoal-1 rounded overflow-hidden border border-edge">
        <div
          className={
            "h-full " +
            (over ? "bg-danger" : "bg-sun")
          }
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-xxs tabular-nums text-ink-soft dark:text-starlight whitespace-nowrap">
        {formatCents(usage.used_cents)} / {formatCents(usage.limit_cents)}
      </span>
    </div>
  );
}

/**
 * The balance chip switches on `kind`, because the two numbers the backend
 * can return are not the same number:
 *   - `balance_native` is credit the PROVIDER reports as remaining;
 *   - `spend_history` is Antiek's OWN meter of what this app has settled
 *     against the key (plus the user's cap) — the provider was never asked.
 * A meter styled as credit is a wrong number, not a missing one, so the two
 * kinds get distinct text, styling, a title that says which it is, and a
 * `data-balance-kind` attribute the tests assert on. Anything else is "—".
 */
function balanceChip(b?: SettingsBalanceResponse | null, loading?: boolean): React.ReactNode {
  if (loading) return <span className="text-xxs text-ink-mute">…</span>;
  if (!b || b.kind === "unavailable") {
    return (
      <span className="text-xxs text-ink-mute dark:text-moonlight" title={b?.note || undefined}>
        —
      </span>
    );
  }
  if (b.kind === "balance_native" && b.balance_usd != null) {
    const negative = b.balance_usd < 0;
    return (
      <span
        data-balance-kind="balance_native"
        className={
          "text-xxs tabular-nums px-1 py-px rounded " +
          (negative ? "text-danger bg-danger/10" : "text-success bg-success/10")
        }
        title={`Provider credit reported by ${b.catalog_id}${b.note ? ` · ${b.note}` : ""}`}
      >
        {negative ? "" : "+"}${b.balance_usd.toFixed(2)}{" "}
        <span className="opacity-70">credit</span>
      </span>
    );
  }
  if (b.kind === "spend_history" && b.spend_usd != null) {
    const budget = b.budget_usd;
    const over = budget != null && b.spend_usd > budget;
    return (
      <span
        data-balance-kind="spend_history"
        className={
          "text-xxs tabular-nums px-1 py-px rounded border border-edge " +
          (over
            ? "text-danger bg-danger/10"
            : "text-ink-soft dark:text-starlight bg-ice-2 dark:bg-charcoal-1")
        }
        title={
          "Antiek spend meter — not provider credit" +
          (budget != null ? ` · cap $${budget.toFixed(2)}` : " · uncapped")
        }
      >
        spent ${b.spend_usd.toFixed(2)}
        {budget != null ? ` / $${budget.toFixed(2)}` : ""}
      </span>
    );
  }
  return (
    <span
      className="text-xxs text-ink-mute dark:text-moonlight"
      title={b.note || b.window_label || undefined}
    >
      —
    </span>
  );
}

export default function ModelUsagePicker({
  value,
  valueModelId = null,
  onChange,
  filter,
  triggerLabel = "Model",
  size = "md",
  showUsage = true,
  showBalance = true,
  includeDefault = false,
  defaultLabel = "Default (house route)",
  models,
  triggerAriaLabel,
  className = "",
}: ModelUsagePickerProps) {
  const [enriched, setEnriched] = useState<EnrichedModel[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const [um, us] = await Promise.all([
        models ? Promise.resolve({ models, count: models.length }) : fetchUserModels(),
        fetchSettingsUsage().catch(() => ({ keys: [], count: 0 })), // usage is best-effort
      ]);
      const filtered = filter ? um.models.filter(filter) : um.models;
      // Seed enriched without balances (balances fetched on demand or eagerly for small N)
      const seeded: EnrichedModel[] = filtered.map((m) => ({
        ...m,
        usage: us.keys.find((k) => k.api_key_id === m.id),
        balance: null,
        balanceLoading: false,
      }));
      setEnriched(seeded);

      // Eagerly fetch balances for the first few (cheap, defensive)
      for (const m of seeded.slice(0, 6)) {
        if (m.key_present) {
          // fire and forget; component will re-render when they land
          fetchSettingsBalance(m.id)
            .then((bal) => {
              setEnriched((prev) =>
                prev.map((e) =>
                  e.id === m.id ? { ...e, balance: bal, balanceLoading: false } : e,
                ),
              );
            })
            .catch(() => {
              setEnriched((prev) =>
                prev.map((e) =>
                  e.id === m.id ? { ...e, balance: null, balanceLoading: false } : e,
                ),
              );
            });
        }
      }
    } catch (e) {
      setLoadError(e instanceof Error ? e.message : String(e));
      setEnriched([]);
    } finally {
      setLoading(false);
    }
  }, [filter, models]);

  useEffect(() => {
    void load();
  }, [load, models]);

  // Variant grouping: registrations of the SAME provider (e.g. DeepSeek
  // V4 Pro + V4 Flash from one key) render under one provider header with
  // model_id as the variant label. Singletons render flat (display_name).
  const grouped = useMemo(() => {
    const byProvider = new Map<string, EnrichedModel[]>();
    for (const m of enriched) {
      const key = m.provider_catalog_id || m.provider_kind;
      const bucket = byProvider.get(key) ?? [];
      bucket.push(m);
      byProvider.set(key, bucket);
    }
    const groups: { key: string; label: string | null; items: EnrichedModel[] }[] = [];
    for (const [key, items] of byProvider) {
      groups.push({ key, label: items.length > 1 ? key : null, items });
    }
    return groups;
  }, [enriched]);

  const selected = useMemo(
    () => enriched.find((e) => e.id === value) ?? null,
    [enriched, value],
  );

  const refreshBalances = useCallback(async () => {
    for (const m of enriched) {
      if (m.key_present) {
        setEnriched((prev) =>
          prev.map((e) => (e.id === m.id ? { ...e, balanceLoading: true } : e)),
        );
        try {
          const bal = await fetchSettingsBalance(m.id);
          setEnriched((prev) =>
            prev.map((e) =>
              e.id === m.id ? { ...e, balance: bal, balanceLoading: false } : e,
            ),
          );
        } catch {
          setEnriched((prev) =>
            prev.map((e) =>
              e.id === m.id ? { ...e, balance: null, balanceLoading: false } : e,
            ),
          );
        }
      }
    }
  }, [enriched]);

  const handleChoose = (id: string, modelId: string) => {
    onChange(id, modelId);
  };

  // The trigger names the variant only when it is not the row's primary, so
  // a single-variant key reads exactly as it did before variants existed.
  const selectedVariant =
    selected && valueModelId && userModelVariants(selected).includes(valueModelId)
      ? valueModelId
      : null;
  const selectedLabel = selected
    ? (selected.display_name || `${selected.provider_catalog_id}/${selected.model_id}`) +
      (selectedVariant && selectedVariant !== selected.model_id ? ` · ${selectedVariant}` : "")
    : triggerLabel;

  const trigger = (
    <LemonButton
      variant="secondary"
      size={size}
      className={className}
      disabled={loading || !!loadError}
      aria-label={triggerAriaLabel}
    >
      {loading ? "…" : selectedLabel}
      <span className="text-ink-mute">▾</span>
    </LemonButton>
  );

  return (
    <LemonDropdown
      trigger={trigger}
      align="below-left"
      menuClassName="min-w-[320px] max-w-[420px]"
    >
      {({ close }) => (
        <div className="py-1 text-sm">
          {loadError && (
            <div className="px-3 py-2 text-danger text-xs">
              {loadError}
            </div>
          )}
          {loading && enriched.length === 0 && (
            <div className="px-3 py-2 text-ink-mute">Loading models…</div>
          )}
          {!loading && enriched.length === 0 && (
            <div className="px-3 py-2 text-ink-soft">
              No API keys yet — connect one in Settings.
            </div>
          )}
          {includeDefault && (
            <LemonMenuItem
              onClick={() => {
                onChange("");
                close();
              }}
            >
              <div className="flex flex-col gap-0.5 w-full">
                <span className={value === "" || value == null ? "font-semibold" : ""}>
                  {defaultLabel}
                </span>
                <div className="text-xxs text-ink-mute">
                  route through the house dispatch tiers
                </div>
              </div>
            </LemonMenuItem>
          )}
          {grouped.map(({ key, label, items }) => (
            <div key={key}>
              {label !== null && (
                <div className="px-3 pt-1.5 pb-0.5 text-xxs font-mono uppercase tracking-wider text-ink-mute">
                  {label}
                </div>
              )}
              {items.map((m) => {
                const variantLabel =
                  label !== null
                    ? m.display_name !== m.model_id
                      ? m.display_name
                      : m.model_id
                    : m.display_name || m.model_id;
                const isSelected = m.id === value;
                const variants = userModelVariants(m);
                const disabled = !m.route_eligible && !m.key_present;
                // The key-level facts (usage, balance, status) render ONCE per
                // key: the ledger is keyed on the record id, so every variant
                // under it shares the same numbers.
                const keyFacts = (
                  <>
                    {showUsage && <div className="mt-0.5">{usageBar(m.usage)}</div>}
                    <div className="text-xxs text-ink-mute">
                      {m.provider_catalog_id || m.provider_kind} · {m.execution_status}
                    </div>
                  </>
                );
                const chipAndKey = (
                  <div className="flex items-center gap-2 shrink-0">
                    {showBalance && balanceChip(m.balance, m.balanceLoading)}
                    {m.key_present ? null : (
                      <span className="text-xxs text-sun-deep dark:text-sun">no key</span>
                    )}
                  </div>
                );
                if (variants.length <= 1) {
                  return (
                    <LemonMenuItem
                      key={m.id}
                      onClick={() => {
                        handleChoose(m.id, m.model_id);
                        close();
                      }}
                      disabled={disabled}
                    >
                      <div className="flex flex-col gap-0.5 w-full">
                        <div className="flex items-center justify-between gap-2">
                          <span className={isSelected ? "font-semibold" : ""}>
                            {variantLabel}
                          </span>
                          {chipAndKey}
                        </div>
                        {keyFacts}
                      </div>
                    </LemonMenuItem>
                  );
                }
                // One key, many variants: a non-clickable key header carrying
                // the shared facts, then one selectable sub-row per model_id.
                const activeVariant =
                  isSelected && valueModelId && variants.includes(valueModelId)
                    ? valueModelId
                    : isSelected
                      ? m.model_id
                      : null;
                return (
                  <div key={m.id} data-key-row={m.id}>
                    <div className="px-3 pt-1.5 pb-0.5">
                      <div className="flex items-center justify-between gap-2">
                        <span className={isSelected ? "font-semibold" : ""}>{variantLabel}</span>
                        {chipAndKey}
                      </div>
                      {keyFacts}
                    </div>
                    {variants.map((variantId) => (
                      <LemonMenuItem
                        key={`${m.id}:${variantId}`}
                        onClick={() => {
                          handleChoose(m.id, variantId);
                          close();
                        }}
                        disabled={disabled}
                      >
                        <div
                          className="flex items-center gap-2 pl-3 w-full"
                          data-variant-row={variantId}
                        >
                          <span className="text-ink-mute">↳</span>
                          <span
                            className={
                              "font-mono text-xs " +
                              (activeVariant === variantId ? "font-semibold" : "")
                            }
                          >
                            {variantId}
                          </span>
                          {variantId === m.model_id && (
                            <span className="text-xxs text-ink-mute">primary</span>
                          )}
                        </div>
                      </LemonMenuItem>
                    ))}
                  </div>
                );
              })}
            </div>
          ))}
          <div className="border-t border-edge mt-1 pt-1 px-2 flex justify-end">
            <button
              type="button"
              className="text-xxs text-ink-soft hover:text-ink px-1"
              onClick={() => void refreshBalances()}
            >
              ↻ refresh balances
            </button>
          </div>
        </div>
      )}
    </LemonDropdown>
  );
}
