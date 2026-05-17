import { useCallback, useState } from "react";
import { useNavigate } from "react-router-dom";

import { startInvestigation } from "../../lib/api";

/**
 * Bottom-of-center chat input. Submit on Cmd/Ctrl+Enter; click submit
 * via the button at the right. POST /investigations + navigate to
 * `/inv/<id>`.
 *
 * Optional `parentInvestigationId` + `spawnContext` props let this
 * component be reused inside the `<ChaseSlideOver>` (Sprint 11 day 7)
 * for chase-this child spawning.
 */
export default function ChatInputArea({
  parentInvestigationId,
  spawnContext,
  placeholder,
  autoFocus,
  onSubmitted,
}: {
  parentInvestigationId?: string;
  spawnContext?: string;
  placeholder?: string;
  autoFocus?: boolean;
  /** Called with the new investigation_id after a successful submit.
   *  When omitted, the component navigates to /inv/<id> itself. */
  onSubmitted?: (investigationId: string) => void;
}) {
  const [question, setQuestion] = useState(spawnContext ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  const submit = useCallback(async () => {
    const q = question.trim();
    if (!q || q.length < 3) {
      setError("Question is too short. At least 3 characters.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const resp = await startInvestigation({
        question: q,
        parent_investigation_id: parentInvestigationId,
        spawn_context: spawnContext,
      });
      setQuestion("");
      if (onSubmitted) {
        onSubmitted(resp.investigation_id);
      } else {
        navigate(`/inv/${resp.investigation_id}`);
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(`Submit failed: ${msg}`);
    } finally {
      setBusy(false);
    }
  }, [question, parentInvestigationId, spawnContext, navigate, onSubmitted]);

  const onKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        void submit();
      }
    },
    [submit],
  );

  return (
    <div className="border-t border-stone-200 bg-white p-3">
      <div className="flex gap-2 items-end max-w-3xl mx-auto">
        <textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder={placeholder ?? "What do you want to research?"}
          autoFocus={autoFocus}
          rows={2}
          disabled={busy}
          className="flex-1 resize-none border border-stone-300 rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-stone-900/10 focus:border-stone-400 disabled:opacity-50 font-serif leading-relaxed"
        />
        <button
          onClick={() => void submit()}
          disabled={busy || question.trim().length < 3}
          className="px-4 py-2 bg-stone-900 text-white text-sm rounded-md hover:bg-stone-700 disabled:bg-stone-400 transition-colors shrink-0"
        >
          {busy ? "…" : "Ask"}
        </button>
      </div>
      {error && (
        <div className="text-xs font-mono text-red-700 max-w-3xl mx-auto mt-2">
          {error}
        </div>
      )}
      <div className="text-[10px] font-mono text-stone-400 max-w-3xl mx-auto mt-1.5">
        ⌘+Enter to submit. Investigations cost ~$0.08-$0.16 each (per
        Sprint 10 validation).
      </div>
    </div>
  );
}
