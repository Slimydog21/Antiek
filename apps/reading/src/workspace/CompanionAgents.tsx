/**
 * CompanionAgents.tsx — the agent surfaces the companion pane renders, one
 * per shipped tab kind. The registry (companionRegistry.tsx) maps kind →
 * surface as DATA: islands (unit 2) and diligence (unit 7) slot in later as
 * new entries without restructuring the pane.
 */
import { useEffect, useState, useSyncExternalStore } from "react";
import AIActionFailure from "../shared/AIActionFailure";
import LemonButton from "../components/lemon/LemonButton";
import { ApiError, getInvestigationStatus } from "../lib/api";
import type { InvestigationSummary, InvestigationStatus } from "../lib/api";
import {
  researchStateLabel,
  researchStateStyle,
} from "../shared/researchState";
import { thoughtPartnerOnce } from "../components/ai/thoughtPartnerOnce";
import { sourceDocumentOf, useCompanion, type AgentTabDescriptor } from "./companionStore";
import { getTabOwner, subscribeTabOwner } from "./tabTreeOwner";
import { useTabTrees } from "./tabTreeStore";
import { openDocumentInLeftPane } from "./crossPane";
import { ModeLink } from "./ModeLink";

export interface AgentSurfaceProps {
  tab: AgentTabDescriptor;
  /** The pane-resolved summary for research-thread tabs (undefined while
   *  the list loads or when the thread is outside the fetched page). */
  summary?: InvestigationSummary;
  summaryMissing?: boolean;
}

/** The ambient scope the companion's dialogue exchanges are bucketed under —
 *  the AISidecar "__sidecar__" convention, kept distinct per surface. */
export const COMPANION_DIALOGUE_SCOPE = "__companion__";

// ─── research thread ─────────────────────────────────────────────────────

export function ResearchThreadSurface({ tab, summary, summaryMissing }: AgentSurfaceProps) {
  if (!summary) {
    return summaryMissing && tab.investigationId ? <SavedThreadStatus tab={tab} threadId={tab.investigationId} /> : (
      <div className="p-3 text-sm text-ink-soft dark:text-moonlight" data-agent-surface="research-thread">
        Loading this thread’s status…
      </div>
    );
  }
  const style = researchStateStyle(summary.status);
  const documentId = tab.documentId ?? sourceDocumentOf(summary);
  return (
    <div className="p-3 flex flex-col gap-2" data-agent-surface="research-thread">
      <div className="flex items-center gap-2">
        <span className="text-xxs uppercase tracking-wider text-shadow-1 dark:text-moonlight">
          {researchStateLabel(style.state)}
        </span>
        {summary.spawned_by_daemon ? (
          <span className="text-xxs font-mono text-shadow-1 dark:text-moonlight">
            · found by the loop
          </span>
        ) : null}
      </div>
      <p className="text-sm font-serif text-ink dark:text-bright leading-relaxed line-clamp-4">
        {summary.question ?? "(no question on record)"}
      </p>
      <p className="text-xxs font-mono text-shadow-1 dark:text-moonlight">
        ${summary.cost_usd_total.toFixed(2)}
        {summary.completed_at
          ? ` · done ${summary.completed_at.slice(0, 10)}`
          : summary.started_at
            ? ` · started ${summary.started_at.slice(0, 10)}`
            : ""}
      </p>
      <div className="flex items-center gap-3 mt-1">
        {/* Opens in the operator's current mode (ModeLink → inMode): beside
            a reader the research is /inv/<id>?m=reading, a tab in the
            reading tree, never a switch into research (R2-H1). */}
        <ModeLink
          to={`/inv/${encodeURIComponent(summary.investigation_id)}`}
          className="text-xs font-mono text-sun-deep underline-offset-2 hover:underline"
        >
          Open research →
        </ModeLink>
        {/* The C4→C5 seam (crossPane.ts): the agent opens its source
            document as a LEFT tab in the current mode's tree. The document
            is the thread's provenance (the opener's, else the thread's own
            parent reading thread); absent, no affordance, never a guessed
            target. */}
        {documentId ? (
          <button
            type="button"
            className="text-xs font-mono text-sun-deep underline-offset-2 hover:underline"
            onClick={() =>
              openDocumentInLeftPane(documentId, {
                from: "companion",
                investigationId: tab.investigationId,
                agentTabId: tab.id,
                agentKind: "research",
              })
            }
          >
            Open source document →
          </button>
        ) : null}
      </div>
    </div>
  );
}

/** A restored thread may be outside the list's newest 50. Its real status
 * endpoint supplies status only; never manufacture question, cost or source. */
function SavedThreadStatus({ tab, threadId }: { tab: AgentTabDescriptor; threadId: string }) {
  const owner = useSyncExternalStore(subscribeTabOwner, getTabOwner);
  const epoch = useTabTrees((state) => state.contextEpoch);
  const key = `${owner.epoch}:${epoch}:${threadId}`;
  const [attempt, setAttempt] = useState(0);
  const [result, setResult] = useState<{ key: string; status: InvestigationStatus["status"] | null } | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    if (owner.suspended) return () => controller.abort();
    void getInvestigationStatus(threadId, controller.signal).then((reply) => {
      if (!controller.signal.aborted && getTabOwner().epoch === owner.epoch && useTabTrees.getState().contextEpoch === epoch) {
        const status = ["in_progress", "completed", "failed", "not_found"].includes(reply.status) ? reply.status : null;
        setResult({ key, status });
      }
    }).catch(() => {
      if (!controller.signal.aborted && getTabOwner().epoch === owner.epoch && useTabTrees.getState().contextEpoch === epoch) setResult({ key, status: null });
    });
    return () => controller.abort();
  }, [threadId, owner.epoch, owner.suspended, epoch, key, attempt]);
  const loaded = result?.key === key;
  const status = loaded ? result.status : null;
  return <div className="p-3 flex flex-col gap-2 text-sm text-2" data-agent-surface="research-thread">
    <p>{!loaded ? "Loading this thread’s status…" : status && status !== "not_found" ? researchStateLabel(researchStateStyle(status).state) : "This thread's status is unavailable for this account."}</p>
    <p className="font-serif">{tab.title || "Research thread"}</p>
    <ModeLink to={`/inv/${encodeURIComponent(threadId)}`} className="text-xs text-sun-deep hover:underline">Open research →</ModeLink>
    {loaded && !status && <button type="button" onClick={() => { setResult(null); setAttempt((value) => value + 1); }} className="text-xs underline">Retry thread status</button>}
  </div>;
}

// ─── dialogue (one-shot thought partner — never a chat) ──────────────────

export function DialogueSurface({ tab }: AgentSurfaceProps) {
  const { prompt, pending, exchange, failure } = useCompanion((state) => state.dialogue);
  const setDraft = useCompanion((state) => state.setDialogue);

  async function ask() {
    const p = prompt.trim();
    if (p.length < 3) return;
    const ownerEpoch = getTabOwner().epoch;
    setDraft({ pending: true, exchange: null, failure: null });
    try {
      const reply = await thoughtPartnerOnce({
        investigationId: COMPANION_DIALOGUE_SCOPE,
        prompt: p,
      });
      if (getTabOwner().epoch === ownerEpoch && !getTabOwner().suspended) setDraft({ exchange: reply });
    } catch (e) {
      // No-key 503 → null reason → AIActionFailure's "provider isn't
      // configured" sentence (the VoiceChaseButton.tsx:56 pattern). Honest,
      // never a fabricated reply.
      const status = e instanceof ApiError ? e.status : 0;
      if (getTabOwner().epoch === ownerEpoch && !getTabOwner().suspended) setDraft({ failure: { reason: status === 503 ? null : e instanceof Error ? e.message : String(e) } });
    } finally {
      if (getTabOwner().epoch === ownerEpoch) setDraft({ pending: false });
    }
  }

  return (
    <div className="p-3 flex flex-col gap-2" data-agent-surface="dialogue" data-tab-id={tab.id}>
      {failure ? (
        <AIActionFailure
          title="Couldn’t get a reply"
          reason={failure.reason}
          onRetry={() => setDraft({ failure: null })}
          retryLabel="Try again"
        />
      ) : null}
      {exchange ? (
        <>
          {/* The user's prompt — visibly USER-sourced. */}
          <blockquote className="text-sm font-serif text-ink-soft dark:text-starlight italic border-l-edge border-sun pl-2 leading-relaxed">
            “{exchange.prompt}”
          </blockquote>
          {/* The MODEL reply — labelled, never conflated with the user's words. */}
          <div className="bg-shadow-2 rounded p-2">
            <span className="text-xxs uppercase tracking-wider text-moonlight block mb-0.5">
              AI reply
            </span>
            <p className="text-sm text-bright whitespace-pre-wrap leading-relaxed">
              {exchange.reply}
            </p>
            <p className="text-xxs uppercase tracking-wide text-moonlight font-mono" data-testid="dialogue-shape">
              {exchange.shape}
            </p>
          </div>
        </>
      ) : null}
      <textarea
        value={prompt}
        onChange={(e) => setDraft({ prompt: e.target.value })}
        placeholder="Ask the thought partner (one-shot)…"
        rows={3}
        aria-label="Ask the thought partner"
        className="w-full bg-shadow-2 text-bright rounded p-1.5 text-sm resize-none outline-none"
      />
      <div className="flex items-center gap-2">
        <LemonButton
          variant="primary"
          size="sm"
          disabled={pending || prompt.trim().length < 3}
          onClick={() => void ask()}
        >
          {pending ? "Asking…" : exchange ? "Ask again" : "Ask"}
        </LemonButton>
        <span className="text-xxs text-moonlight">One-shot reply · session only.</span>
      </div>
    </div>
  );
}
