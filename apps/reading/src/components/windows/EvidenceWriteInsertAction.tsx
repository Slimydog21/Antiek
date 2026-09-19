import { useEffect, useRef, useState } from "react";

import {
  applyPrivateWriteEvidenceInsertion,
  listPrivateWriteDocuments,
  previewPrivateWriteEvidenceInsertion,
  type PrivateWriteDocumentSummaryShape,
  type WriteCitationEvidenceShape,
  type WriteEvidencePreviewShape,
} from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { useWorkspace } from "../../workspace/WorkspaceStore";

const HEX64 = /^[0-9a-f]{64}$/;
const mutationKey = () => globalThis.crypto?.randomUUID?.() ??
  `evidence-insert-${Date.now()}-${Math.random().toString(16).slice(2)}`;

export function EvidenceWriteInsertAction({ evidence }: { evidence: WriteCitationEvidenceShape }) {
  const { sessionGeneration } = useAuth();
  const openPanel = useWorkspace((state) => state.open);
  const [open, setOpen] = useState(false);
  const [documents, setDocuments] = useState<PrivateWriteDocumentSummaryShape[]>([]);
  const [selected, setSelected] = useState("");
  const [preview, setPreview] = useState<WriteEvidencePreviewShape | null>(null);
  const [state, setState] = useState<"idle" | "loading" | "previewing" | "applying" | "error">("idle");
  const [message, setMessage] = useState("");
  const abortRef = useRef<AbortController | null>(null);
  const keyRef = useRef("");
  const generationRef = useRef(sessionGeneration);
  const invokerRef = useRef<HTMLButtonElement | null>(null);
  const dialogRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (generationRef.current !== sessionGeneration) {
      generationRef.current = sessionGeneration; abortRef.current?.abort(); setOpen(false);
      setDocuments([]); setSelected(""); setPreview(null); setMessage(""); setState("idle");
    }
    return () => abortRef.current?.abort();
  }, [sessionGeneration]);

  useEffect(() => {
    if (!open) { invokerRef.current?.focus(); return; }
    dialogRef.current?.querySelector<HTMLElement>("select,button")?.focus();
    const keydown = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape" && state !== "applying" && state !== "previewing") {
        event.preventDefault(); setOpen(false); return;
      }
      if (event.key !== "Tab") return;
      const controls = dialogRef.current?.querySelectorAll<HTMLElement>("select,button:not([disabled])");
      if (!controls?.length) return;
      const first = controls[0]; const last = controls[controls.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    };
    const dialog = dialogRef.current; dialog?.addEventListener("keydown", keydown);
    return () => dialog?.removeEventListener("keydown", keydown);
  }, [open, state]);

  const begin = async () => {
    setOpen(true); setState("loading"); setMessage(""); setPreview(null); keyRef.current = mutationKey();
    const generation = sessionGeneration; const abort = new AbortController(); abortRef.current = abort;
    try {
      const found: PrivateWriteDocumentSummaryShape[] = []; let cursor = "";
      for (let pageIndex = 0; pageIndex < 100; pageIndex += 1) {
        const page = await listPrivateWriteDocuments(abort.signal, cursor, 100);
        const native = page.documents.filter((item) => item.origin_kind === "owner_native");
        found.push(...native);
        if (page.next_after_document_id === null) break;
        if (!page.documents.length || page.next_after_document_id <= cursor) throw new Error("Manuscript list did not advance");
        cursor = page.next_after_document_id;
      }
      if (abort.signal.aborted || generationRef.current !== generation) return;
      setDocuments(found); setSelected(found[0]?.write_document_id ?? ""); setState("idle");
    } catch (caught: unknown) {
      if ((caught as { name?: string }).name === "AbortError") return;
      setState("error"); setMessage(caught instanceof Error ? caught.message : "Manuscripts unavailable");
    }
  };

  const target = documents.find((item) => item.write_document_id === selected);
  const request = target ? {
    base_revision: target.revision, base_html_sha256: target.html_sha256,
    citation_evidence: evidence,
  } : null;

  const makePreview = async () => {
    if (!target || !request || state === "previewing") return;
    setState("previewing"); setMessage(""); const generation = sessionGeneration;
    const abort = new AbortController(); abortRef.current = abort;
    try {
      const value = await previewPrivateWriteEvidenceInsertion(
        target.project_id, target.write_document_id, request, abort.signal,
      );
      if (abort.signal.aborted || generationRef.current !== generation) return;
      if (value.write_document_id !== target.write_document_id || value.project_id !== target.project_id ||
          value.base_revision !== target.revision || value.base_html_sha256 !== target.html_sha256 ||
          value.origin_kind !== "owner_native" || value.visibility !== "private" ||
          !HEX64.test(value.preview_sha256) || !HEX64.test(value.proposed_html_sha256) ||
          value.citation_receipt_sha256 !== evidence.receipt_sha256) {
        throw new Error("Evidence preview receipt is inconsistent");
      }
      setPreview(value); setState("idle");
    } catch (caught: unknown) {
      if ((caught as { name?: string }).name === "AbortError") return;
      setState("error"); setMessage(caught instanceof Error ? caught.message : "Preview failed");
    }
  };

  const apply = async () => {
    if (!target || !request || !preview || state === "applying") return;
    setState("applying"); setMessage(""); const generation = sessionGeneration;
    const abort = new AbortController(); abortRef.current = abort;
    try {
      const result = await applyPrivateWriteEvidenceInsertion(
        target.project_id, target.write_document_id,
        { ...request, preview_sha256: preview.preview_sha256,
          proposed_html_sha256: preview.proposed_html_sha256 }, keyRef.current, abort.signal,
      );
      if (abort.signal.aborted || generationRef.current !== generation) return;
      if (result.project_id !== target.project_id || result.write_document_id !== target.write_document_id ||
          result.operation !== "evidence_insert" || result.prior_revision !== target.revision ||
          result.revision !== target.revision + 1 || !HEX64.test(result.html_sha256)) {
        throw new Error("Evidence insertion receipt is inconsistent");
      }
      openPanel("PrivateWrite", { projectId: target.project_id, writeDocumentId: target.write_document_id }, {
        mode: "floating", title: target.title,
        id: `PrivateWrite:${target.project_id}:${target.write_document_id}`,
      });
      setOpen(false);
    } catch (caught: unknown) {
      if ((caught as { name?: string }).name === "AbortError") return;
      setState("error"); setMessage(caught instanceof Error ? caught.message : "Insertion failed");
    }
  };

  return <>
    <button ref={invokerRef} type="button" onClick={() => void begin()}>Insert evidence into manuscript</button>
    {open ? <div className="fixed inset-0 z-[120] grid place-items-center bg-charcoal-2/60 p-4">
      <div ref={dialogRef} role="dialog" aria-modal="true" aria-labelledby="evidence-write-title" className="w-full max-w-2xl border border-rule bg-ice-0 p-5 text-ink shadow-xl dark:bg-charcoal-2 dark:text-bright">
        <h2 id="evidence-write-title" className="font-serif text-xl">Insert cited evidence</h2>
        <label className="mt-4 block text-xs" htmlFor="evidence-write-target">Owner-native manuscript</label>
        <select id="evidence-write-target" value={selected} disabled={state === "loading" || state === "applying"} onChange={(event) => { setSelected(event.target.value); setPreview(null); }} className="mt-1 w-full border border-rule bg-transparent p-2">
          {!documents.length ? <option value="">No owner-native manuscripts</option> : null}
          {documents.map((item) => <option key={item.write_document_id} value={item.write_document_id}>{item.title} · r{item.revision}</option>)}
        </select>
        {preview ? <div className="mt-4"><p className="text-xs">Source: {preview.source_title}</p><iframe title="Evidence insertion preview" sandbox="" srcDoc={preview.proposed_html} className="mt-2 h-64 w-full border border-rule" /></div> : null}
        {message ? <p role="alert" className="mt-3 text-xs text-danger">{message}</p> : null}
        <div className="mt-5 flex justify-end gap-2">
          <button type="button" disabled={state === "applying" || state === "previewing"} onClick={() => setOpen(false)}>Cancel</button>
          {!preview ? <button type="button" disabled={!target || state === "loading" || state === "previewing"} onClick={() => void makePreview()}>{state === "previewing" ? "Previewing…" : "Preview insertion"}</button> : null}
          {preview ? <button type="button" disabled={state === "applying"} onClick={() => void apply()}>{state === "applying" ? "Inserting…" : "Insert as new revision"}</button> : null}
        </div>
      </div>
    </div> : null}
  </>;
}
