import { useEffect } from "react";

import { getWorkspaceResume, putWorkspaceResume, type WorkspaceResumeEntry } from "../api/workspaceResume";
import { parseHtmlDocumentResumeRef } from "../api/htmlDocumentRefs";
import { parseDeepResearchSessionResumeRef } from "../api/deepResearchSessionRefs";
import { openWindow } from "../components/windows/openWindow";
import { toast } from "../components/lemon/LemonToast";
import { ApiError } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useWindows, type WorkspaceWindowDescriptor } from "./windowsStore";

export function checkpointKey(entry: WorkspaceResumeEntry): string {
  if (entry.kind === "subaction") return `subaction:${entry.workflow}`;
  if (entry.kind === "research_artifact") return `research_artifact:${entry.investigation_id}`;
  if (entry.kind === "hosted_html_document") {
    return `hosted_html_document:${entry.resolver}:${entry.document_id}`;
  }
  if (entry.kind === "deep_research_session") return `deep_research_session:${entry.session_id}`;
  if (entry.kind === "collective_unit") return `collective_unit:${entry.manifest_id}`;
  if (entry.kind === "ancestry_interrogation") {
    return `ancestry_interrogation:${JSON.stringify([entry.investigation_id, entry.manifest_id, entry.receipt_id])}`;
  }
  if (entry.kind === "collective_council") return `collective_council:${entry.plan_id}`;
  return entry.kind;
}

/** Stable, non-display identifier that keeps resolver/document bytes out of window IDs. */
export function hostedDocumentWindowId(resolver: string, documentId: string): string {
  const bytes = new TextEncoder().encode(`${resolver}\u0000${documentId}`);
  let first = 0x811c9dc5;
  let second = 0x9e3779b9;
  for (const byte of bytes) {
    first = Math.imul(first ^ byte, 0x01000193) >>> 0;
    second = Math.imul(second ^ byte, 0x85ebca6b) >>> 0;
  }
  return `win:hosted_html_document:${first.toString(16).padStart(8, "0")}${second.toString(16).padStart(8, "0")}`;
}

export function deepResearchSessionWindowId(sessionId: string): string {
  const bytes = new TextEncoder().encode(sessionId);
  let first = 0x811c9dc5; let second = 0x9e3779b9;
  for (const byte of bytes) { first = Math.imul(first ^ byte, 0x01000193) >>> 0; second = Math.imul(second ^ byte, 0x85ebca6b) >>> 0; }
  return `win:deep_research_session:${first.toString(16).padStart(8, "0")}${second.toString(16).padStart(8, "0")}`;
}

function isCheckpointIdentifier(value: unknown): value is string {
  return typeof value === "string"
    && value.length > 0
    && value.length <= 512
    && value === value.trim()
    && !/[\u0000-\u001f\u007f]/u.test(value);
}

function entryFor(window: WorkspaceWindowDescriptor): WorkspaceResumeEntry | null {
  if (window.kind === "stats" || window.kind === "library") return { kind: window.kind };
  if (window.kind === "subaction" && ["research", "read", "write", "speak"].includes(String(window.payload.workflow))) {
    return { kind: "subaction", workflow: window.payload.workflow as "research" | "read" | "write" | "speak" };
  }
  if (window.kind === "research_artifact" && typeof window.payload.investigationId === "string" && window.payload.investigationId) {
    return { kind: "research_artifact", investigation_id: window.payload.investigationId };
  }
  if (window.kind === "hosted_html_document") {
    const reference = parseHtmlDocumentResumeRef(window.payload.resume_ref);
    if (reference) return { kind: "hosted_html_document", ...reference };
  }
  if (window.kind === "deep_research_session") {
    const reference = parseDeepResearchSessionResumeRef(
      window.payload.resume_ref ?? window.payload.workspace_resume_ref,
    );
    if (reference) return { kind: "deep_research_session", session_id: reference.session_id };
  }
  if (window.kind === "collective_unit" && typeof window.payload.resume_ref === "object" && window.payload.resume_ref !== null) {
    const resume = window.payload.resume_ref as Record<string, unknown>;
    const interrogation = window.payload.interrogation_ref;
    if (interrogation !== undefined) {
      if (
        Object.keys(resume).length !== 1
        || !isCheckpointIdentifier(resume.manifest_id)
        || typeof interrogation !== "object"
        || interrogation === null
        || Array.isArray(interrogation)
      ) return null;
      const exact = interrogation as Record<string, unknown>;
      if (
        Object.keys(exact).length !== 2
        || !isCheckpointIdentifier(exact.investigation_id)
        || !isCheckpointIdentifier(exact.receipt_id)
      ) return null;
      return {
        kind: "ancestry_interrogation",
        investigation_id: exact.investigation_id,
        manifest_id: resume.manifest_id,
        receipt_id: exact.receipt_id,
      };
    }
    if (Object.keys(resume).length === 1 && isCheckpointIdentifier(resume.manifest_id)) return { kind: "collective_unit", manifest_id: resume.manifest_id };
  }
  if (window.kind === "collective_council" && typeof window.payload.resume_ref === "object" && window.payload.resume_ref !== null) {
    const id = (window.payload.resume_ref as { plan_id?: unknown }).plan_id;
    if (typeof id === "string" && id) return { kind: "collective_council", plan_id: id };
  }
  return null;
}

export function semanticEntries(
  windows: Record<string, WorkspaceWindowDescriptor>,
  semanticOrder: string[],
): WorkspaceResumeEntry[] {
  const current = new Map<string, WorkspaceResumeEntry>();
  for (const window of Object.values(windows)) {
    const entry = entryFor(window);
    if (entry) current.set(checkpointKey(entry), entry);
  }
  return semanticOrder.flatMap((key) => current.has(key) ? [current.get(key)!] : []).slice(0, 8);
}

export function replayWorkspace(entries: WorkspaceResumeEntry[]): void {
  const store = useWindows.getState();
  for (const id of Object.keys(store.windows)) {
    if (entryFor(store.windows[id])) store.close(id);
  }
  for (const entry of entries) {
    if (entry.kind === "stats" || entry.kind === "library") openWindow(entry.kind, {}, { id: `win:${entry.kind}` });
    else if (entry.kind === "subaction") openWindow("subaction", { workflow: entry.workflow }, { id: `win:subaction:${entry.workflow}` });
    else if (entry.kind === "research_artifact") openWindow("research_artifact", { investigationId: entry.investigation_id }, { id: `win:research_artifact:${entry.investigation_id}` });
    else if (entry.kind === "hosted_html_document") {
      const resume_ref = { resolver: entry.resolver, document_id: entry.document_id } as const;
      openWindow(
        "hosted_html_document",
        { document_id: entry.document_id, resume_ref },
        {
          id: hostedDocumentWindowId(entry.resolver, entry.document_id),
          title: "Hosted document",
        },
      );
    } else if (entry.kind === "deep_research_session") {
      const resume_ref = { session_id: entry.session_id } as const;
      openWindow("deep_research_session", { resume_ref }, {
        id: deepResearchSessionWindowId(entry.session_id), title: "Deep research", mode: "floating",
      });
    } else if (entry.kind === "collective_unit") {
      openWindow("collective_unit", { resume_ref: { manifest_id: entry.manifest_id } }, { id: deepResearchSessionWindowId(`collective:${entry.manifest_id}`), title: "Collective research", mode: "floating" });
    } else if (entry.kind === "ancestry_interrogation") {
      openWindow("collective_unit", {
        resume_ref: { manifest_id: entry.manifest_id },
        interrogation_ref: { investigation_id: entry.investigation_id, receipt_id: entry.receipt_id },
      }, { id: deepResearchSessionWindowId(`interrogation:${entry.receipt_id}`), title: "Reasoning ancestry collective", mode: "floating" });
    } else {
      openWindow("collective_council", { resume_ref: { plan_id: entry.plan_id } }, { id: deepResearchSessionWindowId(`council:${entry.plan_id}`), title: "Research council", mode: "floating" });
    }
  }
}

export function useWorkspaceResume(): void {
  const { state, sessionGeneration } = useAuth();

  useEffect(() => {
    if (state.status !== "authenticated") return;
    const generation = sessionGeneration;
    const abort = new AbortController();
    let active = true;
    let hydrating = true;
    let revision = 0;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let semanticOrder: string[] = [];
    let lastFingerprint = "";

    const current = () => active && !abort.signal.aborted && generation === sessionGeneration;
    const unsubscribe = useWindows.subscribe((snapshot) => {
      if (hydrating || !current()) return;
      const present = Object.values(snapshot.windows).flatMap((window) => {
        const entry = entryFor(window); return entry ? [checkpointKey(entry)] : [];
      });
      semanticOrder = [...semanticOrder.filter((key) => present.includes(key)), ...present.filter((key) => !semanticOrder.includes(key))];
      const entries = semanticEntries(snapshot.windows, semanticOrder);
      const fingerprint = JSON.stringify(entries);
      if (fingerprint === lastFingerprint) return;
      lastFingerprint = fingerprint;
      if (timer) clearTimeout(timer);
      const mutationKey = crypto.randomUUID();
      timer = setTimeout(() => {
        void putWorkspaceResume({ schema_version: 1, base_revision: revision, entries, mutation_key: mutationKey }, abort.signal)
          .then((receipt) => { if (current()) revision = receipt.revision; })
          .catch(async (error: unknown) => {
            if (!current()) return;
            if (error instanceof ApiError && error.status === 409) {
              try { const latest = await getWorkspaceResume(abort.signal); if (current()) revision = latest.revision; } catch { /* surfaced below */ }
              toast.warn("Workspace changed on another device. Your local window change was not synced; review the latest workspace and try again.");
            }
          });
      }, 250);
    });

    void getWorkspaceResume(abort.signal).then((checkpoint) => {
      if (!current()) return;
      revision = checkpoint.revision;
      semanticOrder = checkpoint.entries.map(checkpointKey);
      replayWorkspace(checkpoint.entries);
      lastFingerprint = JSON.stringify(checkpoint.entries);
      hydrating = false;
    }).catch(() => { if (current()) hydrating = false; });

    return () => {
      active = false;
      abort.abort();
      if (timer) clearTimeout(timer);
      unsubscribe();
    };
  }, [sessionGeneration, state.status]);
}
