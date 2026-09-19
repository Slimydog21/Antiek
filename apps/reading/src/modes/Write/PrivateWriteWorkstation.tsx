import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  ApiError,
  editPrivateWriteDocument,
  getPrivateWriteDocument,
  getPrivateWriteHistory,
  getPrivateWriteRevision,
  restorePrivateWriteDocument,
  type PrivateWriteDocumentShape,
  type PrivateWriteHistoryShape,
  type PrivateWriteRevisionShape,
} from "../../lib/api";
import { useAuth } from "../../lib/auth";

type Props = { projectId?: string; writeDocumentId?: string };
type WorkState = "loading" | "ready" | "saving" | "restoring" | "conflict" | "error" | "unavailable";

const HEX64 = /^[0-9a-f]{64}$/;
const OPERATIONS = new Set([
  "accept", "undo", "create", "edit", "restore",
  "evidence_insert", "evidence_bundle", "synthesis_accept",
]);
const mutationKey = () => globalThis.crypto?.randomUUID?.() ?? `write-${Date.now()}-${Math.random().toString(16).slice(2)}`;

function validDocument(value: PrivateWriteDocumentShape, projectId: string, documentId: string): boolean {
  return value.project_id === projectId && value.write_document_id === documentId &&
    Number.isInteger(value.revision) && value.revision >= 1 && HEX64.test(value.html_sha256) &&
    typeof value.html === "string" && value.visibility === "private" &&
    (value.origin_kind === "ai_composition" || value.origin_kind === "owner_native");
}

function validRevision(value: PrivateWriteRevisionShape, includeHtml: boolean): boolean {
  const raw = value as unknown as Record<string, unknown>;
  if (!Number.isInteger(value.revision) || value.revision < 1 || !OPERATIONS.has(value.operation) ||
      !HEX64.test(value.html_sha256) || typeof value.event_id !== "string" ||
      !(value.origin_kind === "ai_composition" || value.origin_kind === "owner_native") ||
      typeof value.created_at !== "string" || typeof value.has_summary !== "boolean") return false;
  if (value.origin_kind === "owner_native") {
    if (!new Set(["create", "edit", "restore", "evidence_insert", "evidence_bundle", "synthesis_accept"]).has(value.operation) ||
        value.root_acceptance_event_id !== null || value.proposal_id !== null) return false;
  } else if (!new Set(["accept", "undo", "edit", "restore"]).has(value.operation) ||
      typeof value.root_acceptance_event_id !== "string" ||
      typeof value.proposal_id !== "string") return false;
  if (includeHtml) return typeof value.html === "string";
  return !("html" in raw) && !("summary" in raw) && !("rationale" in raw);
}

function validHistory(value: PrivateWriteHistoryShape, projectId: string, documentId: string): boolean {
  if (value.project_id !== projectId || value.write_document_id !== documentId ||
      !Number.isInteger(value.current_revision) || !Array.isArray(value.revisions) ||
      !(value.origin_kind === "ai_composition" || value.origin_kind === "owner_native")) return false;
  return value.revisions.every((revision, index) =>
    validRevision(revision, false) && revision.revision === index + 1 &&
      revision.origin_kind === value.origin_kind,
  ) && value.revisions.at(-1)?.revision === value.current_revision;
}

async function getCompleteHistory(
  projectId: string, documentId: string, signal: AbortSignal,
): Promise<PrivateWriteHistoryShape> {
  const revisions: PrivateWriteRevisionShape[] = [];
  let currentRevision: number | null = null;
  let currentOrigin: PrivateWriteHistoryShape["origin_kind"] | null = null;
  for (let pageNumber = 0; pageNumber < 2_000; pageNumber += 1) {
    const page = await getPrivateWriteHistory(projectId, documentId, signal, revisions.length, 500);
    if (page.project_id !== projectId || page.write_document_id !== documentId ||
        !Number.isInteger(page.current_revision) || page.current_revision < 1 ||
        (currentRevision !== null && page.current_revision !== currentRevision) ||
        !(page.origin_kind === "ai_composition" || page.origin_kind === "owner_native") ||
        (currentOrigin !== null && page.origin_kind !== currentOrigin) ||
        !Array.isArray(page.revisions)) throw new Error("Private Write history page is inconsistent");
    currentRevision = page.current_revision;
    currentOrigin = page.origin_kind;
    for (const item of page.revisions) {
      if (!validRevision(item, false) || item.revision !== revisions.length + 1) {
        throw new Error("Private Write history continuity failed");
      }
      if (item.origin_kind !== currentOrigin) throw new Error("Private Write history origin changed");
      revisions.push(item);
    }
    if (revisions.length === currentRevision) {
      return { project_id: projectId, write_document_id: documentId,
        current_revision: currentRevision, origin_kind: currentOrigin, revisions };
    }
    if (page.revisions.length === 0 || revisions.length > currentRevision) {
      throw new Error("Private Write history page made no progress");
    }
  }
  throw new Error("Private Write history exceeds the bounded page walk");
}

const shortHash = (value: string | null) => value ? value.slice(0, 8) : "origin";

export default function PrivateWriteWorkstation({ projectId, writeDocumentId }: Props) {
  const { sessionGeneration } = useAuth();
  const [document, setDocument] = useState<PrivateWriteDocumentShape | null>(null);
  const [history, setHistory] = useState<PrivateWriteRevisionShape[]>([]);
  const [source, setSource] = useState("");
  const [selectedRevision, setSelectedRevision] = useState<number | null>(null);
  const [historical, setHistorical] = useState<PrivateWriteRevisionShape | null>(null);
  const [view, setView] = useState<"source" | "rendered">("source");
  const [state, setState] = useState<WorkState>("loading");
  const [message, setMessage] = useState("");
  const [restoreTarget, setRestoreTarget] = useState<number | null>(null);
  const context = useRef({ projectId, writeDocumentId, sessionGeneration, generation: 0 });
  const exactAbort = useRef<AbortController | null>(null);
  const hydrateAbort = useRef<AbortController | null>(null);
  const mutationOwner = useRef<string | null>(null);
  const dialogRef = useRef<HTMLDivElement | null>(null);
  const backgroundRef = useRef<HTMLDivElement | null>(null);
  const restoreInvokerRef = useRef<HTMLButtonElement | null>(null);

  const hydrate = useCallback(async (preserveDraftOnFailure = false) => {
    if (!projectId || !writeDocumentId) { setState("unavailable"); return; }
    const generation = context.current.generation + 1;
    context.current = { projectId, writeDocumentId, sessionGeneration, generation };
    exactAbort.current?.abort(); hydrateAbort.current?.abort();
    setState("loading"); setMessage("");
    if (!preserveDraftOnFailure) { setHistorical(null); setSelectedRevision(null); }
    const abort = new AbortController();
    hydrateAbort.current = abort;
    try {
      const [nextDocument, nextHistory] = await Promise.all([
        getPrivateWriteDocument(projectId, writeDocumentId, abort.signal),
        getCompleteHistory(projectId, writeDocumentId, abort.signal),
      ]);
      const live = context.current;
      if (live.generation !== generation || live.sessionGeneration !== sessionGeneration ||
          live.projectId !== projectId || live.writeDocumentId !== writeDocumentId) return;
      if (!validDocument(nextDocument, projectId, writeDocumentId) ||
          !validHistory(nextHistory, projectId, writeDocumentId) ||
          nextHistory.current_revision !== nextDocument.revision ||
          nextHistory.origin_kind !== nextDocument.origin_kind ||
          nextHistory.revisions.at(-1)?.html_sha256 !== nextDocument.html_sha256) {
        throw new Error("Private Write authority response is inconsistent");
      }
      setDocument(nextDocument); setHistory(nextHistory.revisions); setSource(nextDocument.html);
      setSelectedRevision(nextDocument.revision); setState("ready");
    } catch (error: unknown) {
      if ((error as { name?: string }).name === "AbortError") return;
      const live = context.current;
      if (live.generation !== generation || live.sessionGeneration !== sessionGeneration ||
          live.projectId !== projectId || live.writeDocumentId !== writeDocumentId) return;
      if (preserveDraftOnFailure) {
        setState("conflict");
        setMessage("Reload failed. Your draft is still here; retry when the authority is reachable.");
      } else {
        setDocument(null); setHistory([]); setSource(""); setState("unavailable");
        setMessage("This private manuscript is unavailable or its authority could not be verified.");
      }
    }
  }, [projectId, sessionGeneration, writeDocumentId]);

  useEffect(() => {
    setDocument(null); setHistory([]); setSource(""); setHistorical(null);
    setRestoreTarget(null); mutationOwner.current = null;
    void hydrate();
    return () => { context.current.generation += 1; exactAbort.current?.abort(); hydrateAbort.current?.abort(); };
  }, [hydrate]);

  const selectRevision = useCallback(async (revision: PrivateWriteRevisionShape) => {
    if (!projectId || !writeDocumentId || !document) return;
    exactAbort.current?.abort(); setHistorical(null); setSelectedRevision(revision.revision);
    if (revision.revision === document.revision) return;
    const abort = new AbortController(); exactAbort.current = abort;
    const request = { ...context.current };
    try {
      const exact = await getPrivateWriteRevision(projectId, writeDocumentId, revision.revision, abort.signal);
      if (abort.signal.aborted || request.generation !== context.current.generation ||
          request.sessionGeneration !== context.current.sessionGeneration ||
          request.projectId !== context.current.projectId ||
          request.writeDocumentId !== context.current.writeDocumentId) return;
      if (!validRevision(exact, true) || exact.revision !== revision.revision ||
          exact.html_sha256 !== revision.html_sha256 || exact.is_current !== false ||
          exact.project_id !== projectId || exact.write_document_id !== writeDocumentId) {
        throw new Error("Historical revision response is inconsistent");
      }
      setHistorical(exact);
    } catch (error: unknown) {
      if ((error as { name?: string }).name === "AbortError") return;
      if (request.generation !== context.current.generation ||
          request.sessionGeneration !== context.current.sessionGeneration ||
          request.projectId !== context.current.projectId ||
          request.writeDocumentId !== context.current.writeDocumentId) return;
      setMessage("That historical revision could not be verified."); setState("error");
    }
  }, [document, projectId, writeDocumentId]);

  const save = useCallback(async () => {
    if (!projectId || !writeDocumentId || !document || mutationOwner.current !== null ||
        selectedRevision !== document.revision || source === document.html || state === "conflict") return;
    const owner = mutationKey(); mutationOwner.current = owner; setState("saving"); setMessage("");
    const request = { ...context.current };
    try {
      const saved = await editPrivateWriteDocument(projectId, writeDocumentId, {
        base_revision: document.revision, base_html_sha256: document.html_sha256, html: source,
      }, mutationKey());
      if (request.generation !== context.current.generation ||
          request.sessionGeneration !== context.current.sessionGeneration) return;
      if (saved.write_document_id !== writeDocumentId || saved.project_id !== projectId ||
          saved.prior_revision !== document.revision || saved.revision !== document.revision + 1 ||
          saved.visibility !== "private" || !HEX64.test(saved.html_sha256)) {
        throw new Error("Save receipt is inconsistent");
      }
      await hydrate();
      if (context.current.projectId === projectId && context.current.writeDocumentId === writeDocumentId &&
          context.current.sessionGeneration === sessionGeneration) setMessage("Revision saved.");
    } catch (error: unknown) {
      if (request.generation !== context.current.generation ||
          request.sessionGeneration !== context.current.sessionGeneration ||
          request.projectId !== context.current.projectId ||
          request.writeDocumentId !== context.current.writeDocumentId) return;
      if (error instanceof ApiError && error.status === 409) {
        setState("conflict"); setMessage("The manuscript changed elsewhere. Your draft is still here; reload current before saving.");
      } else { setState("error"); setMessage("Save failed. Your draft remains in this panel."); }
    } finally { if (mutationOwner.current === owner) mutationOwner.current = null; }
  }, [document, hydrate, projectId, selectedRevision, sessionGeneration, source, state, writeDocumentId]);

  const restore = useCallback(async () => {
    if (!projectId || !writeDocumentId || !document || restoreTarget === null || mutationOwner.current !== null) return;
    const owner = mutationKey(); mutationOwner.current = owner; setState("restoring"); setMessage("");
    const target = restoreTarget; const request = { ...context.current };
    try {
      const restored = await restorePrivateWriteDocument(projectId, writeDocumentId, {
        base_revision: document.revision, base_html_sha256: document.html_sha256,
        target_revision: target,
      }, mutationKey());
      if (request.generation !== context.current.generation ||
          request.sessionGeneration !== context.current.sessionGeneration ||
          request.projectId !== context.current.projectId ||
          request.writeDocumentId !== context.current.writeDocumentId) return;
      if (restored.operation !== "restore" || restored.target_revision !== target ||
          restored.project_id !== projectId || restored.write_document_id !== writeDocumentId ||
          restored.visibility !== "private" || !HEX64.test(restored.html_sha256) ||
          restored.prior_revision !== document.revision || restored.revision !== document.revision + 1) {
        throw new Error("Restore receipt is inconsistent");
      }
      setRestoreTarget(null); await hydrate();
      if (context.current.projectId === projectId && context.current.writeDocumentId === writeDocumentId &&
          context.current.sessionGeneration === sessionGeneration) {
        setMessage(`Revision ${target} restored as a new revision.`);
      }
    } catch (error: unknown) {
      if (request.generation !== context.current.generation ||
          request.sessionGeneration !== context.current.sessionGeneration ||
          request.projectId !== context.current.projectId ||
          request.writeDocumentId !== context.current.writeDocumentId) return;
      setRestoreTarget(null);
      if (error instanceof ApiError && error.status === 409) {
        setState("conflict"); setMessage("The manuscript changed elsewhere. Reload current before restoring.");
      } else { setState("error"); setMessage("Restore failed. No local manuscript bytes were replaced."); }
    } finally { if (mutationOwner.current === owner) mutationOwner.current = null; }
  }, [document, hydrate, projectId, restoreTarget, sessionGeneration, writeDocumentId]);

  useEffect(() => {
    if (restoreTarget === null) {
      backgroundRef.current?.removeAttribute("inert");
      restoreInvokerRef.current?.focus(); return;
    }
    backgroundRef.current?.setAttribute("inert", "");
    const dialog = dialogRef.current; const buttons = dialog?.querySelectorAll<HTMLButtonElement>("button");
    buttons?.[0]?.focus();
    const keydown = (event: KeyboardEvent) => {
      if (event.key === "Escape") { event.preventDefault(); setRestoreTarget(null); return; }
      if (event.key !== "Tab" || !buttons?.length) return;
      const first = buttons[0]; const last = buttons[buttons.length - 1];
      if (event.shiftKey && globalThis.document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && globalThis.document.activeElement === last) { event.preventDefault(); first.focus(); }
    };
    dialog?.addEventListener("keydown", keydown);
    return () => { dialog?.removeEventListener("keydown", keydown); backgroundRef.current?.removeAttribute("inert"); };
  }, [restoreTarget]);

  const dirty = Boolean(document && source !== document.html);
  const showingCurrent = Boolean(document && selectedRevision === document.revision);
  const displayHtml = showingCurrent ? (dirty ? "" : document?.html ?? "") : historical?.html ?? "";
  const status = state === "loading" ? "Loading authority…" : state === "saving" ? "Saving revision…" :
    state === "restoring" ? "Restoring revision…" : state === "conflict" || state === "error" ||
      state === "unavailable" ? message : dirty ? "Unsaved changes" : message;
  const selectedMeta = useMemo(
    () => history.find((item) => item.revision === selectedRevision) ?? null,
    [history, selectedRevision],
  );

  if (!projectId || !writeDocumentId) return <div className="h-full p-4 text-xs italic">No private Write document loaded.</div>;
  return (
    <div className="relative h-full min-h-0 flex flex-col bg-ice-0 text-ink-1 dark:bg-charcoal-2 dark:text-ice-0" data-private-write-workstation>
      <div ref={backgroundRef} className="contents">
      <header className="flex flex-wrap items-center gap-3 border-b border-rule px-4 py-3 dark:border-charcoal-1">
        <div className="min-w-0 flex-1">
          <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-ink-3">Private Write · {document?.origin_kind === "owner_native" ? "Owner-native" : "Evidence-derived"} · revision desk</p>
          <h2 className="truncate font-serif text-lg">{document?.title ?? "Verifying manuscript"}</h2>
        </div>
        <div className="flex items-center gap-1 rounded border border-rule p-1 dark:border-charcoal-1" aria-label="Manuscript view">
          {(["source", "rendered"] as const).map((choice) => <button key={choice} type="button" onClick={() => setView(choice)} aria-pressed={view === choice} className="px-2 py-1 font-mono text-[10px] uppercase focus-visible:outline focus-visible:outline-2">{choice}</button>)}
        </div>
        <button type="button" onClick={() => void save()} disabled={!dirty || !showingCurrent || state === "loading" || state === "saving" || state === "restoring" || state === "conflict"} className="border border-ink-1 px-3 py-1.5 font-mono text-xs disabled:opacity-40 dark:border-ice-0 focus-visible:outline focus-visible:outline-2">Save revision</button>
      </header>
      <div className="flex min-h-0 flex-1 flex-col-reverse md:flex-row">
        <main className="min-h-0 min-w-0 flex-1 flex flex-col">
          <div className="flex items-center justify-between border-b border-rule px-4 py-2 font-mono text-[10px] dark:border-charcoal-1">
            <span>{showingCurrent ? `Current · r${document?.revision ?? "—"}` : selectedMeta ? `Historical · r${selectedMeta.revision}` : "Select a revision"}</span>
            <span>{selectedMeta ? `${selectedMeta.operation} · ${shortHash(selectedMeta.html_sha256)}` : ""}</span>
          </div>
          {view === "source" ? <textarea aria-label="Private Write HTML source" value={showingCurrent ? source : historical?.html ?? ""} onChange={(event) => showingCurrent && setSource(event.target.value)} disabled={!showingCurrent || state === "loading" || state === "unavailable" || state === "conflict"} spellCheck={false} className="min-h-0 flex-1 resize-none bg-transparent p-4 font-mono text-xs leading-5 outline-none focus-visible:ring-2 focus-visible:ring-inset disabled:opacity-70" /> :
            <div className="relative min-h-0 flex-1"><iframe title={showingCurrent ? "Current manuscript preview" : `Historical manuscript revision ${selectedRevision}`} sandbox="" srcDoc={displayHtml} className="h-full min-h-0 w-full bg-white" />{showingCurrent && dirty && <div className="absolute inset-0 grid place-items-center bg-ice-0 p-6 text-center text-sm text-ink-2"><p>Save this revision before rendering it. Preview only opens server-admitted HTML.</p></div>}</div>}
          {!showingCurrent && historical && <div className="flex items-center justify-between border-t border-rule px-4 py-2 dark:border-charcoal-1"><span className="font-mono text-[10px]">{dirty ? "Save the current draft before restoring history." : "Read-only historical bytes; not persisted locally."}</span><button ref={restoreInvokerRef} type="button" disabled={dirty} onClick={() => setRestoreTarget(historical.revision)} className="border border-rule px-3 py-1 font-mono text-xs disabled:opacity-40 focus-visible:outline focus-visible:outline-2 dark:border-charcoal-1">Restore this revision</button></div>}
        </main>
        <aside className="w-full shrink-0 border-b border-rule md:w-[260px] md:border-b-0 md:border-l dark:border-charcoal-1" aria-label="Revision history">
          <div className="flex items-center justify-between px-3 py-2"><h3 className="font-mono text-[10px] uppercase tracking-[0.16em]">Revision strata</h3><span className="font-mono text-[10px]">{history.length}</span></div>
          <ol className="flex max-h-32 gap-2 overflow-auto px-3 pb-3 md:max-h-none md:flex-col md:border-l md:border-sky-6/50 md:ml-5 md:pl-3">
            {history.map((revision) => <li key={revision.event_id} className="shrink-0"><button type="button" onClick={() => void selectRevision(revision)} aria-current={revision.revision === document?.revision ? "step" : undefined} aria-pressed={revision.revision === selectedRevision} className="w-40 border border-rule px-2 py-2 text-left md:w-full dark:border-charcoal-1 focus-visible:outline focus-visible:outline-2"><span className="flex justify-between font-mono text-[10px]"><b>r{revision.revision}</b><span>{shortHash(revision.html_sha256)}</span></span><span className="mt-1 block font-serif text-sm capitalize">{revision.operation}</span>{revision.target_revision !== null && <span className="font-mono text-[9px]">from r{revision.target_revision}</span>}</button></li>)}
          </ol>
        </aside>
      </div>
      <footer className="flex min-h-9 items-center justify-between gap-3 border-t border-rule px-4 py-2 dark:border-charcoal-1"><span role="status" aria-live="polite" className="font-mono text-[10px]">{status}</span>{state === "conflict" && <button type="button" onClick={() => void hydrate(true)} className="font-mono text-xs underline focus-visible:outline focus-visible:outline-2">Reload current</button>}</footer>
      </div>
      {restoreTarget !== null && <div className="absolute inset-0 z-50 grid place-items-center bg-charcoal-2/60 p-4"><div ref={dialogRef} role="dialog" aria-modal="true" aria-labelledby="restore-title" className="max-w-sm border border-rule bg-ice-0 p-5 text-ink-1 shadow-xl dark:border-charcoal-1 dark:bg-charcoal-2 dark:text-ice-0"><p className="font-mono text-[10px] uppercase tracking-[0.18em]">Immutable restore</p><h3 id="restore-title" className="mt-1 font-serif text-xl">Restore revision {restoreTarget}?</h3><p className="mt-2 text-sm">Revision {document?.revision} remains in history. Antiek will append the selected bytes as a new revision.</p><div className="mt-5 flex justify-end gap-2"><button type="button" onClick={() => setRestoreTarget(null)} className="border border-rule px-3 py-1.5 text-xs dark:border-charcoal-1">Cancel</button><button type="button" onClick={() => void restore()} className="border border-ink-1 bg-ink-1 px-3 py-1.5 text-xs text-ice-0 dark:border-ice-0">Restore as new revision</button></div></div></div>}
    </div>
  );
}
