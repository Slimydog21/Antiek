import { useEffect, useMemo, useRef, useState } from "react";

import livingTvArt from "../../brand/werner/poses/session/werner_living_tv_session_v1.webp";
import type { Event } from "../../generated/types";
import type { InvestigationState } from "../../hooks/useInvestigation";
import { emitWernerExperience } from "../../werner/reactionBus";
import PhaseRow from "./PhaseRow";

/**
 * Live trajectory rendering for an investigation in flight.
 *
 * Renders one PhaseRow per substantive event, with phase-enter rollups
 * (e.g. "Phase 1 · Orientation") interleaved as section headers. Auto-
 * scrolls to bottom on each new event so the live tail stays visible.
 *
 * Dispatch.call events are toggleable as a group: showing every one
 * makes the feed too noisy, but the operator wants the option to
 * inspect them for cost auditing.
 *
 * Transitions to MasterMdViewer happen at the parent component level
 * (ResearchWorkstation/InvestigationCenter) on investigation.completed.
 */
export default function TrajectoryView({
  investigation,
}: {
  investigation: InvestigationState;
}) {
  const [showDispatches, setShowDispatches] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const lastStatusBeat = useRef<string | null>(null);

  // Living-TV: terminal status transitions on the raw trajectory surface.
  useEffect(() => {
    const status = investigation.status;
    if (status === lastStatusBeat.current) return;
    if (status === "completed") {
      lastStatusBeat.current = status;
      emitWernerExperience("deep_research_complete");
    } else if (status === "failed" || status === "not_found") {
      lastStatusBeat.current = status;
      emitWernerExperience("deep_research_error");
    }
  }, [investigation.status]);

  const filteredEvents = useMemo(() => {
    if (showDispatches) return investigation.events;
    return investigation.events.filter((e) => e.action_type !== "dispatch.call");
  }, [investigation.events, showDispatches]);

  // Auto-scroll on new event arrival.
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [filteredEvents.length]);

  const groups = useMemo(() => groupByPhase(filteredEvents), [filteredEvents]);

  return (
    <div className="flex flex-col h-full min-h-0">
      <TrajectoryHeader
        investigation={investigation}
        showDispatches={showDispatches}
        onToggleDispatches={() => setShowDispatches((v) => !v)}
      />
      <img
        src={livingTvArt}
        alt=""
        aria-hidden="true"
        data-testid="trajectory-living-tv-art"
        className="mx-4 mt-2 h-10 max-w-xs rounded object-cover object-center antiek-living-tv-invent"
        loading="lazy"
        decoding="async"
      />
      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto px-4 py-3 space-y-4"
      >
        {groups.length === 0 && (
          <div className="text-sm text-ink-mute dark:text-moonlight italic font-serif">
            Waiting for first phase to begin…
          </div>
        )}
        {groups.map((g) => (
          <div key={g.phase} className="space-y-2">
            <div className="text-[10px] font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight border-b border-rule dark:border-charcoal-1 pb-1">
              Phase {g.phase}{g.label ? ` · ${g.label}` : ""}
            </div>
            {g.events.map((e) => (
              <PhaseRow key={e.event_id ?? Math.random()} event={e} />
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

function TrajectoryHeader({
  investigation,
  showDispatches,
  onToggleDispatches,
}: {
  investigation: InvestigationState;
  showDispatches: boolean;
  onToggleDispatches: () => void;
}) {
  return (
    <div className="px-4 py-2 border-b border-rule dark:border-charcoal-1 bg-ice-1 dark:bg-charcoal-2 flex items-center justify-between text-xs font-mono">
      <div className="flex items-center gap-3">
        <span
          className={`uppercase tracking-wider ${
            investigation.status === "in_progress"
              ? "text-sun-deep dark:text-sun"
              : investigation.status === "completed"
                ? "text-emerald-700"
                : investigation.status === "failed"
                  ? "text-emperor"
                  : "text-shadow-1 dark:text-moonlight"
          }`}
        >
          {investigation.status === "loading" ? "loading…" : investigation.status}
        </span>
        <span className="text-ink-mute dark:text-moonlight">·</span>
        <span className="text-ink-soft dark:text-starlight">
          ${investigation.costTotal.toFixed(4)}
        </span>
        <span className="text-ink-mute dark:text-moonlight">·</span>
        <span className="text-shadow-1 dark:text-moonlight">
          {investigation.events.length} events
        </span>
      </div>
      <button
        onClick={onToggleDispatches}
        className="text-shadow-1 dark:text-moonlight hover:text-ink dark:text-bright transition-colors"
      >
        {showDispatches ? "hide LLM calls" : "show LLM calls"}
      </button>
    </div>
  );
}

// ── Phase grouping ───────────────────────────────────────────────────

interface PhaseGroup {
  phase: number;
  label: string | null;
  events: Event[];
}

const PHASE_LABELS: Record<number, string> = {
  1: "Orientation + decomposition",
  2: "Evidence round 1",
  3: "Parameter extraction",
  4: "Cross-domain connection",
  5: "Synthesis",
  6: "Constraint loop",
  7: "Synthesis archive",
  8: "Compounding",
};

function groupByPhase(events: Event[]): PhaseGroup[] {
  // Use the event envelope's `phase` field. Events without a phase tag
  // (e.g. investigation.start_requested) are bucketed into phase 0.
  const buckets = new Map<number, Event[]>();
  for (const e of events) {
    const phase = (e.phase ?? 0) as number;
    if (!buckets.has(phase)) buckets.set(phase, []);
    buckets.get(phase)!.push(e);
  }
  return Array.from(buckets.entries())
    .sort(([a], [b]) => a - b)
    .map(([phase, events]) => ({
      phase,
      label: PHASE_LABELS[phase] ?? null,
      events,
    }));
}
