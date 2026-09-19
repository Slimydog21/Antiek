import { useEffect, useRef, useState } from "react";

import {
  applyPrivateWriteEvidenceBundle,
  applyEvidenceSynthesisWriteAcceptance,
  applySynthesisKnowledgeAdmission,
  createEvidenceBundleSynthesisProposal,
  executeEvidenceBundleSynthesis,
  listPrivateWriteDocuments,
  listInvestigations,
  listSynthesisKnowledgeCandidates,
  previewPrivateWriteEvidenceBundle,
  previewEvidenceSynthesisWriteAcceptance,
  previewSynthesisKnowledgeAdmission,
  projectEvidenceBundleSynthesis,
  reconcileEvidenceBundleSynthesis,
  type EvidenceBundleSynthesisExecutionShape,
  type EvidenceBundleSynthesisProposalShape,
  type EvidenceBundleSynthesisProjectionShape,
  type EvidenceSynthesisWritePreviewShape,
  type EvidenceSynthesisWriteAcceptanceShape,
  type EvidenceRelationship,
  type PrivateWriteDocumentSummaryShape,
  type WriteCitationEvidenceShape,
  type WriteEvidenceBundleItemShape,
  type WriteEvidenceBundlePreviewShape,
  type SynthesisKnowledgeCandidateInputShape,
  type SynthesisKnowledgePreviewShape,
  type SynthesisKnowledgeSourceUnitShape,
  type InvestigationSummary,
} from "../../lib/api";
import { fetchRegisteredModels, type RegisteredModelRow } from "../../api/settings";
import { useAuth } from "../../lib/auth";
import { useWorkspace } from "../../workspace/WorkspaceStore";

const HEX64 = /^[0-9a-f]{64}$/;
const newKey = () => globalThis.crypto?.randomUUID?.() ??
  `evidence-bundle-${Date.now()}-${Math.random().toString(16).slice(2)}`;
const relationships: EvidenceRelationship[] = ["supports", "contradicts", "context", "unresolved"];

export function EvidenceBundleWriteAction({ evidence }: { evidence: WriteCitationEvidenceShape[] }) {
  const { sessionGeneration } = useAuth();
  const openPanel = useWorkspace((state) => state.open);
  const [open, setOpen] = useState(false);
  const [documents, setDocuments] = useState<PrivateWriteDocumentSummaryShape[]>([]);
  const [selected, setSelected] = useState("");
  const [items, setItems] = useState<WriteEvidenceBundleItemShape[]>([]);
  const [preview, setPreview] = useState<WriteEvidenceBundlePreviewShape | null>(null);
  const [busy, setBusy] = useState<"idle" | "loading" | "preview" | "apply">("idle");
  const [error, setError] = useState("");
  const [applied, setApplied] = useState<{ bundleId: string; target: PrivateWriteDocumentSummaryShape } | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const generationRef = useRef(sessionGeneration);
  const keyRef = useRef("");
  const invokerRef = useRef<HTMLButtonElement | null>(null);
  const dialogRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (generationRef.current !== sessionGeneration) {
      generationRef.current = sessionGeneration; abortRef.current?.abort(); setOpen(false);
      setDocuments([]); setItems([]); setPreview(null); setApplied(null); setError(""); setBusy("idle");
    }
    return () => abortRef.current?.abort();
  }, [sessionGeneration]);
  useEffect(() => {
    if (!open) { invokerRef.current?.focus(); return; }
    dialogRef.current?.querySelector<HTMLElement>("select,button")?.focus();
    const keydown = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape" && busy === "idle") { event.preventDefault(); setOpen(false); return; }
      if (event.key !== "Tab") return;
      const controls = dialogRef.current?.querySelectorAll<HTMLElement>("select,input,button:not([disabled])");
      if (!controls?.length) return;
      const first = controls[0]; const last = controls[controls.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    };
    const dialog = dialogRef.current; dialog?.addEventListener("keydown", keydown);
    return () => dialog?.removeEventListener("keydown", keydown);
  }, [open, busy]);

  const begin = async () => {
    const unique = evidence.filter((item, index) =>
      evidence.findIndex((candidate) => candidate.receipt_sha256 === item.receipt_sha256) === index,
    ).slice(0, 32);
    if (unique.length < 2) return;
    setOpen(true); setBusy("loading"); setError(""); setPreview(null); setApplied(null); keyRef.current = newKey();
    setItems(unique.map((citation_evidence) => ({ citation_evidence, relationship: "unresolved", operator_label: null })));
    const generation = sessionGeneration; const abort = new AbortController(); abortRef.current = abort;
    try {
      const found: PrivateWriteDocumentSummaryShape[] = []; let cursor = "";
      for (let pageIndex = 0; pageIndex < 100; pageIndex += 1) {
        const page = await listPrivateWriteDocuments(abort.signal, cursor, 100);
        found.push(...page.documents.filter((item) => item.origin_kind === "owner_native"));
        if (page.next_after_document_id === null) break;
        if (!page.documents.length || page.next_after_document_id <= cursor) throw new Error("Manuscript list did not advance");
        cursor = page.next_after_document_id;
      }
      if (abort.signal.aborted || generationRef.current !== generation) return;
      setDocuments(found); setSelected(found[0]?.write_document_id ?? ""); setBusy("idle");
    } catch (cause: unknown) {
      if ((cause as { name?: string }).name !== "AbortError") setError(cause instanceof Error ? cause.message : "Manuscripts unavailable");
      setBusy("idle");
    }
  };
  const target = documents.find((item) => item.write_document_id === selected);
  const invalidate = (next: WriteEvidenceBundleItemShape[]) => { setItems(next); setPreview(null); };
  const move = (index: number, delta: number) => {
    const next = [...items]; const other = index + delta;
    if (other < 0 || other >= next.length) return;
    [next[index], next[other]] = [next[other], next[index]]; invalidate(next);
  };
  const baseRequest = target ? { base_revision: target.revision,
    base_html_sha256: target.html_sha256, items } : null;

  const requestPreview = async () => {
    if (!target || !baseRequest || busy !== "idle") return;
    setBusy("preview"); setError(""); const generation = sessionGeneration;
    const abort = new AbortController(); abortRef.current = abort;
    try {
      const value = await previewPrivateWriteEvidenceBundle(
        target.project_id, target.write_document_id, baseRequest, abort.signal,
      );
      if (abort.signal.aborted || generationRef.current !== generation) return;
      if (value.operation !== "evidence_bundle" || value.origin_kind !== "owner_native" ||
          value.write_document_id !== target.write_document_id || value.project_id !== target.project_id ||
          value.base_revision !== target.revision || value.base_html_sha256 !== target.html_sha256 ||
          !HEX64.test(value.preview_sha256) || !HEX64.test(value.manifest_sha256) ||
          !HEX64.test(value.proposed_html_sha256) || value.items.length !== items.length) {
        throw new Error("Evidence bundle preview receipt is inconsistent");
      }
      setPreview(value);
    } catch (cause: unknown) {
      if ((cause as { name?: string }).name !== "AbortError") setError(cause instanceof Error ? cause.message : "Bundle preview failed");
    } finally { if (!abort.signal.aborted) setBusy("idle"); }
  };
  const apply = async () => {
    if (!target || !baseRequest || !preview || busy !== "idle") return;
    setBusy("apply"); setError(""); const generation = sessionGeneration;
    const abort = new AbortController(); abortRef.current = abort;
    try {
      const result = await applyPrivateWriteEvidenceBundle(
        target.project_id, target.write_document_id,
        { ...baseRequest, preview_sha256: preview.preview_sha256,
          manifest_sha256: preview.manifest_sha256,
          proposed_html_sha256: preview.proposed_html_sha256 }, keyRef.current, abort.signal,
      );
      if (abort.signal.aborted || generationRef.current !== generation) return;
      if (result.operation !== "evidence_bundle" || result.write_document_id !== target.write_document_id ||
          result.project_id !== target.project_id || result.prior_revision !== target.revision ||
          result.revision !== target.revision + 1 || !HEX64.test(result.html_sha256) ||
          typeof result.bundle_id !== "string" || !result.bundle_id) {
        throw new Error("Evidence bundle receipt is inconsistent");
      }
      openPanel("PrivateWrite", { projectId: target.project_id, writeDocumentId: target.write_document_id }, {
        mode: "floating", title: target.title,
        id: `PrivateWrite:${target.project_id}:${target.write_document_id}`,
      }); setApplied({ bundleId: result.bundle_id, target: {
        ...target, revision: result.revision, html_sha256: result.html_sha256,
      } });
    } catch (cause: unknown) {
      if ((cause as { name?: string }).name !== "AbortError") setError(cause instanceof Error ? cause.message : "Bundle merge failed");
    } finally { if (!abort.signal.aborted) setBusy("idle"); }
  };

  return <>
    <button ref={invokerRef} type="button" onClick={() => void begin()}>Draft citations into manuscript</button>
    {open ? <div className="fixed inset-0 z-[120] grid place-items-center bg-charcoal-2/60 p-4"><div ref={dialogRef} role="dialog" aria-modal="true" aria-labelledby="bundle-write-title" className="max-h-[90vh] w-full max-w-3xl overflow-auto border border-rule bg-ice-0 p-5 text-ink shadow-xl dark:bg-charcoal-2 dark:text-bright">
      <h2 id="bundle-write-title" className="font-serif text-xl">{applied ? "Synthesize evidence bundle" : "Draft cited research bundle"}</h2>
      {applied ? <EvidenceBundleSynthesisStep bundleId={applied.bundleId} target={applied.target} onClose={() => setOpen(false)} /> : <>
      <label htmlFor="bundle-target" className="mt-3 block text-xs">Owner-native manuscript</label>
      <select id="bundle-target" value={selected} disabled={busy !== "idle"} onChange={(event) => { setSelected(event.target.value); setPreview(null); }} className="w-full border border-rule bg-transparent p-2">{documents.map((item) => <option key={item.write_document_id} value={item.write_document_id}>{item.title} · r{item.revision}</option>)}</select>
      <ol className="mt-4 space-y-3">{items.map((item, index) => <li key={item.citation_evidence.receipt_sha256} className="border border-rule p-3">
        <p className="font-mono text-xs">Evidence {index + 1} · {item.citation_evidence.document_id}</p>
        <label className="text-xs">Relationship <select aria-label={`Evidence ${index + 1} relationship`} value={item.relationship} disabled={busy !== "idle"} onChange={(event) => { const next = [...items]; next[index] = { ...item, relationship: event.target.value as EvidenceRelationship }; invalidate(next); }}>{relationships.map((value) => <option key={value}>{value}</option>)}</select></label>
        <label className="ml-3 text-xs">Operator framing <input aria-label={`Evidence ${index + 1} operator framing`} maxLength={200} value={item.operator_label ?? ""} disabled={busy !== "idle"} onChange={(event) => { const next = [...items]; next[index] = { ...item, operator_label: event.target.value || null }; invalidate(next); }} /></label>
        <button type="button" disabled={index === 0 || busy !== "idle"} onClick={() => move(index, -1)}>Move up</button><button type="button" disabled={index === items.length - 1 || busy !== "idle"} onClick={() => move(index, 1)}>Move down</button>
      </li>)}</ol>
      {preview ? <iframe title="Evidence bundle manuscript preview" sandbox="" srcDoc={preview.proposed_html} className="mt-4 h-72 w-full border border-rule" /> : null}
      {error ? <p role="alert" className="mt-3 text-xs text-danger">{error}</p> : null}
      <div className="mt-5 flex justify-end gap-2"><button type="button" disabled={busy !== "idle"} onClick={() => setOpen(false)}>Cancel</button>{!preview ? <button type="button" disabled={!target || busy !== "idle"} onClick={() => void requestPreview()}>{busy === "preview" ? "Previewing…" : "Preview bundle"}</button> : <button type="button" disabled={busy !== "idle"} onClick={() => void apply()}>{busy === "apply" ? "Merging…" : "Merge bundle as one revision"}</button>}</div></>}
    </div></div> : null}
  </>;
}

function EvidenceBundleSynthesisStep({ bundleId, target, onClose }: {
  bundleId: string; target: PrivateWriteDocumentSummaryShape; onClose: () => void;
}) {
  const { sessionGeneration } = useAuth();
  const openPanel = useWorkspace((state) => state.open);
  const [models, setModels] = useState<RegisteredModelRow[]>([]);
  const [pair, setPair] = useState("");
  const [instruction, setInstruction] = useState("");
  const [projection, setProjection] = useState<EvidenceBundleSynthesisProjectionShape | null>(null);
  const [ceiling, setCeiling] = useState("");
  const [proposal, setProposal] = useState<EvidenceBundleSynthesisProposalShape | null>(null);
  const [execution, setExecution] = useState<EvidenceBundleSynthesisExecutionShape | null>(null);
  const [writePreview, setWritePreview] = useState<EvidenceSynthesisWritePreviewShape | null>(null);
  const [acceptedWrite, setAcceptedWrite] = useState<EvidenceSynthesisWriteAcceptanceShape | null>(null);
  const [busy, setBusy] = useState(false); const [error, setError] = useState("");
  const proposalKey = useRef(newKey()); const executionKey = useRef(newKey());
  const acceptanceKey = useRef(newKey());
  const generationRef = useRef(sessionGeneration);
  const abortRef = useRef<AbortController | null>(null);
  const inFlightRef = useRef(false);
  useEffect(() => {
    generationRef.current = sessionGeneration;
    abortRef.current?.abort();
    setProposal(null); setExecution(null); setProjection(null); setWritePreview(null); setAcceptedWrite(null); setError(""); setBusy(false);
  }, [sessionGeneration]);
  useEffect(() => {
    const generation = generationRef.current;
    void fetchRegisteredModels().then((value) => {
    if (generationRef.current !== generation) return;
    const enabled = value.models.filter((item) => item.enabled !== false && item.provider_id && item.model_id);
    setModels(enabled); if (enabled[0]) setPair(`${enabled[0].provider_id}\0${enabled[0].model_id}`);
  }).catch((cause: unknown) => {
    if (generationRef.current === generation) setError(cause instanceof Error ? cause.message : "Models unavailable");
  });
    return () => abortRef.current?.abort();
  }, []);
  const [providerId = "", modelId = ""] = pair.split("\0");
  const start = () => {
    if (inFlightRef.current) return null;
    inFlightRef.current = true; setBusy(true); setError("");
    const abort = new AbortController(); abortRef.current = abort;
    return { abort, generation: generationRef.current };
  };
  const finish = (abort: AbortController) => {
    inFlightRef.current = false;
    if (!abort.signal.aborted) setBusy(false);
  };
  const current = (abort: AbortController, generation: number) =>
    !abort.signal.aborted && generationRef.current === generation;
  const project = async () => { const request = start(); if (!request) return;
    setExecution(null); setProposal(null);
    try { const value = await projectEvidenceBundleSynthesis(target.project_id, target.write_document_id, bundleId,
      { instruction, provider_id: providerId, model_id: modelId, expected_output_tokens: 4000 }, request.abort.signal);
      if (!current(request.abort, request.generation)) return;
      if (value.source_kind !== "evidence_bundle" || value.project_id !== target.project_id ||
          value.write_document_id !== target.write_document_id || value.bundle_id !== bundleId ||
          value.provider_id !== providerId || value.model_id !== modelId ||
          !Number.isInteger(value.projected_max_cents) || value.projected_max_cents < 1 || value.item_count < 2) {
        throw new Error("Evidence synthesis projection receipt is inconsistent");
      }
      setProjection(value); setCeiling(String(value.projected_max_cents));
    } catch (cause: unknown) { if (current(request.abort, request.generation)) setError(cause instanceof Error ? cause.message : "Projection unavailable"); }
    finally { finish(request.abort); } };
  const stage = async () => { if (!projection) return; const request = start(); if (!request) return;
    try { const approved = Number(ceiling); if (!Number.isInteger(approved) || approved < projection.projected_max_cents) throw new Error("Approved ceiling must cover the server projection");
      const value = await createEvidenceBundleSynthesisProposal(target.project_id, target.write_document_id, bundleId,
        { base_revision: 0, instruction, provider_id: providerId, model_id: modelId,
          approved_ceiling_cents: approved, expected_output_tokens: 4000 }, proposalKey.current, request.abort.signal);
      if (!current(request.abort, request.generation)) return;
      if (value.source_kind !== "evidence_bundle" || value.project_id !== target.project_id ||
          value.write_document_id !== target.write_document_id || value.bundle_id !== bundleId ||
          value.provider_id !== providerId || value.model_id !== modelId ||
          value.projected_max_cents !== projection.projected_max_cents ||
          value.approved_ceiling_cents !== approved || value.state !== "staged" || !value.proposal_id) {
        throw new Error("Evidence synthesis proposal receipt is inconsistent");
      }
      setProposal(value);
    } catch (cause: unknown) { if (current(request.abort, request.generation)) setError(cause instanceof Error ? cause.message : "Proposal staging failed"); }
    finally { finish(request.abort); } };
  const acceptExecution = (value: EvidenceBundleSynthesisExecutionShape, proposalId: string) => {
    if (value.proposal_id !== proposalId || value.visibility !== "private" || !value.attempt_id || !value.run_id ||
        (value.html !== null && (!value.html_sha256 || !HEX64.test(value.html_sha256)))) {
      throw new Error("Evidence synthesis execution receipt is inconsistent");
    }
    setExecution(value);
  };
  const execute = async () => { if (!proposal) return; const request = start(); if (!request) return;
    try { const value = await executeEvidenceBundleSynthesis(target.project_id, target.write_document_id, bundleId,
      proposal.proposal_id, executionKey.current, request.abort.signal);
      if (!current(request.abort, request.generation)) return; acceptExecution(value, proposal.proposal_id);
    } catch (cause: unknown) { if (current(request.abort, request.generation)) setError(cause instanceof Error ? cause.message : "Synthesis failed"); }
    finally { finish(request.abort); } };
  const reconcile = async () => { if (!proposal) return; const request = start(); if (!request) return;
    try { const value = await reconcileEvidenceBundleSynthesis(target.project_id, target.write_document_id, bundleId,
      proposal.proposal_id, request.abort.signal);
      if (!current(request.abort, request.generation)) return; acceptExecution(value, proposal.proposal_id);
    } catch (cause: unknown) { if (current(request.abort, request.generation)) setError(cause instanceof Error ? cause.message : "Reconciliation failed"); }
    finally { finish(request.abort); } };
  const previewWrite = async () => { if (!proposal || execution?.state !== "ready_for_review") return;
    const request = start(); if (!request) return;
    try { const value = await previewEvidenceSynthesisWriteAcceptance(
      target.project_id, target.write_document_id, bundleId, proposal.proposal_id,
      { base_revision: target.revision, base_html_sha256: target.html_sha256 }, request.abort.signal);
      if (!current(request.abort, request.generation)) return;
      if (value.operation !== "synthesis_accept" || value.project_id !== target.project_id ||
          value.write_document_id !== target.write_document_id || value.bundle_id !== bundleId ||
          value.proposal_id !== proposal.proposal_id || value.execution_run_id !== execution.run_id ||
          value.base_revision !== target.revision || value.base_html_sha256 !== target.html_sha256 ||
          value.result_html_sha256 !== execution.html_sha256 || !HEX64.test(value.preview_sha256) ||
          !HEX64.test(value.proposed_html_sha256)) throw new Error("Synthesis Write preview receipt is inconsistent");
      setWritePreview(value);
    } catch (cause: unknown) { if (current(request.abort, request.generation)) setError(cause instanceof Error ? cause.message : "Write preview failed"); }
    finally { finish(request.abort); } };
  const acceptWrite = async () => { if (!proposal || !writePreview || execution?.state !== "ready_for_review") return;
    const request = start(); if (!request) return;
    try { const value = await applyEvidenceSynthesisWriteAcceptance(
      target.project_id, target.write_document_id, bundleId, proposal.proposal_id,
      { base_revision: writePreview.base_revision, base_html_sha256: writePreview.base_html_sha256,
        preview_sha256: writePreview.preview_sha256,
        proposed_html_sha256: writePreview.proposed_html_sha256 }, acceptanceKey.current, request.abort.signal);
      if (!current(request.abort, request.generation)) return;
      if (value.operation !== "synthesis_accept" || value.project_id !== target.project_id ||
          value.write_document_id !== target.write_document_id || value.bundle_id !== bundleId ||
          value.proposal_id !== proposal.proposal_id || value.execution_run_id !== execution.run_id ||
          value.prior_revision !== writePreview.base_revision || value.revision !== value.prior_revision + 1 ||
          !HEX64.test(value.html_sha256) || !HEX64.test(value.receipt_sha256)) {
        throw new Error("Synthesis Write acceptance receipt is inconsistent");
      }
      openPanel("PrivateWrite", { projectId: target.project_id, writeDocumentId: target.write_document_id }, {
        mode: "floating", title: target.title,
        id: `PrivateWrite:${target.project_id}:${target.write_document_id}`,
      }); setAcceptedWrite(value);
    } catch (cause: unknown) { if (current(request.abort, request.generation)) setError(cause instanceof Error ? cause.message : "Write acceptance failed"); }
    finally { finish(request.abort); } };
  if (acceptedWrite && proposal) return <SynthesisKnowledgeAdmissionStep
    target={target} bundleId={bundleId} proposalId={proposal.proposal_id}
    acceptance={acceptedWrite} onClose={onClose}
  />;
  return <div className="mt-4 space-y-3">
    <p className="text-sm">The manuscript revision is saved. Model synthesis remains a separate private review artifact.</p>
    <label className="block text-xs">Decision-tree model<select aria-label="Synthesis model" value={pair} disabled={busy || proposal !== null} onChange={(event) => { setPair(event.target.value); setProjection(null); setProposal(null); }} className="w-full border border-rule bg-transparent p-2">{models.map((item) => <option key={`${item.provider_id}/${item.model_id}`} value={`${item.provider_id}\0${item.model_id}`}>{item.display_name || item.model_id} · {item.provider_id}</option>)}</select></label>
    <label className="block text-xs">Instruction<textarea aria-label="Synthesis instruction" value={instruction} disabled={busy || proposal !== null} maxLength={20000} onChange={(event) => { setInstruction(event.target.value); setProjection(null); setProposal(null); }} className="h-24 w-full border border-rule bg-transparent p-2" /></label>
    {projection ? <div data-testid="evidence-synthesis-budget" className="border border-rule p-3 text-xs"><p>Server projected maximum: {projection.projected_max_cents}¢</p><p>API-key budget: spent {projection.budget.spent_usd == null ? "unknown" : `$${projection.budget.spent_usd.toFixed(4)}`} · remaining {projection.budget.remaining_usd == null ? "unknown" : `$${projection.budget.remaining_usd.toFixed(4)}`}</p><label>Approved ceiling (¢)<input aria-label="Approved ceiling cents" type="number" min={projection.projected_max_cents} value={ceiling} onChange={(event) => setCeiling(event.target.value)} /></label></div> : null}
    {execution?.html ? <iframe title="Private evidence synthesis review" sandbox="" srcDoc={execution.html} className="h-72 w-full border border-rule" /> : null}
    {writePreview ? <iframe title="Evidence synthesis manuscript preview" sandbox="" srcDoc={writePreview.proposed_html} className="h-72 w-full border border-rule" /> : null}
    {execution?.state === "rejected" ? <p role="alert">Rejected: {execution.rejection_reason}</p> : null}
    {proposal && !execution ? <p className="text-xs">Proposal staged: {proposal.proposal_id}. Execution still requires explicit authorization.</p> : null}
    {error ? <p role="alert" className="text-danger">{error}</p> : null}
    <div className="flex justify-end gap-2"><button type="button" disabled={busy} onClick={onClose}>Close</button>{!projection ? <button type="button" disabled={busy || !pair || !instruction.trim()} onClick={() => void project()}>Project cost</button> : !proposal ? <button type="button" disabled={busy} onClick={() => void stage()}>{busy ? "Staging…" : "Approve ceiling and stage proposal"}</button> : execution?.state === "ready_for_review" ? !writePreview ? <button type="button" disabled={busy} onClick={() => void previewWrite()}>Preview in manuscript</button> : <button type="button" disabled={busy} onClick={() => void acceptWrite()}>Accept into revision {writePreview.base_revision + 1}</button> : <><button type="button" disabled={busy} onClick={() => void execute()}>{busy ? "Working…" : "Execute staged proposal"}</button>{error && error.toLowerCase().includes("reconcil") ? <button type="button" disabled={busy} onClick={() => void reconcile()}>Reconcile checkpoint</button> : null}</>}</div>
  </div>;
}

function SynthesisKnowledgeAdmissionStep({ target, bundleId, proposalId, acceptance, onClose }: {
  target: PrivateWriteDocumentSummaryShape; bundleId: string; proposalId: string;
  acceptance: EvidenceSynthesisWriteAcceptanceShape; onClose: () => void;
}) {
  const { sessionGeneration } = useAuth();
  const [sourceUnits, setSourceUnits] = useState<SynthesisKnowledgeSourceUnitShape[]>([]);
  const [investigations, setInvestigations] = useState<InvestigationSummary[]>([]);
  const [targetInvestigation, setTargetInvestigation] = useState("");
  const [items, setItems] = useState<(SynthesisKnowledgeCandidateInputShape & { selected: boolean })[]>([]);
  const [preview, setPreview] = useState<SynthesisKnowledgePreviewShape | null>(null);
  const [admitted, setAdmitted] = useState(false);
  const [busy, setBusy] = useState(true); const [error, setError] = useState("");
  const generationRef = useRef(sessionGeneration); const abortRef = useRef<AbortController | null>(null);
  const inFlightRef = useRef(false); const keyRef = useRef(newKey());
  useEffect(() => {
    generationRef.current = sessionGeneration; abortRef.current?.abort(); setPreview(null);
    setAdmitted(false); setError(""); setBusy(true); inFlightRef.current = false;
    const generation = sessionGeneration; const abort = new AbortController(); abortRef.current = abort;
    void Promise.all([
      listSynthesisKnowledgeCandidates(
        target.project_id, target.write_document_id, bundleId, proposalId,
        acceptance.acceptance_id, abort.signal,
      ),
      listInvestigations({ limit: 200 }),
    ]).then(([candidates, investigationPage]) => {
      if (abort.signal.aborted || generationRef.current !== generation) return;
      if (candidates.acceptance_id !== acceptance.acceptance_id ||
          candidates.proposal_id !== proposalId || candidates.verification !== "unverified" ||
          candidates.epistemic_status !== "model_proposed" || candidates.visibility !== "private" ||
          candidates.units.some((unit, index) => unit.unit_index !== index ||
            !HEX64.test(unit.original_text_sha256) || !unit.text.trim())) {
        throw new Error("Synthesis knowledge candidates are inconsistent");
      }
      setSourceUnits(candidates.units);
      setItems(candidates.units.map((unit) => ({
        unit_index: unit.unit_index, kind: "insight", text: unit.text, selected: false,
      })));
      setInvestigations(investigationPage.investigations);
      setTargetInvestigation(investigationPage.investigations[0]?.investigation_id ?? "");
      setBusy(false);
    }).catch((cause: unknown) => {
      if (!abort.signal.aborted && generationRef.current === generation) {
        setError(cause instanceof Error ? cause.message : "Knowledge candidates unavailable");
        setBusy(false);
      }
    });
    return () => abort.abort();
  }, [acceptance.acceptance_id, bundleId, proposalId, sessionGeneration,
    target.project_id, target.write_document_id]);
  const selectedItems = items.filter((item) => item.selected).map(({ selected: _, ...item }) => item);
  const invalidate = (next: typeof items) => { setItems(next); setPreview(null); setAdmitted(false); };
  const start = () => {
    if (inFlightRef.current) return null;
    inFlightRef.current = true; setBusy(true); setError("");
    const abort = new AbortController(); abortRef.current = abort;
    return { abort, generation: generationRef.current };
  };
  const finish = (abort: AbortController) => {
    inFlightRef.current = false; if (!abort.signal.aborted) setBusy(false);
  };
  const current = (abort: AbortController, generation: number) =>
    !abort.signal.aborted && generationRef.current === generation;
  const requestPreview = async () => {
    if (!targetInvestigation || selectedItems.length < 1 || selectedItems.length > 32) return;
    const request = start(); if (!request) return;
    try {
      const value = await previewSynthesisKnowledgeAdmission(
        target.project_id, target.write_document_id, bundleId, proposalId,
        acceptance.acceptance_id,
        { target_investigation_id: targetInvestigation, items: selectedItems }, request.abort.signal,
      );
      if (!current(request.abort, request.generation)) return;
      if (value.acceptance_id !== acceptance.acceptance_id || value.proposal_id !== proposalId ||
          value.target_investigation_id !== targetInvestigation || value.verification !== "unverified" ||
          value.epistemic_status !== "model_proposed_operator_admitted" ||
          !HEX64.test(value.preview_sha256) || !HEX64.test(value.item_manifest_sha256) ||
          value.items.length !== selectedItems.length || value.items.some((item, index) =>
            item.unit_index !== selectedItems[index].unit_index || item.kind !== selectedItems[index].kind ||
            item.admitted_text !== selectedItems[index].text || !HEX64.test(item.item_receipt_sha256))) {
        throw new Error("Synthesis knowledge preview receipt is inconsistent");
      }
      setPreview(value);
    } catch (cause: unknown) {
      if (current(request.abort, request.generation)) setError(cause instanceof Error ? cause.message : "Knowledge preview failed");
    } finally { finish(request.abort); }
  };
  const apply = async () => {
    if (!preview || !targetInvestigation || selectedItems.length < 1) return;
    const request = start(); if (!request) return;
    try {
      const value = await applySynthesisKnowledgeAdmission(
        target.project_id, target.write_document_id, bundleId, proposalId,
        acceptance.acceptance_id,
        { target_investigation_id: targetInvestigation, items: selectedItems,
          preview_sha256: preview.preview_sha256 }, keyRef.current, request.abort.signal,
      );
      if (!current(request.abort, request.generation)) return;
      if (value.acceptance_id !== acceptance.acceptance_id || value.proposal_id !== proposalId ||
          value.bundle_id !== bundleId || value.project_id !== target.project_id ||
          value.write_document_id !== target.write_document_id ||
          value.target_investigation_id !== targetInvestigation ||
          value.verification !== "unverified" || !HEX64.test(value.receipt_sha256) ||
          value.items.length !== selectedItems.length) {
        throw new Error("Synthesis knowledge admission receipt is inconsistent");
      }
      setAdmitted(true);
    } catch (cause: unknown) {
      if (current(request.abort, request.generation)) setError(cause instanceof Error ? cause.message : "Knowledge admission failed");
    } finally { finish(request.abort); }
  };
  return <div className="mt-4 space-y-3" data-testid="synthesis-knowledge-admission">
    <h3 className="font-serif text-lg">Retain synthesis in the knowledge graph</h3>
    <p className="border border-rule p-3 text-xs"><strong>Epistemic status:</strong> model-proposed, operator-admitted, unverified. Admission saves a knowledge unit; it does not verify the claim.</p>
    <label className="block text-xs">Target research investigation<select aria-label="Knowledge target investigation" value={targetInvestigation} disabled={busy || admitted} onChange={(event) => { setTargetInvestigation(event.target.value); setPreview(null); }} className="w-full border border-rule bg-transparent p-2"><option value="">Select an investigation</option>{investigations.map((investigation) => <option key={investigation.investigation_id} value={investigation.investigation_id}>{investigation.question || investigation.investigation_id} · {investigation.status}</option>)}</select></label>
    <ol className="space-y-3">{sourceUnits.map((unit, index) => {
      const item = items[index]; if (!item) return null;
      return <li key={unit.unit_index} className="border border-rule p-3">
        <label className="text-xs"><input type="checkbox" aria-label={`Select synthesis unit ${index + 1}`} checked={item.selected} disabled={busy || admitted} onChange={(event) => { const next = [...items]; next[index] = { ...item, selected: event.target.checked }; invalidate(next); }} /> Retain unit {index + 1}</label>
        <label className="ml-3 text-xs">Kind <select aria-label={`Synthesis unit ${index + 1} kind`} value={item.kind} disabled={busy || admitted || !item.selected} onChange={(event) => { const next = [...items]; next[index] = { ...item, kind: event.target.value as "insight" | "question" }; invalidate(next); }}><option value="insight">Insight</option><option value="question">Open question</option></select></label>
        <textarea aria-label={`Synthesis unit ${index + 1} text`} value={item.text} maxLength={20000} disabled={busy || admitted || !item.selected} onChange={(event) => { const next = [...items]; next[index] = { ...item, text: event.target.value }; invalidate(next); }} className="mt-2 h-24 w-full border border-rule bg-transparent p-2" />
        <p className="font-mono text-[10px]">Evidence receipts: {unit.evidence.map((evidence) => evidence.citation_receipt_sha256.slice(0, 12)).join(", ")}</p>
      </li>;
    })}</ol>
    {preview ? <div data-testid="synthesis-knowledge-preview" className="border border-rule p-3 text-xs"><p>Preview: {preview.items.length} private knowledge unit(s).</p><ul>{preview.items.map((item) => <li key={item.item_receipt_sha256}>{item.kind} · {item.disposition === "created" ? "new to this investigation" : "already in this investigation"} · {item.canonical_text}</li>)}</ul></div> : null}
    {admitted ? <p role="status">Knowledge admission recorded. Units remain explicitly unverified.</p> : null}
    {error ? <p role="alert" className="text-danger">{error}</p> : null}
    <div className="flex justify-end gap-2"><button type="button" disabled={busy} onClick={onClose}>Close</button>{!admitted && (!preview ? <button type="button" disabled={busy || !targetInvestigation || selectedItems.length < 1 || selectedItems.length > 32 || selectedItems.some((item) => !item.text.trim())} onClick={() => void requestPreview()}>Preview knowledge admission</button> : <button type="button" disabled={busy} onClick={() => void apply()}>Admit {preview.items.length} unverified unit(s)</button>)}</div>
  </div>;
}
