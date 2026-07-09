import { useCallback, useState } from "react";
import { useNavigate } from "react-router-dom";

import {
  ResearchLaunchBudgetPanel,
  type ResearchLaunchBudgetProjection,
} from "../../components/engagement/ResearchLaunchBudgetPanel";
import LemonButton from "../../components/lemon/LemonButton";
import LemonTextarea from "../../components/lemon/LemonTextarea";
import { track, trackException } from "../../lib/analytics";
import { startInvestigation } from "../../lib/api";
import type { ResearchTier } from "../../lib/api";
import {
  hydratePublicationRefs,
  parsePublicationRefs,
  questionWithPublicationRefs,
} from "./publicationRefs";

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
 *   researchTier           optional fast|deep for budget projection (default deep)
 *
 * S5 redesign: now a Lemon-styled docked-bottom panel surface. The
 * surrounding chrome (sun-yellow border, ink offset shadow) is provided
 * by PanelLayoutPanel; this component renders only the inner controls.
 *
 * Residual (bq): live budget + #440 projection (parity with StartResearch bp).
 * Residual (ct): publication refs (arxiv/substack/url) parity with StartResearch cj.
 * Residual (df): soft-gate Ask when budget projection would exceed (parity de).
 */
export default function ChatInputArea({
  parentInvestigationId,
  spawnContext,
  placeholder,
  autoFocus,
  onSubmitted,
  researchTier = "deep",
}: {
  parentInvestigationId?: string;
  spawnContext?: string;
  placeholder?: string;
  autoFocus?: boolean;
  onSubmitted?: (investigationId: string) => void;
  researchTier?: ResearchTier;
}) {
  const [question, setQuestion] = useState(spawnContext ?? "");
  const [pubRefs, setPubRefs] = useState("");
  const [pubRefStatus, setPubRefStatus] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [budgetWarn, setBudgetWarn] = useState(false);
  const [forceOverBudget, setForceOverBudget] = useState(false);
  const navigate = useNavigate();

  const onProjectionChange = useCallback((p: ResearchLaunchBudgetProjection) => {
    setBudgetWarn(p.wouldExceedBudget === true);
  }, []);

  const submit = useCallback(async () => {
    const q = question.trim();
    if (!q || q.length < 3) {
      setError("Question is too short. At least 3 characters.");
      return;
    }
    if (budgetWarn && !forceOverBudget) {
      setError(
        "Projected cost may exceed remaining daily budget — enable force override or reduce scope.",
      );
      return;
    }
    setBusy(true);
    setError(null);
    setPubRefStatus(null);
    try {
      const refs = parsePublicationRefs(pubRefs);
      let launchQuestion = q;
      if (refs.length > 0) {
        const hydrated = await hydratePublicationRefs(refs);
        setPubRefStatus(
          `Hydrated ${hydrated.ok.length} publication asset(s)` +
            (hydrated.failed.length ? ` · ${hydrated.failed.length} failed` : "") +
            " · HTML-first",
        );
        launchQuestion = questionWithPublicationRefs(q, refs);
      }
      const resp = await startInvestigation({
        question: launchQuestion,
        parent_investigation_id: parentInvestigationId,
        spawn_context: spawnContext,
      });
      track("investigation_started", {
        question_length: launchQuestion.length,
        has_parent: Boolean(parentInvestigationId),
        has_spawn_context: Boolean(spawnContext),
        publication_ref_count: refs.length,
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
    pubRefs,
    parentInvestigationId,
    spawnContext,
    navigate,
    onSubmitted,
    budgetWarn,
    forceOverBudget,
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
          className="font-serif text-[15px] leading-relaxed"
        />
        {error && (
          <div className="text-xs font-mono text-emperor mt-2">{error}</div>
        )}
      </div>
      {/* Residual (ct): arxiv/substack/URL handles for chase follow-ups. */}
      <div
        className="mt-2 space-y-1"
        data-testid="chat-input-publication-refs"
        data-view-format="html"
      >
        <label
          className="text-[10px] font-mono uppercase tracking-wider text-ink-mute dark:text-moonlight"
          htmlFor="chat-publication-refs-input"
        >
          Publication refs
        </label>
        <textarea
          id="chat-publication-refs-input"
          data-testid="chat-publication-refs-input"
          value={pubRefs}
          onChange={(e) => setPubRefs(e.target.value)}
          disabled={busy}
          rows={2}
          placeholder={"arxiv:1706.03762\nhttps://…"}
          className="w-full rounded border border-ink/20 bg-transparent px-2 py-1 text-[11px] font-mono dark:border-bright/20"
        />
        {pubRefStatus ? (
          <p
            className="text-[10px] font-mono text-aurora"
            data-testid="chat-publication-refs-status"
            role="status"
          >
            {pubRefStatus}
          </p>
        ) : null}
      </div>
      {/* Residual (bq/df): same launch budget panel as StartResearch (bp). */}
      <div className="mt-2" data-testid="chat-input-budget-mount">
        <ResearchLaunchBudgetPanel
          promptText={question}
          researchTier={researchTier === "fast" ? "fast" : "deep"}
          allowTierPick
          onProjectionChange={onProjectionChange}
        />
        {budgetWarn ? (
          <label
            className="mt-1 flex items-center gap-2 text-[11px] font-mono text-emperor"
            data-testid="chat-input-over-budget-warn"
          >
            <input
              type="checkbox"
              data-testid="chat-input-force-over-budget"
              checked={forceOverBudget}
              onChange={(e) => setForceOverBudget(e.target.checked)}
              disabled={busy}
            />
            Force Ask despite budget projection
          </label>
        ) : null}
      </div>
      <div className="mt-2 flex items-center justify-between gap-3">
        <div className="text-[11px] font-mono text-ink-mute dark:text-moonlight">
          <kbd className="border-2 border-ink dark:border-bright rounded px-1.5 text-[10px] font-mono bg-ice-0 dark:bg-charcoal-1 shadow-[2px_2px_0_0_#0F1419] dark:shadow-[2px_2px_0_0_#8A7300] mr-1.5">⌘ ↵</kbd>
          to submit · live projection above
        </div>
        <LemonButton
          variant="primary"
          onClick={() => void submit()}
          disabled={
            busy ||
            question.trim().length < 3 ||
            (budgetWarn && !forceOverBudget)
          }
        >
          {busy ? "…" : "Ask"}
        </LemonButton>
      </div>
    </div>
  );
}
