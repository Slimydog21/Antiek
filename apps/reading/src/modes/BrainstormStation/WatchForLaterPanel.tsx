import { useCallback, useEffect, useState } from "react";

import { listWatchForLater, type ParkedQuestionEntry } from "../../lib/api";
import WatchForLaterFolder from "./WatchForLaterFolder";

/**
 * BrainstormStation's "watch for later" parked-questions list as a
 * PanelKind. Self-fetches the parked-question list (PanelHost freezes
 * starter props at mount time, so we can't trust a parent-passed
 * `questions` prop to update).
 *
 * Selection is a self-managed concern — clicking a question shows it
 * inline below the list rather than syncing with the main slot.
 * Future improvement: wire selection through workspace store so the
 * main slot's ParkedQuestion view follows the operator's choice.
 */
export default function WatchForLaterPanel() {
  const [questions, setQuestions] = useState<ParkedQuestionEntry[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<ParkedQuestionEntry | null>(null);

  const reload = useCallback(async () => {
    setLoading(true);
    try {
      const data = await listWatchForLater();
      setQuestions(data.questions);
      setError(null);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void reload();
    const t = setInterval(reload, 15_000);
    return () => clearInterval(t);
  }, [reload]);

  return (
    <div className="h-full overflow-y-auto bg-ice-1 dark:bg-charcoal-2">
      <WatchForLaterFolder
        questions={questions}
        loading={loading}
        error={error}
        selectedId={selected?.question_id ?? null}
        onSelect={setSelected}
      />
    </div>
  );
}
