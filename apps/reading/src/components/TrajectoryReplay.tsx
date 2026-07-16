import { useEffect, useMemo, useRef, useState } from "react";

import type { Event } from "../generated/types";

interface Props {
  events: Event[];
  /** Optional override for autoplay speed in events per second. */
  playSpeed?: number;
}

/** Existing replay chronology: emitted_at ascending, stable for equal timestamps. */
export function orderTrajectoryEvents(events: Event[]): Event[] {
  return [...events].sort((a, b) => {
    const ta = a.emitted_at ?? "";
    const tb = b.emitted_at ?? "";
    return ta < tb ? -1 : ta > tb ? 1 : 0;
  });
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
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null);
  const [playing, setPlaying] = useState<boolean>(false);
  const intervalRef = useRef<number | null>(null);

  const sortedEvents = useMemo(() => {
    return orderTrajectoryEvents(events);
  }, [events]);

  const total = sortedEvents.length;
  const sortedEventsRef = useRef(sortedEvents);
  const selectedIndex = selectedEventId
    ? sortedEvents.findIndex((event) => event.event_id === selectedEventId)
    : -1;
  const resolvedIndex = selectedIndex >= 0 ? selectedIndex : 0;
  const currentEvent = resolvedIndex < total ? sortedEvents[resolvedIndex] : null;

  useEffect(() => {
    sortedEventsRef.current = sortedEvents;
  }, [sortedEvents]);

  useEffect(() => {
    if (selectedIndex < 0) {
      setSelectedEventId(sortedEvents[0]?.event_id ?? null);
    }
  }, [selectedIndex, sortedEvents]);

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
      setSelectedEventId((currentId) => {
        const currentEvents = sortedEventsRef.current;
        const currentIndex = currentEvents.findIndex((event) => event.event_id === currentId);
        const nextIndex = Math.max(0, currentIndex) + 1;
        if (nextIndex >= currentEvents.length) {
          setPlaying(false);
          return currentId;
        }
        return currentEvents[nextIndex]?.event_id ?? currentId;
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
        setSelectedEventId(eid);
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
    <div className="trajectory-player">
      <div className="trajectory-player__controls">
        <button
          type="button"
          onClick={() => setPlaying((p) => !p)}
          className="trajectory-player__play"
          aria-pressed={playing}
        >
          {playing ? "Pause" : "Play"}
        </button>
        <button
          type="button"
          onClick={() => { setPlaying(false); setSelectedEventId(sortedEvents[0]?.event_id ?? null); }}
          className="trajectory-player__restart"
        >
          ⏮ Restart
        </button>
        <span className="trajectory-player__position" role="status" aria-live="polite">
          Event {resolvedIndex + 1} of {total}
        </span>
      </div>

      <input
        aria-label="Replay event position"
        aria-valuetext={`Event ${resolvedIndex + 1} of ${total}`}
        type="range"
        min={0}
        max={Math.max(0, total - 1)}
        value={resolvedIndex}
        onChange={(e) => {
          setPlaying(false);
          const next = Number(e.target.value);
          setSelectedEventId(sortedEvents[next]?.event_id ?? null);
        }}
        className="trajectory-player__range"
      />

      {currentEvent && <EventFrame event={currentEvent} />}
    </div>
  );
}

function EventFrame({ event }: { event: Event }) {
  return (
    <article className="trajectory-frame">
      <p className="trajectory-frame__meta">
        {event.emitted_at} · {event.role ?? "?"} · {event.action_type}
      </p>
      <p className="trajectory-frame__id">
        event_id: {event.event_id}
      </p>
      <pre>
        {JSON.stringify(event.payload, null, 2)}
      </pre>
    </article>
  );
}
