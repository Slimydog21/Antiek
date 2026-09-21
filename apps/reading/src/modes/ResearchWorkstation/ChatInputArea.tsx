import { useCallback, useState } from "react";
import { useNavigate } from "react-router-dom";

import ModelUsagePicker from "../../components/ai/ModelUsagePicker";
import LemonButton from "../../components/lemon/LemonButton";
import LemonTextarea from "../../components/lemon/LemonTextarea";
import { useOwnerModelChoice } from "../../hooks/useOwnerModelChoice";
import { track, trackException } from "../../lib/analytics";
import { startInvestigation } from "../../lib/api";

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
  const model = useOwnerModelChoice("chat");
  const { launchFields } = model;
  // An owner-chosen route is accepted only on a ROOT research: the server
  // refuses a start that carries both a model choice and a parent or a chased
  // passage (422 owner_model_root_required, app.py:2374). So the control is
  // offered on the root composer and is absent — not disabled, not ignored —
  // when this composer is opened as a child of something else.
  const rootLaunch = !parentInvestigationId && !spawnContext;

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
        ...(rootLaunch ? launchFields(q) : {}),
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
  }, [
    question,
    parentInvestigationId,
    spawnContext,
    navigate,
    onSubmitted,
    rootLaunch,
    launchFields,
  ]);

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
          className="font-serif text-base leading-relaxed"
        />
        {error && (
          <div className="text-xs font-mono text-emperor mt-2">{error}</div>
        )}
      </div>
      {rootLaunch && (
        <div className="mt-2 flex items-center gap-2">
          <span className="text-xxs font-mono uppercase tracking-wider text-shadow-1 dark:text-moonlight">
            Model for this research
          </span>
          <ModelUsagePicker
            models={model.models}
            value={model.selectedRowId}
            onChange={model.select}
            includeDefault
            defaultLabel="Default (house route)"
            triggerLabel={model.triggerLabel}
            triggerAriaLabel="Model for this research"
            size="sm"
          />
          {model.state === "error" && (
            <span className="text-xxs font-mono text-emperor" aria-live="polite">
              Your models couldn’t load. Default is still available.
            </span>
          )}
        </div>
      )}
      <div className="mt-2 flex items-center justify-between gap-3">
        <div className="text-xs font-mono text-ink-mute dark:text-moonlight">
          <kbd className="border-2 border-ink dark:border-bright rounded px-1.5 text-xxs font-mono bg-ice-0 dark:bg-charcoal-1 shadow-[2px_2px_0_0_#0F1419] dark:shadow-[2px_2px_0_0_#8A7300] mr-1.5">⌘ ↵</kbd>
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
