/**
 * DRW SPR-10 M1 + M2 — editable document view with inline highlights.
 *
 * Renders the document's raw_text with the SPR-03 notes drawn inline as
 * highlights — insights in one style, open questions in another — anchored by
 * content (see `anchor.ts`), so they survive edits or are marked stale, never
 * silently mis-placed. Edit mode is a minimal textarea (the spec's explicit
 * "engage the raw material", scoped to the minimum — not a rich-text editor);
 * saving creates a new version (SPR-08) and preserves the original. Clicking a
 * highlight selects its note (the rabbit-hole entry point).
 */

import { useMemo, useState } from "react";

import LemonButton from "../../components/lemon/LemonButton";
import type { DocumentNote } from "../../api/reading";
import { computeHighlights, toSegments } from "./anchor";

export interface DocumentViewProps {
  rawText: string;
  notes: DocumentNote[];
  selectedNoteId: string | null;
  onSelectNote: (noteId: string) => void;
  onSaveEdit: (newText: string) => void;
  busy?: boolean;
}

export default function DocumentView({
  rawText, notes, selectedNoteId, onSelectNote, onSaveEdit, busy,
}: DocumentViewProps) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(rawText);

  const { segments, staleCount } = useMemo(() => {
    const { highlights, staleNoteIds } = computeHighlights(rawText, notes);
    return { segments: toSegments(rawText, highlights), staleCount: staleNoteIds.length };
  }, [rawText, notes]);

  return (
    <div className="flex h-full flex-col gap-2">
      <div className="flex items-center justify-between">
        <span className="text-[11px] text-shadow-1 dark:text-moonlight">
          {notes.length} notes
          {staleCount > 0 && (
            <span className="ml-2 text-emperor" title="anchors no longer in the document">
              · {staleCount} stale
            </span>
          )}
        </span>
        {editing ? (
          <div className="flex gap-1.5">
            <LemonButton size="sm" variant="primary" disabled={busy}
              onClick={() => { onSaveEdit(draft); setEditing(false); }}>Save version</LemonButton>
            <LemonButton size="sm" variant="tertiary" disabled={busy}
              onClick={() => { setDraft(rawText); setEditing(false); }}>Cancel</LemonButton>
          </div>
        ) : (
          <LemonButton size="sm" variant="secondary" disabled={busy}
            onClick={() => { setDraft(rawText); setEditing(true); }}>Edit</LemonButton>
        )}
      </div>

      {editing ? (
        <textarea
          className="h-full w-full flex-1 resize-none rounded-md border-2 border-sun bg-ice-0 p-3 font-mono text-sm text-ink dark:bg-charcoal-2 dark:text-bright"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          aria-label="document editor"
        />
      ) : (
        <article className="flex-1 overflow-auto whitespace-pre-wrap rounded-md border-2 border-sun bg-ice-0 p-4 font-serif text-[15px] leading-relaxed text-ink dark:bg-charcoal-2 dark:text-bright">
          {segments.map((seg, i) =>
            seg.highlight ? (
              <mark
                key={i}
                role="button"
                tabIndex={0}
                onClick={() => onSelectNote(seg.highlight!.noteId)}
                onKeyDown={(e) => { if (e.key === "Enter") onSelectNote(seg.highlight!.noteId); }}
                className={[
                  "cursor-pointer rounded-sm px-0.5",
                  seg.highlight.kind === "insight"
                    ? "bg-sun/30 dark:bg-sun/20"
                    : "bg-aurora/25 dark:bg-aurora/20",
                  seg.highlight.noteId === selectedNoteId ? "ring-2 ring-sun" : "",
                ].join(" ")}
              >
                {seg.text}
              </mark>
            ) : (
              <span key={i}>{seg.text}</span>
            ),
          )}
        </article>
      )}
    </div>
  );
}
