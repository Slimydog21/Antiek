import { useCallback, useEffect, useRef, useState } from "react";
import type { OwnerModelUsagePickerProps } from "./OwnerModelUsagePicker";
import ModelUsagePickerView, {
  type ModelUsagePickerRow,
} from "./ModelUsagePickerView";
import { modelUsageReadQueue } from "./modelUsageReadQueue";
import { balanceLabel, usageBadge } from "./usageLabels";
import {
  fetchSettingsBalance,
  fetchSettingsUsage,
  type SettingsBalanceResponse,
  type SettingsUsageKeyEntry,
} from "../../api/settingsUsage";
import type {
  InventoryRow,
  ModelInventory,
  OwnerModelController,
} from "../../hooks/useOwnerModelController";
type ReadyInventory = Extract<ModelInventory, { kind: "ready" }>;
type BalanceRead =
  | { kind: "loading" | "failed" }
  | { kind: "ready"; value: SettingsBalanceResponse };
type UsageRead =
  | { kind: "loading" | "failed" }
  | { kind: "ready"; values: ReadonlyMap<string, SettingsUsageKeyEntry> };
interface Cycle {
  snapshot: ReadyInventory;
  live: boolean;
  seen: Set<string>;
  isCurrent(): boolean;
}
interface Metrics {
  cycle: Cycle;
  usage: UsageRead;
  balances: ReadonlyMap<string, BalanceRead>;
  receivedAt: number | null;
}
const alwaysCurrent = () => true;
const executable = (row: ModelUsagePickerRow) =>
  row.enabled &&
  row.key_present &&
  row.registered &&
  row.route_eligible &&
  row.pricing_status === "known" &&
  row.hard_ceiling_eligible &&
  row.execution_status === "executable";
type PickerPresentation = Pick<
  Parameters<typeof ModelUsagePickerView>[0],
  | "rows"
  | "value"
  | "valueModelId"
  | "loading"
  | "loadError"
  | "triggerLabel"
  | "defaultSelected"
  | "includeDefault"
>;
function pickerPresentation({
  inventory,
  selection,
  resourceAvailable,
  inventoryCurrent,
  allowHouse,
}: {
  inventory: ModelInventory;
  selection: OwnerModelController["selection"];
  resourceAvailable: boolean;
  inventoryCurrent: boolean;
  allowHouse: boolean;
}): PickerPresentation {
  if (!resourceAvailable) {
    return {
      rows: [],
      value: null,
      valueModelId: null,
      loading: false,
      loadError: "Resource unavailable",
      triggerLabel: "Resource unavailable",
      defaultSelected: false,
      includeDefault: false,
    };
  }
  const selected = selection.kind === "saved" ? selection : null;
  const house = selection.kind === "house";
  return {
    rows: inventory.kind === "ready" && inventoryCurrent ? inventory.rows : [],
    value: selected?.recordId ?? (house ? "" : null),
    valueModelId: selected?.modelId ?? null,
    loading: inventory.kind === "loading" || inventory.kind === "suspended",
    loadError: inventory.kind === "failed" ? "Your models couldn’t load." : null,
    triggerLabel: house
      ? "Default (house route)"
      : selection.kind === "unavailable"
        ? `Selected model unavailable · ${selection.modelId}`
        : "Choose model",
    defaultSelected: house,
    includeDefault: allowHouse,
  };
}
export default function OwnerModelUsagePickerImpl({
  controller,
  triggerAriaLabel = "Model",
  allowHouse,
  isResourceCurrent = alwaysCurrent,
}: OwnerModelUsagePickerProps) {
  const { inventory, selection, isInventoryCurrent } = controller;
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const cycleRef = useRef<Cycle | null>(null);
  const allOnNextReadyRef = useRef<{
    scope: ReadyInventory["scope"];
    isResourceCurrent: () => boolean;
  } | null>(null);
  const update = useCallback(
    (cycle: Cycle, change: (previous: Metrics) => Metrics) => {
      if (!cycle.isCurrent()) return;
      setMetrics((previous) =>
        previous?.cycle === cycle && cycle.isCurrent()
          ? change(previous)
          : previous,
      );
    },
    [],
  );
  const enqueue = useCallback(
    (cycle: Cycle, rows: readonly InventoryRow[]) => {
      for (const row of rows) {
        if (!cycle.isCurrent()) return;
        if (!row.key_present || cycle.seen.has(row.id)) continue;
        cycle.seen.add(row.id);
        update(cycle, (previous) => ({
          ...previous,
          balances: new Map(previous.balances).set(row.id, { kind: "loading" }),
        }));
        modelUsageReadQueue.enqueue({
          isCurrent: cycle.isCurrent,
          run: async () => {
            if (!cycle.isCurrent()) return;
            try {
              const value = await fetchSettingsBalance(row.id);
              if (!cycle.isCurrent()) return;
              const bound =
                value.api_key_id === row.id &&
                value.catalog_id === (row.provider_catalog_id ?? "unknown");
              update(cycle, (previous) => ({
                ...previous,
                balances: new Map(previous.balances).set(
                  row.id,
                  bound ? { kind: "ready", value } : { kind: "failed" },
                ),
                receivedAt: Date.now(),
              }));
            } catch {
              update(cycle, (previous) => ({
                ...previous,
                balances: new Map(previous.balances).set(row.id, {
                  kind: "failed",
                }),
              }));
            }
          },
        });
      }
    },
    [update],
  );
  useEffect(() => {
    if (
      !isResourceCurrent() ||
      inventory.kind !== "ready" ||
      !isInventoryCurrent(inventory)
    ) {
      cycleRef.current = null;
      setMetrics(null);
      return;
    }
    const cycle: Cycle = {
      snapshot: inventory,
      live: true,
      seen: new Set(),
      isCurrent: () =>
        cycle.live && isResourceCurrent() && isInventoryCurrent(inventory),
    };
    cycleRef.current = cycle;
    setMetrics({
      cycle,
      usage: { kind: "loading" },
      balances: new Map(),
      receivedAt: null,
    });
    void (async () => {
      if (!cycle.isCurrent()) return;
      try {
        const result = await fetchSettingsUsage();
        if (!cycle.isCurrent()) return;
        const ids = new Set(inventory.rows.map((row) => row.id));
        // Owner usage history can outlive a deleted model registration.
        // Validate uniqueness across the response, then join only current keys.
        const valid =
          new Set(result.keys.map((entry) => entry.api_key_id)).size ===
          result.keys.length;
        const values = new Map(
          result.keys
            .filter((entry) => ids.has(entry.api_key_id))
            .map((entry) => [entry.api_key_id, entry]),
        );
        update(cycle, (previous) => ({
          ...previous,
          usage: valid ? { kind: "ready", values } : { kind: "failed" },
          receivedAt: Date.now(),
        }));
      } catch {
        update(cycle, (previous) => ({
          ...previous,
          usage: { kind: "failed" },
        }));
      }
    })();
    const refreshIntent = allOnNextReadyRef.current;
    const all =
      refreshIntent?.scope === inventory.scope &&
      refreshIntent.isResourceCurrent === isResourceCurrent &&
      refreshIntent.isResourceCurrent();
    allOnNextReadyRef.current = null;
    enqueue(
      cycle,
      all
        ? inventory.rows
        : inventory.rows.filter((row) => row.key_present).slice(0, 6),
    );
    return () => {
      cycle.live = false;
      if (cycleRef.current === cycle) cycleRef.current = null;
    };
  }, [inventory, isInventoryCurrent, isResourceCurrent, enqueue, update]);
  const onMenuMount = useCallback(() => {
    const cycle = metrics?.cycle;
    if (cycle?.isCurrent()) enqueue(cycle, cycle.snapshot.rows);
  }, [enqueue, metrics?.cycle]);
  const refresh = useCallback(async () => {
    if (
      !isResourceCurrent() ||
      inventory.kind === "suspended" ||
      !isInventoryCurrent(inventory)
    )
      return;
    allOnNextReadyRef.current = { scope: inventory.scope, isResourceCurrent };
    await controller.refresh();
  }, [controller, inventory, isInventoryCurrent, isResourceCurrent]);
  const resourceAvailable = isResourceCurrent();
  const current =
    resourceAvailable && metrics?.cycle.isCurrent() ? metrics : null;
  const presentation = pickerPresentation({
    inventory,
    selection,
    resourceAvailable,
    inventoryCurrent: isInventoryCurrent(inventory),
    allowHouse,
  });
  return (
    <div className="flex flex-wrap items-center gap-2">
      <ModelUsagePickerView
        {...presentation}
        triggerAriaLabel={triggerAriaLabel}
        size="sm"
        defaultLabel="Default (house route)"
        isRowDisabled={(row) => !executable(row)}
        onChange={(id, modelId) => {
          if (
            !isResourceCurrent() ||
            inventory.kind !== "ready" ||
            !isInventoryCurrent(inventory)
          )
            return;
          if (id === "") controller.select({ kind: "house" });
          else if (modelId)
            controller.select({ kind: "saved", recordId: id, modelId });
        }}
        onMenuMount={onMenuMount}
        onRefresh={refresh}
        renderUsage={(row) => {
          const usage = current?.usage;
          const entry =
            usage?.kind === "ready" ? usage.values.get(row.id) : undefined;
          return (
            <span className="text-xxs text-ink-mute">
              {entry
                ? usageBadge(entry)
                : usage?.kind === "loading"
                  ? "Usage loading…"
                  : usage?.kind === "failed"
                    ? "Usage unavailable"
                    : "Usage unavailable (no entry)"}
            </span>
          );
        }}
        renderBalance={(row) => {
          const read = current?.balances.get(row.id);
          const label =
            read?.kind === "ready" ? balanceLabel(read.value) : null;
          return (
            <span
              className="text-xxs tabular-nums"
              data-balance-kind={
                read?.kind === "ready" && label?.tone === "ok"
                  ? read.value.kind
                  : undefined
              }
              title={label?.text}
            >
              {label?.text ??
                (read?.kind === "loading"
                  ? "Balance loading…"
                  : read?.kind === "failed"
                    ? "Provider balance unavailable"
                    : "Balance not requested")}
            </span>
          );
        }}
      />
      <button
        type="button"
        className="text-xxs text-ink-soft"
        aria-label="Refresh model usage"
        disabled={
          !resourceAvailable ||
          inventory.kind === "suspended" ||
          inventory.kind === "loading"
        }
        onClick={() => void refresh()}
      >
        ↻ refresh usage
      </button>
      {current?.receivedAt && (
        <span
          className="text-xxs text-ink-mute"
          title="Local response received time; not provider as-of"
        >
          received {new Date(current.receivedAt).toLocaleTimeString()}
        </span>
      )}
    </div>
  );
}
