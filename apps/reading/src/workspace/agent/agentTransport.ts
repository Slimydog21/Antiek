/**
 * agentTransport.ts — the pane's transport seam (SPR-07, fix 2).
 *
 * Today the ONE implementation posts the existing POST /thought-partner
 * and returns the whole text (`kind: "whole"`); SPR-B's SSE bridge is a
 * second implementation of the same interface. The pane renders the kind
 * out loud (AgentThread's status row), so "streaming" is never claimed
 * while the reply arrives whole.
 *
 * The wire body is EXACTLY {investigation_id, prompt, history,
 * system_context} (the AISidecar.tsx:218-230 shape minus launchFields):
 * never model_choice, never project_id (the server has no project
 * identity; scope is a line in system_context), never the raw quoteHint
 * (anchorContext.ts verifies it first).
 */
import { ApiError, apiFetch } from "../../lib/api";
import { formatReadingFocusSystemContext, type ReadingFocus } from "../../lib/readingFocus";
import { normalizeThoughtPartnerShape, type ThoughtPartnerShape } from "../../hooks/useThoughtPartnerThread";
import { findProjectPath, type AgentScope, type ContextTree, type ProjectNode } from "../contracts/tree";
import { AGENT_PANE_SCOPE } from "./agentTypes";
import { selectionContextBlock } from "./anchorContext";

export interface AgentTransportRequest {
  prompt: string;
  history: Array<{ question: string; answer: string }>;
  system_context: string;
  signal: AbortSignal;
}

export interface AgentTransportReply {
  text: string;
  shape: ThoughtPartnerShape;
  libraryRetrievalStatus?: string | null;
}

export interface AgentTransport {
  kind: "whole" | "sse";
  send(req: AgentTransportRequest): Promise<AgentTransportReply>;
}

export const thoughtPartnerTransport: AgentTransport = {
  kind: "whole",
  async send(req) {
    const resp = await apiFetch("/thought-partner", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        investigation_id: AGENT_PANE_SCOPE,
        prompt: req.prompt,
        history: req.history,
        system_context: req.system_context,
      }),
      signal: req.signal,
    });
    if (!resp.ok) {
      throw new ApiError(`POST /thought-partner failed: HTTP ${resp.status}`, resp.status, await resp.text());
    }
    const data = (await resp.json()) as { text?: string; body?: string; shape?: unknown; library_retrieval_status?: string | null };
    return {
      text: data.text ?? data.body ?? "",
      shape: normalizeThoughtPartnerShape(data.shape),
      ...(data.library_retrieval_status !== undefined ? { libraryRetrievalStatus: data.library_retrieval_status } : {}),
    };
  },
};

/** 503 (no provider configured) ⇒ null, so AIActionFailure says exactly
 *  that (CompanionAgents.tsx:130-134); otherwise the message. */
export function failureReasonOf(e: unknown): string | null {
  if (e instanceof ApiError && e.status === 503) return null;
  return e instanceof Error ? e.message : String(e);
}

const NO_TREE = "no project tree is fed in this session";

/** The SPR-06 tree, summarized for the selected project: title, sub-projects, agents. */
export function projectTreeSummary(tree: ContextTree, projectId: string): string {
  if (tree.status === "unfed") return `# PROJECT\n${NO_TREE}`;
  if (tree.status === "loading") return "# PROJECT\nthe project tree is still loading";
  if (tree.status === "error") return `# PROJECT\nthe project tree failed to load: ${tree.error ?? "unknown"}`;
  const path = findProjectPath(tree, projectId);
  if (!path) return `# PROJECT\nproject ${projectId} is not in the fed tree`;
  const node = path[path.length - 1];
  const lines = [`# PROJECT ${node.title} (${node.id})`];
  const walk = (n: ProjectNode, depth: number) => {
    for (const c of n.children) {
      lines.push(`${"  ".repeat(depth)}- sub-project: ${c.title} (${c.id})`);
      walk(c, depth + 1);
    }
    for (const a of n.agents) lines.push(`${"  ".repeat(depth)}- agent: ${a.title} [${a.runKind}${a.status ? `, ${a.status.state}` : ""}]`);
  };
  walk(node, 0);
  if (lines.length === 1) lines.push("(no sub-projects or agents yet)");
  return lines.join("\n");
}

const PANE_VOCABULARY = [
  "# ACTIONS (this pane's vocabulary)",
  "After your prose you may append one fenced `@@actions` block holding a JSON array. Kinds:",
  "  open_document {anchor}                       // anchor: {space:\"book\", documentId, kind, version, range, quoteHint}",
  "  open_writer {deliverable_id, block_id?}",
  "  project_seed {title, prompt, sources?}        // interview mode only",
  "Actions are rendered as buttons the user confirms; never assume they ran.",
].join("\n");

const INTERVIEW_LINE = "Mode: project-creation interview. Ask one question at a time; stop when something concrete arrives; offer options as an @@options card.";

export function agentSystemContext(i: {
  projectSummary: string | null;
  scope: AgentScope;
  projectId?: string;
  focus: ReadingFocus | null;
  verifiedQuote: string | null;
  interview?: boolean;
}): string {
  const parts: string[] = ["# Antiek agent pane\nYou are a thought-partner beside the user's work."];
  parts.push(i.scope === "project" ? `Scope: project ${i.projectId ?? ""}. Enforced in this browser only.` : "Scope: cross-project.");
  parts.push(i.projectSummary ?? `# PROJECT\n${NO_TREE}`);
  const reading = formatReadingFocusSystemContext(i.focus);
  if (reading) parts.push(reading);
  if (i.verifiedQuote && i.focus) {
    parts.push(selectionContextBlock({ quote: i.verifiedQuote, documentId: i.focus.documentId, pageIndex: i.focus.pageIndex }));
  }
  if (i.interview) parts.push(INTERVIEW_LINE);
  parts.push(PANE_VOCABULARY);
  return parts.join("\n\n");
}
