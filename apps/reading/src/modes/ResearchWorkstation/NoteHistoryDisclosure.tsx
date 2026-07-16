import { useEffect, useRef, useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";

import { getNoteHistory } from "../../lib/api";
import type { NoteHistoryResponse } from "../../lib/api";

export interface NoteHistoryDisclosureProps {
  nodeId: string;
  investigationId: string;
  refinementCount: number;
  version?: number;
}

/** Lazy, integrity-checked history shared by live and completed note surfaces. */
export default function NoteHistoryDisclosure({
  nodeId,
  investigationId,
  refinementCount,
  version = 0,
}: NoteHistoryDisclosureProps) {
  const [open, setOpen] = useState(false);
  const [history, setHistory] = useState<NoteHistoryResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [failed, setFailed] = useState(false);
  const requestGeneration = useRef(0);

  useEffect(() => {
    requestGeneration.current += 1;
    setOpen(false);
    setHistory(null);
    setLoading(false);
    setFailed(false);
  }, [nodeId, investigationId, refinementCount, version]);

  const load = async () => {
    const generation = ++requestGeneration.current;
    setOpen(true);
    setLoading(true);
    setFailed(false);
    try {
      const response = await getNoteHistory(nodeId, investigationId);
      if (generation !== requestGeneration.current) return;
      setHistory(response);
    } catch {
      if (generation !== requestGeneration.current) return;
      setFailed(true);
    } finally {
      if (generation !== requestGeneration.current) return;
      setLoading(false);
    }
  };

  const toggle = () => {
    if (open) setOpen(false);
    else if (history) setOpen(true);
    else void load();
  };

  return (
    <div className="basis-full">
      <button
        type="button"
        onClick={toggle}
        aria-expanded={open}
        className="inline-flex items-center gap-1 font-mono underline decoration-dotted underline-offset-2 transition-colors hover:text-ink dark:hover:text-bright"
      >
        {open ? <ChevronDown size={12} aria-hidden="true" /> : <ChevronRight size={12} aria-hidden="true" />}
        {refinementCount} {refinementCount === 1 ? "change" : "changes"}
      </button>
      {open && loading && (
        <p className="mt-1.5 font-mono text-[11px] italic" role="status">loading change history…</p>
      )}
      {open && failed && (
        <p className="mt-1.5 font-mono text-[11px]" role="alert">
          Couldn’t load change history.{" "}
          <button type="button" onClick={() => void load()} className="underline decoration-dotted underline-offset-2">
            Try again
          </button>
        </p>
      )}
      {open && history && !loading && !failed && (
        <div className="mt-2 border-l-2 border-rule pl-2.5 dark:border-charcoal-1">
          {!history.complete && (
            <p className="mb-2 font-mono text-[11px] text-shadow-1 dark:text-moonlight">
              Earlier changes predate the authoritative history available here.
            </p>
          )}
          <ol className="space-y-2">
            {history.entries.map((entry) => (
              <li key={entry.event_id} className="text-[12px] leading-relaxed">
                <p className="font-mono text-[10px] uppercase text-shadow-1 dark:text-moonlight">
                  {entry.outcome === "applied" ? "Changed" : "Attempt did not replace the note"}
                </p>
                <p className="font-serif text-ink dark:text-bright">{entry.new_text}</p>
                {entry.outcome === "applied" && (
                  <p className="font-serif italic text-ink-mute dark:text-moonlight">was: {entry.previous_text}</p>
                )}
              </li>
            ))}
          </ol>
        </div>
      )}
    </div>
  );
}
