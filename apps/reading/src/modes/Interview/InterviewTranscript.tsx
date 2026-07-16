import { useCallback, useEffect, useState } from "react";

import thinkingArt from "../../brand/werner/poses/session/werner_thinking_session_v1.png";
import { apiFetch } from "../../lib/api";
import { emitWernerExperience } from "../../werner/reactionBus";

/**
 * InterviewTranscript panel (S10 row 10.10; Speak SPR-02 M5).
 *
 * Read-only transcript viewer that can be docked alongside the main
 * interview view. The operator gets a calm, prose-optimised reading
 * surface while the compose form lives in main slot. Refreshes on a
 * 10s timer when mounted; future improvement: subscribe to a
 * substrate-side transcript-changed event instead of polling.
 *
 * Speak SPR-02 adds transcript CORRECTION: ASR mishears names, places,
 * and dates — exactly the biographical details that matter — so a
 * `pending` informant turn (transcribed, not yet distilled) is
 * editable before it is distilled. The backend (`submit_answer`)
 * distills the corrected text, never the raw one; this surface is how
 * the interviewee fixes "Kyro" → "Cairo" before it becomes a confident
 * fact in the graph.
 */
type Turn = {
  role: "interviewer" | "informant";
  text: string;
  ts: string | null;
  /** Set on a transcribed-but-not-yet-distilled answer (Speak SPR-02). */
  pending?: boolean;
  /** The question this answer is anchored to (Speak SPR-02). */
  question_id?: string;
};

type Props = {
  interviewId?: string;
  /**
   * Seed turns directly instead of fetching — used by Storybook and
   * tests. When provided, the polling fetch is skipped.
   */
  seedTurns?: Turn[];
  /**
   * Called when the interviewee saves a correction to a `pending`
   * turn. Receives the turn index and the corrected text. The host
   * persists it (and distillation runs from the corrected text).
   */
  onCorrect?: (index: number, correctedText: string) => void | Promise<void>;
};

export default function InterviewTranscript({
  interviewId,
  seedTurns,
  onCorrect,
}: Props) {
  const [turns, setTurns] = useState<Turn[]>(seedTurns ?? []);
  const [error, setError] = useState<string | null>(null);
  const [editingIndex, setEditingIndex] = useState<number | null>(null);
  const [draft, setDraft] = useState<string>("");

  const reload = useCallback(async () => {
    if (seedTurns || !interviewId) return;
    try {
      const resp = await apiFetch(
        `/interviews/${encodeURIComponent(interviewId)}`,
      );
      if (!resp.ok) {
        setError(`HTTP ${resp.status}`);
        return;
      }
      const data = await resp.json();
      const t: Turn[] = Array.isArray(data.transcript) ? data.transcript : [];
      setTurns(t);
      setError(null);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }, [interviewId, seedTurns]);

  useEffect(() => {
    if (seedTurns) return;
    void reload();
    const handle = setInterval(() => void reload(), 10_000);
    return () => clearInterval(handle);
  }, [reload, seedTurns]);

  const beginEdit = useCallback((index: number, current: string) => {
    setEditingIndex(index);
    setDraft(current);
  }, []);

  const saveEdit = useCallback(
    async (index: number) => {
      const corrected = draft.trim();
      try {
        setTurns((prev) =>
          prev.map((t, i) =>
            i === index ? { ...t, text: corrected, pending: false } : t,
          ),
        );
        setEditingIndex(null);
        if (onCorrect) await onCorrect(index, corrected);
        // Living-TV: transcript correction saved — noted.
        emitWernerExperience("note_saved");
      } catch {
        emitWernerExperience("fail");
      }
    },
    [draft, onCorrect],
  );

  if (!interviewId && !seedTurns) {
    return (
      <div className="h-full p-3 bg-ice-0 dark:bg-charcoal-2 text-[12px] font-mono italic text-ink-mute dark:text-moonlight">
        No interview loaded.
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto p-3 bg-ice-0 dark:bg-charcoal-2">
      <header className="mb-2 flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          <img
            src={thinkingArt}
            alt=""
            aria-hidden="true"
            data-testid="interview-transcript-werner-brand"
            className="h-6 w-6 shrink-0 object-contain"
          />
          <h3 className="text-xs font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
            Transcript · {turns.length} turn{turns.length === 1 ? "" : "s"}
          </h3>
        </div>
        {!seedTurns && (
          <button
            type="button"
            onClick={() => void reload()}
            className="text-[10px] font-mono text-sun-deep dark:text-sun hover:underline"
          >
            refresh
          </button>
        )}
      </header>
      {error && (
        <p className="text-[12px] text-emperor font-mono mb-2">{error}</p>
      )}
      {turns.length === 0 ? (
        <p className="text-[12px] italic text-ink-mute dark:text-moonlight font-serif">
          No turns recorded yet.
        </p>
      ) : (
        <ol className="space-y-3">
          {turns.map((t, i) => {
            const correctable = t.role === "informant" && t.pending === true;
            const isEditing = editingIndex === i;
            return (
              <li key={i} className="font-serif text-[14px] leading-relaxed">
                <span
                  className={
                    "block font-mono text-[10px] uppercase tracking-wider " +
                    (t.role === "interviewer"
                      ? "text-sun-deep dark:text-sun"
                      : "text-aurora")
                  }
                >
                  {t.role}
                  {t.pending && (
                    <span className="ml-2 text-sun-deep dark:text-sun">
                      · pending correction
                    </span>
                  )}
                  {t.ts && (
                    <span className="ml-2 text-ink-mute dark:text-moonlight">
                      {t.ts}
                    </span>
                  )}
                </span>
                {isEditing ? (
                  <div className="mt-1">
                    <textarea
                      value={draft}
                      onChange={(e) => setDraft(e.target.value)}
                      rows={3}
                      className="w-full font-serif text-[14px] p-2 border border-ink-mute rounded bg-ice-0 dark:bg-charcoal-1 text-ink dark:text-bright"
                    />
                    <div className="mt-1 flex gap-2">
                      <button
                        type="button"
                        onClick={() => void saveEdit(i)}
                        className="text-[10px] font-mono text-sun-deep dark:text-sun hover:underline"
                      >
                        save correction
                      </button>
                      <button
                        type="button"
                        onClick={() => setEditingIndex(null)}
                        className="text-[10px] font-mono text-ink-mute hover:underline"
                      >
                        cancel
                      </button>
                    </div>
                  </div>
                ) : (
                  <p className="text-ink dark:text-bright mt-0.5">
                    {t.text}
                    {correctable && (
                      <button
                        type="button"
                        onClick={() => { emitWernerExperience("highlight"); beginEdit(i, t.text); }}
                        className="ml-2 text-[10px] font-mono text-sun-deep dark:text-sun hover:underline align-middle"
                      >
                        correct
                      </button>
                    )}
                  </p>
                )}
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}
