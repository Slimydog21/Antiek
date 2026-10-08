/**
 * AgentReplyActions.tsx — a reply's actions as BUTTONS the user confirms
 * (SPR-07 M6). Nothing runs on render and nothing auto-dispatches (the
 * AISidecar.tsx:244-275 loop is not reused). A refusal from the frozen
 * opener renders inline instead of being swallowed (the
 * CompanionAgents.tsx:88-99 anti-pattern).
 */
import { useId, useState } from "react";

import type { AiAction } from "../../components/ai/aiActions";
import LemonButton from "../../components/lemon/LemonButton";
import { openDocumentFromAgent, type OpenDocumentFromAgentResult } from "../contracts/openers";
import { AGENT_PANE_TAB_KIND, type AgentPaneTab } from "./agentTypes";
import type { ProjectSeed } from "./interviewMode";

/** The AgentRef kind the pane reports to the opener: the tab's own kind
 *  (agentTypes.AGENT_PANE_TAB_KIND), so the opened document's branch
 *  origin (`agentKind`) matches the tree's `runKind` for this tab. */
export const AGENT_REPLY_AGENT_KIND = AGENT_PANE_TAB_KIND;

const REFUSAL_COPY: Record<Exclude<OpenDocumentFromAgentResult, { ok: true }>["reason"], string> = {
  document_mismatch: "That passage is in another document",
  deliverable_anchor: "Writer passages can't open here yet",
  empty_document_id: "No document named",
};

export interface AgentReplyActionsProps {
  tab: AgentPaneTab;
  actions: readonly AiAction[];
  interview: boolean;
  /** The mounted parent's originating owner and pane lease, still confirmed. */
  isCurrent: () => boolean;
  onSeedConfirm?: (seed: ProjectSeed) => void;
}

export function AgentReplyActions({ tab, actions, interview, isCurrent, onSeedConfirm }: AgentReplyActionsProps) {
  const shown = actions.filter((a) => a.kind === "open_document" || a.kind === "open_writer" || (a.kind === "project_seed" && interview));
  if (shown.length === 0) return null;
  return (
    <div className="flex flex-col gap-1.5 mt-1" data-reply-actions>
      {shown.map((action, i) => {
        if (action.kind === "open_document") return <OpenDocumentButton key={i} tab={tab} action={action} isCurrent={isCurrent} />;
        if (action.kind === "open_writer") return <OpenWriterButton key={i} action={action} />;
        if (action.kind === "project_seed") return <SeedCard key={i} action={action} onConfirm={onSeedConfirm} />;
        return null;
      })}
    </div>
  );
}

function OpenDocumentButton({ tab, action, isCurrent }: { tab: AgentPaneTab; action: Extract<AiAction, { kind: "open_document" }>; isCurrent: () => boolean }) {
  const [refusal, setRefusal] = useState<string | null>(null);
  const anchor = action.anchor;
  const admitted = () => {
    try { return typeof isCurrent === "function" && isCurrent() === true; }
    catch { return false; }
  };
  const run = () => {
    if (!admitted()) return;
    if (anchor.space !== "book") {
      setRefusal(REFUSAL_COPY.deliverable_anchor);
      return;
    }
    const result = openDocumentFromAgent({
      documentId: anchor.documentId,
      anchor,
      agent: { id: tab.id, viewId: tab.id, kind: AGENT_REPLY_AGENT_KIND },
    });
    if (!admitted()) return;
    setRefusal(result.ok ? null : REFUSAL_COPY[result.reason]);
  };
  const label = anchor.quoteHint ? `Open the passage: "${anchor.quoteHint.quote.slice(0, 60)}"` : "Open the passage";
  return (
    <div className="flex flex-col gap-0.5">
      <LemonButton variant="secondary" size="sm" onClick={run} data-reply-action="open_document">
        {label}
      </LemonButton>
      {refusal ? <p className="text-xxs text-emperor" data-reply-action-refusal>{refusal}</p> : null}
    </div>
  );
}

function OpenWriterButton({ action }: { action: Extract<AiAction, { kind: "open_writer" }> }) {
  const id = useId();
  return (
    <div className="flex flex-col gap-0.5">
      <LemonButton variant="secondary" size="sm" disabled aria-describedby={id} data-reply-action="open_writer">
        Open in the writer{action.block_id ? ` (block ${action.block_id})` : ""}
      </LemonButton>
      <p id={id} className="text-xxs text-shadow-1 dark:text-moonlight">
        No writer opener exists in the frozen contracts (openers.ts:42 refuses deliverable anchors); handoff F3.
      </p>
    </div>
  );
}

function SeedCard({ action, onConfirm }: { action: Extract<AiAction, { kind: "project_seed" }>; onConfirm?: (seed: ProjectSeed) => void }) {
  return (
    <div className="rounded border border-hairline bg-ice-1 dark:bg-charcoal-1 p-2 flex flex-col gap-1" data-seed-card>
      <p className="text-xxs uppercase tracking-wider text-shadow-1 dark:text-moonlight">Project seed</p>
      <p className="text-sm font-medium text-ink dark:text-bright">{action.title}</p>
      <p className="text-xs text-ink-soft dark:text-moonlight whitespace-pre-wrap">{action.prompt}</p>
      {action.sources?.length ? (
        <p className="text-xxs font-mono text-shadow-1 dark:text-moonlight">sources: {action.sources.join(", ")}</p>
      ) : null}
      <div>
        <LemonButton
          variant="primary"
          size="sm"
          onClick={() => onConfirm?.({ title: action.title, prompt: action.prompt, ...(action.sources ? { sources: action.sources } : {}) })}
        >
          Create this project
        </LemonButton>
      </div>
    </div>
  );
}
