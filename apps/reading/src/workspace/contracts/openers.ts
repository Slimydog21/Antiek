/**
 * contracts/openers.ts — the two opener interfaces (SPR-06 M5), plugged
 * into the existing implementations: crossPane.openDocumentInLeftPane for
 * agent → document and companionStore.openAgentTab for document → agent.
 * LAZY module. No behaviour change for existing callers: both seams keep
 * their signatures; this module only composes them with the contract types.
 */
import { useCompanion, type AgentTabKind } from "../companionStore";
import { openDocumentInLeftPane } from "../crossPane";
import { toBranchAnchor, type BookDocumentAnchor, type DocumentAnchor } from "./anchor";
import { AGENT_RUN_KIND_OF_TAB, agentViewId, type AgentScope } from "./tree";

export interface AgentRef {
  /** RUN identity (AgentNode.id). */
  id: string;
  /** VIEW identity (the companion tab id). */
  viewId: string;
  kind: AgentTabKind;
  investigationId?: string;
}

export interface OpenDocumentFromAgentRequest {
  /** Book space. */
  documentId: string;
  /** A deliverable anchor does not type-check here; untyped callers are guarded at runtime. */
  anchor?: BookDocumentAnchor;
  agent: AgentRef;
  documentTitle?: string;
}

export type OpenDocumentFromAgentResult =
  | { ok: true }
  | { ok: false; reason: "empty_document_id" | "document_mismatch" | "deliverable_anchor" };

/** → openDocumentInLeftPane(documentId, {from:"companion", investigationId?,
 *  agentTabId: viewId, agentKind: AGENT_RUN_KIND_OF_TAB[kind]}, title?,
 *  anchor ? toBranchAnchor(anchor) : undefined). Absent stays absent. */
export function openDocumentFromAgent(req: OpenDocumentFromAgentRequest): OpenDocumentFromAgentResult {
  const documentId = req.documentId.trim();
  if (!documentId) return { ok: false, reason: "empty_document_id" };
  const anchor = req.anchor as DocumentAnchor | undefined;
  if (anchor && anchor.space !== "book") return { ok: false, reason: "deliverable_anchor" };
  if (anchor && anchor.documentId !== documentId) return { ok: false, reason: "document_mismatch" };
  const investigationId = req.agent.investigationId?.trim();
  openDocumentInLeftPane(
    documentId,
    {
      from: "companion",
      ...(investigationId ? { investigationId } : {}),
      agentTabId: req.agent.viewId,
      agentKind: AGENT_RUN_KIND_OF_TAB[req.agent.kind],
    },
    req.documentTitle,
    anchor ? toBranchAnchor(anchor) : undefined,
  );
  return { ok: true };
}

export interface OpenAgentFromDocumentRequest {
  kind: AgentTabKind;
  scope: AgentScope;
  /** documentId is copied onto the descriptor ONLY when anchor.space === "book". */
  anchor?: DocumentAnchor;
  /** Required for research-thread; blank ⇒ rejected (never an `agent:thread:` collapse). */
  investigationId?: string;
  title?: string;
}

export type OpenAgentResult =
  | { ok: true; viewId: string; reused: boolean }
  | { ok: false; reason: "empty_investigation_id" | "scope_kind_mismatch" };

/** scope_kind_mismatch: kind "dialogue" with scope "project" (the dialogue
 *  agent is cross-project by construction, COMPANION_DIALOGUE_SCOPE).
 *  → useCompanion.getState().openAgentTab({kind, title, investigationId,
 *  ...(book ? {documentId} : {}), scope, ...(anchor ? {anchor} : {})}). */
export function openAgentFromDocument(req: OpenAgentFromDocumentRequest): OpenAgentResult {
  const investigationId = req.investigationId?.trim();
  if (req.kind === "research-thread" && !investigationId) return { ok: false, reason: "empty_investigation_id" };
  if (req.kind === "dialogue" && req.scope === "project") return { ok: false, reason: "scope_kind_mismatch" };
  const store = useCompanion.getState();
  const expected = agentViewId(req.kind, investigationId);
  const reused = store.tabs.some((t) => t.id === expected);
  const book = req.anchor?.space === "book" ? req.anchor : null;
  const viewId = store.openAgentTab({
    kind: req.kind,
    ...(req.title ? { title: req.title } : {}),
    ...(investigationId ? { investigationId } : {}),
    ...(book ? { documentId: book.documentId } : {}),
    scope: req.scope,
    ...(req.anchor ? { anchor: req.anchor } : {}),
  });
  return { ok: true, viewId, reused };
}
