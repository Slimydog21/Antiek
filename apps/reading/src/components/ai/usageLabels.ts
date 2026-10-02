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
  if (balance.kind === "unavailable") {
    return { text: "Provider balance unavailable", tone: "unknown" };
  }
  if (balance.kind === "spend_history") {
    if (balance.note === "no usage recorded for this key") {
      return {
        text: "Antiek meter: no usage recorded (not provider credit)",
        tone: "unknown",
      };
    }
    const spend =
      typeof balance.spend_usd === "number" && Number.isFinite(balance.spend_usd)
        ? balance.spend_usd
        : null;
    const budget =
      typeof balance.budget_usd === "number" && Number.isFinite(balance.budget_usd)
        ? balance.budget_usd
        : null;
    if (spend === null) {
      return { text: "Antiek meter unavailable (not provider credit)", tone: "unknown" };
    }
    if (budget === null) {
      return {
        text: `Antiek meter: spent ${formatUsd(spend)}, uncapped (not provider credit)`,
        tone: "ok",
      };
    }
    return {
      text: `Antiek meter: ${formatUsd(spend)} settled of ${formatUsd(budget)} cap; holds excluded (not provider credit)`,
      tone: "ok",
    };
  }
  if (balance.catalog_id === "deepseek" && balance.kind === "balance_native") {
    const entries = balance.native_balances;
    return entries && entries.length > 0
      ? {
          text: `Provider-reported balance: ${entries.map(({ currency, total }) => `${currency} ${total}`).join(" · ")}${balance.native_available === false ? " · insufficient for API calls" : ""}`,
          tone: balance.native_available === false ? "unknown" : "ok",
        }
      : { text: "Provider balance unavailable", tone: "unknown" };
  }
  if (
    balance.kind === "balance_native" &&
    typeof balance.balance_usd === "number" &&
    Number.isFinite(balance.balance_usd)
  ) {
    return {
      text: `Provider-reported balance ${formatNativeUsd(balance.balance_usd)}${balance.native_available === false ? " · insufficient for API calls" : ""}`,
      tone: balance.native_available === false ? "unknown" : "ok",
    };
  }
  if (
    balance.kind === "quota_pct" &&
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
  return { text: "Provider balance unavailable", tone: "unknown" };
}
