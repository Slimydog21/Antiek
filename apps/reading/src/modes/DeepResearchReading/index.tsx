/**
 * DRW SPR-10 — the reading surface: the system takes notes for you.
 *
 * Open a document and it is already annotated with the insights + open
 * questions SPR-03 distilled — inline highlights, anchored by content so they
 * survive edits. Challenge a note and it changes (or escalates to a research).
 * Structural gaps for the document sit alongside. Spin a research from a gap
 * or a note in the moment — it seeds the cascade planner and hands off to the
 * SPR-09 monitor (`/deep-research?plan=…`) — then return to reading.
 *
 * Rabbit-hole scope (honest, rigor #2): selecting a highlight focuses its note
 * card (challenge / spin). A full conversational span-chat reuses the existing
 * chat infrastructure and is deliberately NOT rebuilt here — the spin-research
 * is the "go deeper" action, scoped to the minimum that engages the material.
 */

import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { PanelHost } from "../../workspace/PanelHost";
import type { StarterPanel } from "../../workspace/PanelHost";
import { createPlan } from "../../api/research";
import { getDocument, createDocumentVersion, type ReadingDocument } from "../../api/reading";
import DocumentView from "./DocumentView";
import GapSidebar from "./GapSidebar";
import NoteCard from "./NoteCard";
import { computeHighlights } from "./anchor";
import { useLiveNotes } from "./useLiveNotes";

const NO_STARTERS: StarterPanel[] = [];

export default function DeepResearchReading() {
  return (
    <PanelHost starters={NO_STARTERS}>
      <Reading />
    </PanelHost>
  );
}

function Reading() {
  const { documentId = null } = useParams<{ documentId?: string }>();
  const navigate = useNavigate();
  const [doc, setDoc] = useState<ReadingDocument | null>(null);
  const [docError, setDocError] = useState<string | null>(null);
  const [selectedNoteId, setSelectedNoteId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const live = useLiveNotes(documentId);

  useEffect(() => {
    if (!documentId) return;
    let cancelled = false;
    void (async () => {
      try {
        const d = await getDocument(documentId);
        if (!cancelled) { setDoc(d); setDocError(null); }
      } catch (e) {
        if (!cancelled) setDocError(e instanceof Error ? e.message : String(e));
      }
    })();
    return () => { cancelled = true; };
  }, [documentId]);

  const spin = useCallback(async (seed: string) => {
    setBusy(true);
    try {
      const r = await createPlan({ problem: seed });
      navigate(`/deep-research?plan=${encodeURIComponent(r.root_node_id)}`);
    } finally {
      setBusy(false);
    }
  }, [navigate]);

  const saveEdit = useCallback(async (newText: string) => {
    if (!documentId) return;
    setBusy(true);
    try {
      const r = await createDocumentVersion(documentId, newText);
      if (!r.unchanged) navigate(`/deep-research/read/${encodeURIComponent(r.new_document_id)}`);
    } finally {
      setBusy(false);
    }
  }, [documentId, navigate]);

  if (!documentId) {
    return <Empty>Open a document to read it with its notes taken for you.</Empty>;
  }
  if (docError) {
    return <Empty>Could not load this document: {docError}</Empty>;
  }
  if (!doc) {
    return <Empty>Loading document…</Empty>;
  }

  const raw = doc.raw_text ?? "";
  const { staleNoteIds } = computeHighlights(raw, live.notes);
  const staleSet = new Set(staleNoteIds);

  return (
    <div className="grid h-full grid-cols-[1fr_360px] gap-4 overflow-hidden p-4">
      <div className="flex min-w-0 flex-col gap-2 overflow-hidden">
        <h1 className="truncate text-sm font-semibold text-ink dark:text-bright">{doc.title ?? doc.document_id}</h1>
        <div className="min-h-0 flex-1">
          <DocumentView
            rawText={raw}
            notes={live.notes}
            selectedNoteId={selectedNoteId}
            onSelectNote={setSelectedNoteId}
            onSaveEdit={saveEdit}
            busy={busy}
          />
        </div>
      </div>

      <aside className="flex min-h-0 flex-col gap-4 overflow-auto">
        <section className="flex flex-col gap-2">
          <h2 className="text-[11px] uppercase tracking-[0.14em] text-shadow-1 dark:text-moonlight">
            Notes {live.loading && <span className="text-aurora">· taking…</span>}
          </h2>
          {live.notes.map((n) => (
            <div key={n.node_id} className={n.node_id === selectedNoteId ? "ring-2 ring-sun rounded-md" : ""}>
              <NoteCard
                note={n}
                documentId={documentId}
                stale={staleSet.has(n.node_id)}
                onRefined={() => live.refetch()}
                onEscalated={(_child, questionId) => void spin(n.text || questionId)}
              />
            </div>
          ))}
          {!live.notes.length && !live.loading && (
            <p className="text-[11px] text-shadow-1 dark:text-moonlight">No notes yet — the pass runs as you read.</p>
          )}
        </section>

        <section className="flex flex-col gap-2">
          <h2 className="text-[11px] uppercase tracking-[0.14em] text-shadow-1 dark:text-moonlight">Structural gaps</h2>
          <GapSidebar gaps={live.gaps} onSpin={(g) => void spin(g.question)} />
        </section>
      </aside>
    </div>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex h-full items-center justify-center p-8 text-center text-sm text-shadow-1 dark:text-moonlight">
      <div className="max-w-md">{children}</div>
    </div>
  );
}
