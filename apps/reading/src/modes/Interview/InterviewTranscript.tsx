import { useCallback, useEffect, useState } from "react";

import { apiFetch } from "../../lib/api";

/**
 * InterviewTranscript panel (S10 row 10.10).
 *
 * Read-only transcript viewer that can be docked alongside the main
 * interview view. The operator gets a calm, prose-optimised reading
 * surface while the compose form lives in main slot. Refreshes on a
 * 10s timer when mounted; future improvement: subscribe to a
 * substrate-side transcript-changed event instead of polling.
 */
type Turn = {
  role: "interviewer" | "informant";
  text: string;
  ts: string | null;
};

type Props = {
  interviewId?: string;
};

export default function InterviewTranscript({ interviewId }: Props) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    if (!interviewId) return;
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
  }, [interviewId]);

  useEffect(() => {
    void reload();
    const handle = setInterval(() => void reload(), 10_000);
    return () => clearInterval(handle);
  }, [reload]);

  if (!interviewId) {
    return (
      <div className="h-full p-3 bg-ice-0 dark:bg-charcoal-2 text-[12px] font-mono italic text-ink-mute dark:text-moonlight">
        No interview loaded.
      </div>
    );
  }

  return (
    <div className="h-full overflow-y-auto p-3 bg-ice-0 dark:bg-charcoal-2">
      <header className="flex items-center justify-between mb-2">
        <h3 className="text-xs font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
          Transcript · {turns.length} turn{turns.length === 1 ? "" : "s"}
        </h3>
        <button
          type="button"
          onClick={() => void reload()}
          className="text-[10px] font-mono text-sun-deep dark:text-sun hover:underline"
        >
          refresh
        </button>
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
          {turns.map((t, i) => (
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
                {t.ts && (
                  <span className="ml-2 text-ink-mute dark:text-moonlight">
                    {t.ts}
                  </span>
                )}
              </span>
              <p className="text-ink dark:text-bright mt-0.5">{t.text}</p>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
