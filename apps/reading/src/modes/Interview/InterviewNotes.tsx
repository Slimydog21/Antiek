import { useEffect, useState } from "react";

/**
 * InterviewNotes panel (S10 row 10.10).
 *
 * A scratchpad for the operator's observations while running an
 * interview — what the informant emphasised, body-language cues,
 * follow-up questions to ask later. Lives in localStorage keyed by
 * interviewId so notes survive panel toggling + reloads. Substrate-
 * side notes (typed events) are a separate concern; this is the
 * operator's private margin.
 */
type Props = {
  interviewId?: string;
};

const LS_PREFIX = "antiek.interview-notes.";

export default function InterviewNotes({ interviewId }: Props) {
  const [text, setText] = useState<string>("");
  const [saved, setSaved] = useState<"idle" | "saving" | "saved">("idle");

  // Load on mount + on interview change
  useEffect(() => {
    if (!interviewId) {
      setText("");
      return;
    }
    try {
      const stored = window.localStorage.getItem(LS_PREFIX + interviewId);
      setText(stored ?? "");
    } catch {
      setText("");
    }
  }, [interviewId]);

  // Debounced autosave (1.2s after last keypress)
  useEffect(() => {
    if (!interviewId) return;
    setSaved("saving");
    const t = setTimeout(() => {
      try {
        window.localStorage.setItem(LS_PREFIX + interviewId, text);
        setSaved("saved");
      } catch {
        // ignore quota
      }
    }, 1200);
    return () => clearTimeout(t);
  }, [text, interviewId]);

  if (!interviewId) {
    return (
      <div className="h-full p-3 bg-ice-0 dark:bg-charcoal-2 text-[12px] font-mono italic text-ink-mute dark:text-moonlight">
        No interview loaded.
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col bg-ice-0 dark:bg-charcoal-2">
      <header className="px-3 py-2 flex items-center justify-between border-b border-rule dark:border-charcoal-1">
        <h3 className="text-xs font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
          Notes · operator margin
        </h3>
        <span className="text-[10px] font-mono text-ink-mute dark:text-moonlight">
          {saved === "saving"
            ? "saving…"
            : saved === "saved"
              ? "saved to local"
              : ""}
        </span>
      </header>
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder={
          "Body-language cues, emphasis, follow-ups… stored locally only."
        }
        className="flex-1 w-full p-3 font-serif text-[14px] leading-relaxed bg-transparent text-ink dark:text-bright outline-none resize-none"
      />
      <footer className="px-3 py-2 border-t border-rule dark:border-charcoal-1 text-[10px] font-mono text-ink-mute dark:text-moonlight">
        Notes are operator-private (localStorage). Substrate events are
        recorded separately via the main compose form.
      </footer>
    </div>
  );
}
