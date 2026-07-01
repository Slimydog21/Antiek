import { useCallback, useEffect, useState } from "react";

import { listWatchForLater, type ParkedQuestionEntry } from "../../lib/api";
import WatchForLaterFolder from "./WatchForLaterFolder";

export const BRAINSTORM_SELECT_QUESTION_EVENT = "antiek:brainstorm:select-question";
export const BRAINSTORM_WATCHLIST_CHANGED_EVENT =
  "antiek:brainstorm:watchlist-changed";

let latestBrainstormQuestionSelection: ParkedQuestionEntry | null = null;

export function dispatchBrainstormQuestionSelection(question: ParkedQuestionEntry) {
  latestBrainstormQuestionSelection = question;
  window.dispatchEvent(
    new CustomEvent(BRAINSTORM_SELECT_QUESTION_EVENT, {
      detail: { question },
    }),
  );
}

export function dispatchBrainstormWatchlistChanged() {
  window.dispatchEvent(new CustomEvent(BRAINSTORM_WATCHLIST_CHANGED_EVENT));
}

export function getBrainstormQuestionSelection(): ParkedQuestionEntry | null {
  return latestBrainstormQuestionSelection;
}

export function resetBrainstormQuestionSelection() {
  latestBrainstormQuestionSelection = null;
}

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
    const onChanged = () => {
      void reload();
    };
    window.addEventListener(BRAINSTORM_WATCHLIST_CHANGED_EVENT, onChanged);
    return () => {
      clearInterval(t);
      window.removeEventListener(BRAINSTORM_WATCHLIST_CHANGED_EVENT, onChanged);
    };
  }, [reload]);

  useEffect(() => {
    const applySelection = (question: ParkedQuestionEntry) => {
      setSelected(question);
    };
    const latest = getBrainstormQuestionSelection();
    if (latest) applySelection(latest);
    const onSelect = (event: Event) => {
      const question = (event as CustomEvent<{ question?: ParkedQuestionEntry }>)
        .detail?.question;
      if (question) applySelection(question);
    };
    window.addEventListener(BRAINSTORM_SELECT_QUESTION_EVENT, onSelect);
    return () => {
      window.removeEventListener(BRAINSTORM_SELECT_QUESTION_EVENT, onSelect);
    };
  }, []);

  return (
    <div className="h-full overflow-y-auto bg-ice-1 dark:bg-charcoal-2">
      <WatchForLaterFolder
        questions={questions}
        loading={loading}
        error={error}
        selectedId={selected?.question_id ?? null}
        onSelect={(question) => {
          setSelected(question);
          dispatchBrainstormQuestionSelection(question);
        }}
      />
    </div>
  );
}
