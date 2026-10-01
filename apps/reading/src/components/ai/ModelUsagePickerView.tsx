import { useEffect, useMemo, type ReactNode } from "react";
import { LemonButton } from "../lemon";
import { LemonDropdown, LemonMenuItem } from "../lemon/LemonDropdown";
import type { UserModelRow } from "../../api/settingsModels";
import type {
  SettingsUsageKeyEntry,
  SettingsBalanceResponse,
} from "../../api/settingsUsage";
export type ModelUsagePickerRow = Readonly<Omit<UserModelRow, "model_ids">> & {
  readonly model_ids?: readonly string[];
  usage?: SettingsUsageKeyEntry;
  balance?: SettingsBalanceResponse | null;
  balanceLoading?: boolean;
};
interface ViewProps {
  rows: readonly ModelUsagePickerRow[];
  value: string | null;
  valueModelId?: string | null;
  onChange: (id: string, modelId?: string) => void;
  loading: boolean;
  loadError: string | null;
  triggerLabel?: string;
  triggerAriaLabel?: string;
  size?: "sm" | "md";
  className?: string;
  showUsage?: boolean;
  showBalance?: boolean;
  includeDefault?: boolean;
  defaultLabel?: string;
  defaultSelected?: boolean;
  onRefresh: () => void | Promise<void>;
  onMenuMount?: () => void;
  renderUsage?: (row: ModelUsagePickerRow) => ReactNode;
  renderBalance?: (row: ModelUsagePickerRow) => ReactNode;
  isRowDisabled?: (row: ModelUsagePickerRow) => boolean;
}
function MenuMount({
  onMount,
  children,
}: {
  onMount?: () => void;
  children: ReactNode;
}) {
  useEffect(() => {
    onMount?.();
  }, [onMount]);
  return <>{children}</>;
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
          className={"h-full " + (over ? "bg-danger" : "bg-sun")}
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
function balanceChip(
  b?: SettingsBalanceResponse | null,
  loading?: boolean,
): React.ReactNode {
  if (loading) return <span className="text-xxs text-ink-mute">…</span>;
  if (!b || b.kind === "unavailable") {
    return (
      <span
        className="text-xxs text-ink-mute dark:text-moonlight"
        title={b?.note || undefined}
      >
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

/** Shared presentation only: data authority and scheduling belong to its caller. */
export default function ModelUsagePickerView({
  rows: enriched,
  value,
  valueModelId = null,
  onChange,
  loading,
  loadError,
  triggerLabel = "Model",
  triggerAriaLabel,
  size = "md",
  className = "",
  showUsage = true,
  showBalance = true,
  includeDefault = false,
  defaultLabel = "Default (house route)",
  onRefresh,
  onMenuMount,
  defaultSelected,
  renderUsage,
  renderBalance,
  isRowDisabled,
}: ViewProps) {
  // Variant grouping: registrations of the SAME provider (e.g. DeepSeek
  // V4 Pro + V4 Flash from one key) render under one provider header with
  // model_id as the variant label. Singletons render flat (display_name).
  const grouped = useMemo(() => {
    const byProvider = new Map<string, ModelUsagePickerRow[]>();
    for (const m of enriched) {
      const key = m.provider_catalog_id || m.provider_kind;
      const bucket = byProvider.get(key) ?? [];
      bucket.push(m);
      byProvider.set(key, bucket);
    }
    const groups: {
      key: string;
      label: string | null;
      items: ModelUsagePickerRow[];
    }[] = [];
    for (const [key, items] of byProvider) {
      groups.push({ key, label: items.length > 1 ? key : null, items });
    }
    return groups;
  }, [enriched]);

  const selected = useMemo(
    () => enriched.find((e) => e.id === value) ?? null,
    [enriched, value],
  );

  // The trigger names the variant only when it is not the row's primary, so
  // a single-variant key reads exactly as it did before variants existed.
  const selectedVariant =
    selected &&
    valueModelId &&
    (selected.model_ids ?? [selected.model_id]).includes(valueModelId)
      ? valueModelId
      : null;
  const selectedLabel = selected
    ? (selected.display_name ||
        `${selected.provider_catalog_id}/${selected.model_id}`) +
      (selectedVariant && selectedVariant !== selected.model_id
        ? ` · ${selectedVariant}`
        : "")
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
        <MenuMount onMount={onMenuMount}>
          <div className="py-1 text-sm">
            {loadError && (
              <div className="px-3 py-2 text-danger text-xs">{loadError}</div>
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
                  <span
                    className={
                      (defaultSelected ?? (value === "" || value == null))
                        ? "font-semibold"
                        : ""
                    }
                  >
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
                  const variants = m.model_ids ?? [m.model_id];
                  const disabled = isRowDisabled
                    ? isRowDisabled(m)
                    : !m.route_eligible && !m.key_present;
                  // The key-level facts (usage, balance, status) render ONCE per
                  // key: the ledger is keyed on the record id, so every variant
                  // under it shares the same numbers.
                  const keyFacts = (
                    <>
                      {showUsage && (
                        <div className="mt-0.5">
                          {renderUsage ? renderUsage(m) : usageBar(m.usage)}
                        </div>
                      )}
                      <div className="text-xxs text-ink-mute">
                        {m.provider_catalog_id || m.provider_kind} ·{" "}
                        {m.execution_status}
                      </div>
                    </>
                  );
                  const chipAndKey = (
                    <div className="flex items-center gap-2 shrink-0">
                      {showBalance &&
                        (renderBalance
                          ? renderBalance(m)
                          : balanceChip(m.balance, m.balanceLoading))}
                      {m.key_present ? null : (
                        <span className="text-xxs text-sun-deep dark:text-sun">
                          no key
                        </span>
                      )}
                    </div>
                  );
                  if (variants.length <= 1) {
                    return (
                      <LemonMenuItem
                        key={m.id}
                        onClick={() => {
                          onChange(m.id, m.model_id);
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
                    isSelected &&
                    valueModelId &&
                    variants.includes(valueModelId)
                      ? valueModelId
                      : isSelected
                        ? m.model_id
                        : null;
                  return (
                    <div key={m.id} data-key-row={m.id}>
                      <div className="px-3 pt-1.5 pb-0.5">
                        <div className="flex items-center justify-between gap-2">
                          <span className={isSelected ? "font-semibold" : ""}>
                            {variantLabel}
                          </span>
                          {chipAndKey}
                        </div>
                        {keyFacts}
                      </div>
                      {variants.map((variantId) => (
                        <LemonMenuItem
                          key={`${m.id}:${variantId}`}
                          onClick={() => {
                            onChange(m.id, variantId);
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
                                (activeVariant === variantId
                                  ? "font-semibold"
                                  : "")
                              }
                            >
                              {variantId}
                            </span>
                            {variantId === m.model_id && (
                              <span className="text-xxs text-ink-mute">
                                primary
                              </span>
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
                onClick={() => void onRefresh()}
              >
                ↻ refresh balances
              </button>
            </div>
          </div>
        </MenuMount>
      )}
    </LemonDropdown>
  );
}
