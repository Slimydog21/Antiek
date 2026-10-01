import type {
  SettingsBalanceResponse,
  SettingsUsageKeyEntry,
} from "../../api/settingsUsage";
function formatCents(value: number | null): string {
  if (value == null) return "unknown";
  return `$${(value / 100).toFixed(2)}`;
}
function formatUsd(value: number): string {
  return `$${value.toFixed(2)}`;
}
// Exact numeric presentation from the held native-precision successor. Current
// API exposes numeric USD only; native currency strings require later composition.
function formatNativeUsd(value: number): string {
  const amount = String(value);
  if (amount.includes("e")) return `$${amount}`;
  const [whole, fraction = ""] = amount.split(".");
  return `$${whole}.${fraction.padEnd(2, "0")}`;
}
export function usageBadge(entry: SettingsUsageKeyEntry): string {
  return `used ${formatCents(entry.used_cents)} · cap ${entry.limit_cents === null ? "uncapped" : formatCents(entry.limit_cents)} · remaining ${formatCents(entry.remaining_cents)} · held ${formatCents(entry.held_cents)} · available ${formatCents(entry.available_cents)}`;
}
export function balanceLabel(balance: SettingsBalanceResponse): {
  text: string;
  tone: "ok" | "unknown";
} {
  if (balance.kind === "spend_history") {
    if (balance.note === "no usage recorded for this key")
      return {
        text: "Antiek meter: no usage recorded (not provider credit)",
        tone: "unknown",
      };
    if (balance.spend_usd === null)
      return {
        text: "Antiek meter unavailable (not provider credit)",
        tone: "unknown",
      };
    return {
      text:
        balance.budget_usd === null
          ? `Antiek meter: spent ${formatUsd(balance.spend_usd)}, uncapped (not provider credit)`
          : `Antiek meter: ${formatUsd(balance.spend_usd)} settled of ${formatUsd(balance.budget_usd)} cap; holds excluded (not provider credit)`,
      tone: "ok",
    };
  }
  if (balance.kind === "balance_native" && balance.balance_usd !== null)
    return {
      text: `Provider-reported credit ${formatNativeUsd(balance.balance_usd)}`,
      tone: "ok",
    };
  if (
    balance.kind === "quota_pct" &&
    balance.utilization !== null &&
    balance.utilization >= 0 &&
    balance.utilization <= 1
  )
    return {
      text: `Quota remaining ${Math.max(0, (1 - balance.utilization) * 100).toFixed(1)}%`,
      tone: "ok",
    };
  return { text: "Provider balance unavailable", tone: "unknown" };
}
