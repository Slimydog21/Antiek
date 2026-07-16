import { useCallback, useEffect, useState } from "react";

import { apiFetch } from "../../lib/api";
import { emitWernerExperience } from "../../werner/reactionBus";

/**
 * ReplayStepList (S10 row 10.14) — docked-left step-pill timeline
 * sibling of the main Replay viewer.
 *
 * The main slot in `Replay/index.tsx` already renders the expanded
 * TrajectoryReplay with full event payloads. This panel surfaces a
 * compact, clickable navigation timeline: one pill per significant
 * "delivered" event (decompose, evidence, parameter, connector,
 * synthesize) so the operator can scrub quickly through long runs
 * (≥ 50 events).
 *
 * Click a pill → the main view scrolls to the anchored event id.
 * The anchor link uses `#event-<id>` which the main TrajectoryReplay
 * applies as a `data-event-id` attribute on each row.
 */
type Props = {
  investigationId?: string;
};

type StepEvent = {
  event_id: string;
  action_type: string;
  phase: number | null;
  emitted_at: string | null;
};

const SIGNIFICANT_ACTIONS = new Set([
  "decompose.delivered",
  "evidence.retrieve.delivered",
  "parameter_extract.delivered",
  "connector.delivered",
  "synthesize.delivered",
  "investigation.completed",
  "investigation.failed",
]);

export default function ReplayStepList({ investigationId }: Props) {
  const [steps, setSteps] = useState<StepEvent[]>([]);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    if (!investigationId) return;
    setLoading(true);
    try {
      const resp = await apiFetch(
        `/trajectory/${encodeURIComponent(investigationId)}`,
      );
      if (!resp.ok) {
        setError(`HTTP ${resp.status}`);
        return;
      }
      const data = await resp.json();
      const raw: Array<Record<string, unknown>> = Array.isArray(data.events)
        ? data.events
        : [];
      const filtered: StepEvent[] = raw
        .filter((e) =>
          SIGNIFICANT_ACTIONS.has(String(e.action_type ?? "")),
        )
        .map((e) => ({
          event_id: String(e.event_id ?? ""),
          action_type: String(e.action_type ?? ""),
          phase: typeof e.phase === "number" ? e.phase : null,
          emitted_at: (e.emitted_at as string | null) ?? null,
        }));
      setSteps(filtered);
      setError(null);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [investigationId]);

  useEffect(() => {
    void reload();
    const t = setInterval(() => void reload(), 5_000);
    return () => clearInterval(t);
  }, [reload]);

  if (!investigationId) {
    return (
      <div className="h-full p-3 bg-ice-0 dark:bg-charcoal-2 text-[12px] font-mono italic text-ink-mute dark:text-moonlight">
        No investigation in URL.
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col bg-ice-0 dark:bg-charcoal-2">
      <header className="px-3 py-2 flex items-center justify-between border-b border-rule dark:border-charcoal-1">
        <h3 className="text-xs font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
          Steps · {steps.length}
        </h3>
        {loading && (
          <span className="text-[10px] font-mono text-ink-mute dark:text-moonlight">
            polling…
          </span>
        )}
      </header>
      <div className="flex-1 overflow-y-auto p-2 space-y-1">
        {error && (
          <p className="text-[11px] font-mono text-emperor">{error}</p>
        )}
        {!error && steps.length === 0 && !loading && (
          <p className="text-[11px] font-mono italic text-ink-mute dark:text-moonlight">
            No significant steps yet.
          </p>
        )}
        {steps.map((s, i) => (
          <button
            type="button"
            key={s.event_id || i}
            onClick={() => {
              // TrajectoryReplay is a slider, not a scrollable list —
              // we dispatch a custom event with the target event_id;
              // the slider component listens + jumps its currentIndex.
              emitWernerExperience("highlight");
              window.dispatchEvent(
                new CustomEvent("antiek:replay:goto", {
                  detail: { eventId: s.event_id },
                }),
              );
            }}
            className={
              "block w-full text-left px-2 py-1.5 rounded text-[12px] font-mono " +
              "border border-rule dark:border-charcoal-1 " +
              "bg-ice-1 dark:bg-charcoal-2 " +
              "hover:bg-sun/15 dark:hover:bg-sun/10 transition-colors"
            }
            title={s.action_type}
          >
            <div className="flex items-baseline justify-between gap-2">
              <span className="text-ink dark:text-bright truncate">
                {prettifyAction(s.action_type)}
              </span>
              {s.phase !== null && (
                <span className="text-[10px] text-shadow-1 dark:text-moonlight shrink-0">
                  ph {s.phase}
                </span>
              )}
            </div>
            {s.emitted_at && (
              <div className="text-[10px] text-ink-mute dark:text-moonlight truncate">
                {s.emitted_at}
              </div>
            )}
          </button>
        ))}
      </div>
    </div>
  );
}

function prettifyAction(s: string): string {
  return s
    .replace(/\.delivered$/, " ✓")
    .replace(/\./g, " · ")
    .replace(/_/g, " ");
}
