/**
 * DRW SPR-09 M6 — aggregate cost meter.
 *
 * Mandatory, not optional. Shows the session's real spend against the
 * aggregate cap, straight from SPR-06's numbers — never a UI-side estimate
 * presented as actual. Warns as the cap nears and flags when it is reached
 * (the point at which the backend blocks further launches).
 */

import type { SessionCost } from "../../api/research";

const WARN_FRACTION = 0.8;

export default function CostMeter({ cost }: { cost: SessionCost | null }) {
  if (!cost) {
    return (
      <div className="text-[11px] uppercase tracking-[0.14em] text-shadow-1 dark:text-moonlight">
        cost · awaiting session
      </div>
    );
  }
  const spent = cost.aggregate_spent_usd;
  const cap = cost.aggregate_cap_usd;
  const frac = cap > 0 ? Math.min(1, spent / cap) : 0;
  const atCap = cap > 0 && spent >= cap;
  const warn = !atCap && frac >= WARN_FRACTION;
  const barColor = atCap
    ? "bg-emperor"
    : warn
      ? "bg-sun"
      : "bg-aurora";

  return (
    <div className="flex flex-col gap-1" aria-label="session cost meter">
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-[11px] uppercase tracking-[0.14em] text-shadow-1 dark:text-moonlight">
          session cost
        </span>
        <span className="font-mono text-sm text-ink dark:text-bright">
          ${spent.toFixed(4)}
          <span className="text-shadow-1 dark:text-moonlight"> / ${cap.toFixed(2)}</span>
        </span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-ice-3 dark:bg-charcoal-1">
        <div
          className={`h-full ${barColor} transition-[width] duration-300`}
          style={{ width: `${(frac * 100).toFixed(1)}%` }}
        />
      </div>
      {atCap && (
        <span className="text-[11px] text-emperor">
          Aggregate budget reached — new launches are blocked until the cap is lifted.
        </span>
      )}
      {warn && (
        <span className="text-[11px] text-shadow-1 dark:text-moonlight">
          Approaching the aggregate budget.
        </span>
      )}
    </div>
  );
}
