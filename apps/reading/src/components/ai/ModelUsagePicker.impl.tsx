import { useCallback, useEffect, useState } from "react";

import ModelUsagePickerView from "./ModelUsagePickerView";
import { fetchUserModels, type UserModelRow } from "../../api/settingsModels";
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
        models
          ? Promise.resolve({ models, count: models.length })
          : fetchUserModels(),
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
                  e.id === m.id
                    ? { ...e, balance: bal, balanceLoading: false }
                    : e,
                ),
              );
            })
            .catch(() => {
              setEnriched((prev) =>
                prev.map((e) =>
                  e.id === m.id
                    ? { ...e, balance: null, balanceLoading: false }
                    : e,
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
              e.id === m.id
                ? { ...e, balance: null, balanceLoading: false }
                : e,
            ),
          );
        }
      }
    }
  }, [enriched]);

  return (
    <ModelUsagePickerView
      rows={enriched}
      value={value}
      valueModelId={valueModelId}
      onChange={onChange}
      loading={loading}
      loadError={loadError}
      triggerLabel={triggerLabel}
      triggerAriaLabel={triggerAriaLabel}
      size={size}
      className={className}
      showUsage={showUsage}
      showBalance={showBalance}
      includeDefault={includeDefault}
      defaultLabel={defaultLabel}
      onRefresh={refreshBalances}
    />
  );
}
