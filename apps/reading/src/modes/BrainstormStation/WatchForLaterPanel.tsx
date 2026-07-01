import { useCallback, useEffect, useState } from "react";

import { listWatchForLater, type ParkedQuestionEntry } from "../../lib/api";
import WatchForLaterFolder from "./WatchForLaterFolder";

export const BRAINSTORM_SELECT_QUESTION_EVENT = "antiek:brainstorm:select-question";

/**
 * BrainstormStation's "watch for later" parked-questions list as a
 * PanelKind. Self-fetches the parked-question list (PanelHost freezes
 * starter props at mount time, so we can't trust a parent-passed
 * `questions` prop to update).
 *
 * Selection emits a small browser event so the route's main slot can
 * show the selected question even though PanelHost freezes starter props.
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
        onSelect={(question) => {
          setSelected(question);
          window.dispatchEvent(
            new CustomEvent(BRAINSTORM_SELECT_QUESTION_EVENT, {
              detail: { question },
            }),
          );
        }}
      />
    </div>
  );
}
