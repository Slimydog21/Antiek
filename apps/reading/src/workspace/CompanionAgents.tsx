/**
 * CompanionAgents.tsx — the agent surfaces the companion pane renders, one
 * per shipped tab kind. The registry (companionRegistry.tsx) maps kind →
 * surface as DATA: islands (unit 2) and diligence (unit 7) slot in later as
 * new entries without restructuring the pane.
 */
import { useState } from "react";
import { Link } from "react-router-dom";

import AIActionFailure from "../shared/AIActionFailure";
import LemonButton from "../components/lemon/LemonButton";
import { ApiError } from "../lib/api";
import type { InvestigationSummary } from "../lib/api";
import {
  researchStateLabel,
  researchStateStyle,
} from "../shared/researchState";
import { thoughtPartnerOnce } from "../components/ai/thoughtPartnerOnce";
import type { ThoughtPartnerOnceReply } from "../components/ai/thoughtPartnerOnce";
import type { AgentTabDescriptor } from "./companionStore";
import { openDocumentInLeftPane } from "./crossPane";

export interface AgentSurfaceProps {
  tab: AgentTabDescriptor;
  /** The pane-resolved summary for research-thread tabs (undefined while
   *  the list loads or when the thread is outside the fetched page). */
  summary?: InvestigationSummary;
}

/** The ambient scope the companion's dialogue exchanges are bucketed under —
 *  the AISidecar "__sidecar__" convention, kept distinct per surface. */
export const COMPANION_DIALOGUE_SCOPE = "__companion__";

// ─── research thread ─────────────────────────────────────────────────────

export function ResearchThreadSurface({ tab, summary }: AgentSurfaceProps) {
  if (!summary) {
    return (
      <div className="p-3 text-sm text-ink-soft dark:text-moonlight" data-agent-surface="research-thread">
        Loading this thread’s status…
      </div>
    );
  }
  const style = researchStateStyle(summary.status);
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
        <Link
          to={`/inv/${encodeURIComponent(summary.investigation_id)}`}
          className="text-xs font-mono text-sun-deep underline-offset-2 hover:underline"
        >
          Open research →
        </Link>
        {/* The C4→C5 seam (crossPane.ts): the event shape is the contract;
            PR 3 swaps the handler for a left-pane tab spawn. Absent when the
            opening surface never knew the document — never a guessed target. */}
        {tab.documentId ? (
          <button
            type="button"
            className="text-xs font-mono text-sun-deep underline-offset-2 hover:underline"
            onClick={() =>
              openDocumentInLeftPane(tab.documentId!, {
                from: "companion",
                investigationId: tab.investigationId,
                agentTabId: tab.id,
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

// ─── dialogue (one-shot thought partner — never a chat) ──────────────────

export function DialogueSurface({ tab }: AgentSurfaceProps) {
  const [prompt, setPrompt] = useState("");
  const [pending, setPending] = useState(false);
  const [exchange, setExchange] = useState<ThoughtPartnerOnceReply | null>(null);
  const [failure, setFailure] = useState<{ reason: string | null } | null>(null);

  async function ask() {
    const p = prompt.trim();
    if (p.length < 3) return;
    setPending(true);
    setExchange(null);
    setFailure(null);
    try {
      const reply = await thoughtPartnerOnce({
        investigationId: COMPANION_DIALOGUE_SCOPE,
        prompt: p,
      });
      setExchange(reply);
    } catch (e) {
      // No-key 503 → null reason → AIActionFailure's "provider isn't
      // configured" sentence (the VoiceChaseButton.tsx:56 pattern). Honest,
      // never a fabricated reply.
      const status = e instanceof ApiError ? e.status : 0;
      setFailure({ reason: status === 503 ? null : e instanceof Error ? e.message : String(e) });
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="p-3 flex flex-col gap-2" data-agent-surface="dialogue" data-tab-id={tab.id}>
      {failure ? (
        <AIActionFailure
          title="Couldn’t get a reply"
          reason={failure.reason}
          onRetry={() => setFailure(null)}
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
        onChange={(e) => setPrompt(e.target.value)}
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
        <span className="text-xxs text-moonlight">One-shot reply (not a chat).</span>
      </div>
    </div>
  );
}
