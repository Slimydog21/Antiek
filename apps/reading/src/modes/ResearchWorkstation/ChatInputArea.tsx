import { useCallback, useState } from "react";
import { useNavigate } from "react-router-dom";

import LemonButton from "../../components/lemon/LemonButton";
import LemonTextarea from "../../components/lemon/LemonTextarea";
import { track, trackException } from "../../lib/analytics";
import { startInvestigation } from "../../lib/api";
import { emitWernerExperience } from "../../werner/reactionBus";

/**
 * Bottom-of-center chat input. Submit on Cmd/Ctrl+Enter; click "Ask"
 * via the button at the right. POST /investigations + (by default)
 * navigate to `/inv/<id>`.
 *
 *   parentInvestigationId   if present, child-of-parent context is set
 *   spawnContext            the original highlight (chase-this)
 *   placeholder             override the placeholder text
 *   autoFocus               steal focus on mount
 *   onSubmitted             called with the new investigation_id;
 *                           when omitted, the component navigates itself
 *
 * S5 redesign: now a Lemon-styled docked-bottom panel surface. The
 * surrounding chrome (sun-yellow border, ink offset shadow) is provided
 * by PanelLayoutPanel; this component renders only the inner controls.
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
      track("investigation_started", {
        question_length: q.length,
        has_parent: Boolean(parentInvestigationId),
        has_spawn_context: Boolean(spawnContext),
      });
      setQuestion("");
      if (onSubmitted) {
        onSubmitted(resp.investigation_id);
      } else {
        navigate(`/inv/${resp.investigation_id}`);
      }
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      trackException(e instanceof Error ? e : new Error(msg));
      setError(`Submit failed: ${msg}`);
    } finally {
      setBusy(false);
    }
  }, [question, parentInvestigationId, spawnContext, navigate, onSubmitted]);

  return (
    <div className="h-full flex flex-col p-3 bg-ice-1 dark:bg-charcoal-2 text-ink dark:text-bright">
      <div className="flex-1 min-h-0 flex flex-col">
        <LemonTextarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onSubmit={() => void submit()}
          placeholder={placeholder ?? "What do you want to research?"}
          autoFocus={autoFocus}
          disabled={busy}
          minRows={2}
          maxRows={10}
          className="font-serif text-[15px] leading-relaxed"
        />
        {error && (
          <div className="text-xs font-mono text-emperor mt-2">{error}</div>
        )}
      </div>
      <div className="mt-2 flex items-center justify-between gap-3">
        <div className="text-[11px] font-mono text-ink-mute dark:text-moonlight">
          <kbd className="border-2 border-ink dark:border-bright rounded px-1.5 text-[10px] font-mono bg-ice-0 dark:bg-charcoal-1 shadow-[2px_2px_0_0_#0F1419] dark:shadow-[2px_2px_0_0_#8A7300] mr-1.5">⌘ ↵</kbd>
          to submit · ~$0.08-$0.16 / investigation
        </div>
        <LemonButton
          variant="primary"
          onClick={() => void submit()}
          disabled={busy || question.trim().length < 3}
        >
          {busy ? "…" : "Ask"}
        </LemonButton>
      </div>
    </div>
  );
}
