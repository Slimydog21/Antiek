import { useMemo, useRef, useEffect } from "react";

import type {
  ConfidenceLevel,
  Event,
  NoteEmergedPayload,
} from "../generated/types";
import { emitWernerExperience } from "../werner/reactionBus";

interface NotesFeedProps {
  events: Event[];
  /** Optional click handler — when the user clicks a source_event_id
   *  chip, the parent scrolls the chat feed to that event. App wires
   *  this to a DOM-id lookup on the NotesPanel row
   *  (`event-row-<event_id>`) + scrollIntoView + a transient amber
   *  ring so the eye catches the landing. No-op if the row hasn't
   *  rendered yet (event still in flight). */
  onCiteJump?: (eventId: string) => void;
}

/**
 * Live feed of ``note.emerged`` events from the background note-taker.
 *
 * Each note renders as a card with:
 * - The note text (the role's terse insight, max 1-2 sentences).
 * - A confidence badge (color-coded same as ClaimCard).
 * - Source_event_ids rendered as clickable chips. Clicking a chip
 *   fires ``onCiteJump`` — the parent can scroll the trajectory
 *   feed to the cited event.
 *
 * Auto-scrolls to bottom on each new note so the live tail is
 * always visible. Sprint 5 day 1-2 — closes the operator visibility
 * gap from Sprint 4 (notes were flowing but invisible without
 * ``curl /trajectory/...``).
 */
export default function NotesFeed({ events, onCiteJump }: NotesFeedProps) {
  const notes = useMemo(
    () =>
      events.filter(
        (e): e is Event & { payload: NoteEmergedPayload } =>
          e.action_type === "note.emerged",
      ),
    [events],
  );

  const scrollRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [notes.length]);

  return (
    <div className="flex flex-col h-full bg-ice-0 dark:bg-charcoal-2 border-l border-rule dark:border-charcoal-1">
      <div className="px-4 py-2 text-xs font-mono bg-ice-3 dark:bg-charcoal-1 border-b border-rule dark:border-charcoal-1 flex items-center justify-between">
        <span className="text-ink-soft dark:text-starlight">notes</span>
        <span className="text-shadow-1 dark:text-moonlight">
          {notes.length} insight{notes.length === 1 ? "" : "s"}
        </span>
      </div>
      <div ref={scrollRef} className="flex-1 overflow-auto px-3 py-3">
        {notes.length === 0 ? (
          <div className="text-sm text-ink-mute dark:text-moonlight font-mono leading-relaxed">
            <p>no notes yet.</p>
            <p className="mt-1">
              the background note-taker fires every few wrestling events;
              insights crystallized from the back-and-forth will appear here.
            </p>
          </div>
        ) : (
          <ul className="flex flex-col gap-2.5">
            {notes.map((e) => (
              <NoteCard
                key={e.event_id}
                event={e}
                onCiteJump={onCiteJump}
              />
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function NoteCard({
  event,
  onCiteJump,
}: {
  event: Event & { payload: NoteEmergedPayload };
  onCiteJump?: (eventId: string) => void;
}) {
  const p = event.payload;
  return (
    <li className="border border-amber-200 rounded-md bg-sun/10/30 px-3 py-2.5 flex flex-col gap-1.5">
      <div className="flex items-start justify-between gap-2">
        <p className="text-sm text-ink dark:text-bright leading-snug flex-1">
          {p.note_text}
        </p>
        {/* Server-side default is "unknown"; the TS field type is
            ``ConfidenceLevel | undefined`` because Pydantic ``default=``
            produces an optional TS field via the codegen. Fall back
            here so the badge always renders. */}
        <ConfidenceBadge level={p.confidence ?? "unknown"} />
      </div>
      {p.source_event_ids.length > 0 && (
        <div className="flex flex-wrap gap-1 pt-0.5">
          <span className="text-[10px] font-mono text-shadow-1 dark:text-moonlight mr-0.5">
            from:
          </span>
          {p.source_event_ids.map((eid) => (
            <button
              key={eid}
              onClick={() => {
                // Living-TV: citation jump — curious glance.
                emitWernerExperience("highlight");
                onCiteJump?.(eid);
              }}
              className="text-[10px] font-mono text-ink-soft dark:text-starlight bg-ice-3 dark:bg-charcoal-1 hover:bg-ice-4 dark:bg-charcoal-1 px-1.5 py-0.5 rounded transition-colors"
              title={`jump to ${eid}`}
            >
              ↩ {shortenEventId(eid)}
            </button>
          ))}
        </div>
      )}
      <div className="text-[9px] font-mono text-ink-mute dark:text-moonlight pt-0.5">
        {shortenEventId(event.event_id)}
        {event.document_id && (
          <>
            {" · "}
            <span title={event.document_id}>doc={shortenDocId(event.document_id)}</span>
          </>
        )}
      </div>
    </li>
  );
}

function ConfidenceBadge({ level }: { level: ConfidenceLevel }) {
  const styles: Record<ConfidenceLevel, string> = {
    high: "bg-emerald-100 text-emerald-800",
    moderate: "bg-sun/20 text-amber-800",
    low: "bg-orange-100 text-orange-800",
    unknown: "bg-ice-4 dark:bg-charcoal-1 text-ink-soft dark:text-starlight",
  };
  return (
    <span
      className={`text-[10px] font-mono px-1.5 py-0.5 rounded uppercase tracking-wide ${styles[level]}`}
    >
      {level}
    </span>
  );
}

function shortenEventId(id: string): string {
  // event_id format: evt-<12hex>-<13digit>
  return id.length > 14 ? id.slice(0, 16) : id;
}

function shortenDocId(id: string): string {
  return id.length > 14 ? id.slice(0, 14) + "…" : id;
}
