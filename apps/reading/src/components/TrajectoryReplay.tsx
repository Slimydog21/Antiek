import { useEffect, useMemo, useRef, useState } from "react";

import type { Event } from "../generated/types";
import { emitWernerExperience } from "../werner/reactionBus";

interface Props {
  events: Event[];
  /** Optional override for autoplay speed in events per second. */
  playSpeed?: number;
}

/**
 * Trajectory replay viewer (PostHog Wedge 5 in spirit, master-spec §14.1).
 *
 * Timeline scrubber + event-at-time renderer for re-reading
 * investigation trajectories. Required for accurate operator-graded
 * outcomes (which gates autoresearch Wedge 3 config sweeps per
 * §14.2).
 *
 * Does NOT vendor rrweb (Antiek records typed events, not DOM —
 * §12.8 REJECT). Borrows the rrweb concept: timeline + frame
 * renderer + playback controls.
 */
export default function TrajectoryReplay({ events, playSpeed = 2 }: Props) {
  const [currentIndex, setCurrentIndex] = useState<number>(0);
  const [playing, setPlaying] = useState<boolean>(false);
  const intervalRef = useRef<number | null>(null);

  const sortedEvents = useMemo(() => {
    return [...events].sort((a, b) => {
      const ta = a.emitted_at ?? "";
      const tb = b.emitted_at ?? "";
      return ta < tb ? -1 : ta > tb ? 1 : 0;
    });
  }, [events]);

  const total = sortedEvents.length;
  const currentEvent = currentIndex < total ? sortedEvents[currentIndex] : null;

  useEffect(() => {
    if (!playing || total === 0) {
      if (intervalRef.current !== null) {
        window.clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
      return;
    }
    const tickMs = Math.max(50, Math.floor(1000 / playSpeed));
    intervalRef.current = window.setInterval(() => {
      setCurrentIndex((idx) => {
        if (idx + 1 >= total) {
          setPlaying(false);
          return idx;
        }
        return idx + 1;
      });
    }, tickMs);
    return () => {
      if (intervalRef.current !== null) {
        window.clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [playing, playSpeed, total]);

  // S10 row 10.14 — Replay step-list panel dispatches `antiek:replay:goto`
  // with an event_id when the operator clicks a step pill. We listen +
  // jump the slider to that index. Pauses playback so the operator
  // can read at their own pace.
  useEffect(() => {
    const onGoto = (e: globalThis.Event) => {
      const ce = e as CustomEvent<{ eventId?: string }>;
      const eid = ce.detail?.eventId;
      if (!eid) return;
      const idx = sortedEvents.findIndex((evt) => evt.event_id === eid);
      if (idx >= 0) {
        setPlaying(false);
        setCurrentIndex(idx);
      }
    };
    window.addEventListener("antiek:replay:goto", onGoto);
    return () => window.removeEventListener("antiek:replay:goto", onGoto);
  }, [sortedEvents]);

  if (total === 0) {
    return (
      <div className="px-4 py-3 text-xs text-shadow-1 dark:text-moonlight italic">
        No events in this trajectory yet.
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3 px-4 py-3">
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={() => {
            setPlaying((p) => {
              // Living-TV: replay play starts thinking beat; pause is quiet.
              if (!p) emitWernerExperience("deep_research_start");
              return !p;
            });
          }}
          className="px-2.5 py-1 rounded-md bg-ink text-white text-xs font-medium hover:bg-shadow-2 transition-colors"
        >
          {playing ? "Pause" : "Play"}
        </button>
        <button
          type="button"
          onClick={() => {
            setCurrentIndex(0);
            emitWernerExperience("highlight");
          }}
          className="text-xs text-shadow-1 dark:text-moonlight hover:text-ink dark:text-bright"
        >
          ⏮ Restart
        </button>
        <span className="text-xs font-mono text-shadow-1 dark:text-moonlight">
          {currentIndex + 1} / {total}
        </span>
      </div>

      <input
        type="range"
        min={0}
        max={Math.max(0, total - 1)}
        value={currentIndex}
        onChange={(e) => {
          setPlaying(false);
          setCurrentIndex(Number(e.target.value));
        }}
        className="w-full"
      />

      {currentEvent && <EventFrame event={currentEvent} />}
    </div>
  );
}

function EventFrame({ event }: { event: Event }) {
  return (
    <div className="border border-rule dark:border-charcoal-1 rounded-md px-3 py-2 bg-ice-0 dark:bg-charcoal-2">
      <p className="text-xs font-mono text-shadow-1 dark:text-moonlight mb-1">
        {event.emitted_at} · {event.role ?? "?"} · {event.action_type}
      </p>
      <p className="text-xs font-mono text-ink-mute dark:text-moonlight mb-2">
        event_id: {event.event_id}
      </p>
      <pre className="text-xs font-mono text-ink dark:text-bright whitespace-pre-wrap break-words max-h-64 overflow-y-auto">
        {JSON.stringify(event.payload, null, 2)}
      </pre>
    </div>
  );
}
