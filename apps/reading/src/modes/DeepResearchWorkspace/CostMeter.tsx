/**
 * DRW SPR-09 M6 — aggregate cost meter.
 *
 * Mandatory, not optional. Shows the session's real spend against the
 * aggregate cap, straight from SPR-06's numbers — never a UI-side estimate
 * presented as actual. Warns as the cap nears and flags when it is reached
 * (the point at which the backend blocks further launches).
 */

import { useEffect, useRef } from "react";

import thinkingArt from "../../brand/werner/poses/session/werner_thinking_session_v1.png";
import type { SessionCost } from "../../api/research";
import { emitWernerExperience } from "../../werner/reactionBus";

const WARN_FRACTION = 0.8;

/** Pure policy: budget bar living-TV beat for a spend snapshot. */
export function costMeterWernerBeat(input: {
  spent: number;
  cap: number;
  warnFraction?: number;
}): "fail" | "highlight" | null {
  const { spent, cap, warnFraction = WARN_FRACTION } = input;
  if (!(cap > 0) || !Number.isFinite(spent) || !Number.isFinite(cap)) return null;
  if (spent >= cap) return "fail";
  if (spent / cap >= warnFraction) return "highlight";
  return null;
}

export default function CostMeter({ cost }: { cost: SessionCost | null }) {
  const lastBeat = useRef<string | null>(null);

  useEffect(() => {
    if (!cost) return;
    const beat = costMeterWernerBeat({
      spent: cost.aggregate_spent_usd,
      cap: cost.aggregate_cap_usd,
    });
    if (!beat || beat === lastBeat.current) return;
    lastBeat.current = beat;
    emitWernerExperience(beat);
  }, [cost]);

  if (!cost) {
    return (
      <div
        className="flex items-center gap-2 text-[11px] uppercase tracking-[0.14em] text-shadow-1 dark:text-moonlight"
        data-testid="cost-meter-awaiting"
      >
        <img
          src={thinkingArt}
          alt=""
          aria-hidden="true"
          data-testid="cost-meter-werner-brand"
          className="h-5 w-5 object-contain opacity-80"
        />
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
    <div
      className="flex flex-col gap-1"
      aria-label="session cost meter"
      data-testid="cost-meter"
      data-at-cap={atCap ? "true" : "false"}
      data-warn={warn ? "true" : "false"}
    >
      <div className="flex items-baseline justify-between gap-3">
        <span className="flex items-center gap-1.5 text-[11px] uppercase tracking-[0.14em] text-shadow-1 dark:text-moonlight">
          <img
            src={thinkingArt}
            alt=""
            aria-hidden="true"
            data-testid="cost-meter-werner-brand"
            className="h-5 w-5 object-contain"
          />
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
