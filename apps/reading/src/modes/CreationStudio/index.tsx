import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import {
  attachBlock,
  createDeliverable,
  createSection,
  getDeliverable,
  ingestVoiceNote,
  listDeliverables,
  type DeliverableDetailResponse,
  type DeliverableKind,
  type DeliverableSummary,
  type SectionResponse,
} from "../../lib/api";
import HeaderBar from "../shared/HeaderBar";

type RecordingState = "idle" | "recording" | "transcribing" | "ingested";

const DELIVERABLE_KIND_LABELS: Record<DeliverableKind, string> = {
  research_memo: "Research memo",
  book_chapter: "Book chapter",
  biography_section: "Biography section",
  investor_brief: "Investor brief",
  general_essay: "General essay",
};

/**
 * Mode C v0 — section-based creation surface.
 *
 * Sprint 13 ships the substrate-honest minimum: list deliverables,
 * create new ones, add sections, attach blocks by id. Sprint 14 will
 * layer drag-drop, the block palette, and inline prose generation.
 *
 * Also: voice note quick-capture (sidebar widget). Records audio in
 * the browser via MediaRecorder, posts the operator-provided
 * transcript to /voice-notes/ingest. The audio→whisper round trip
 * is a Sprint-13-end stretch (audio upload endpoint).
 */
export default function CreationStudio() {
  return (
    <div className="flex flex-col h-screen bg-stone-50">
      <HeaderBar />
      <main className="flex-1 overflow-hidden">
        <div className="h-full max-w-6xl mx-auto px-6 py-6 grid grid-cols-[280px_1fr] gap-6">
          <DeliverableSidebar />
          <DeliverableDetail />
        </div>
      </main>
    </div>
  );
}

function DeliverableSidebar() {
  const navigate = useNavigate();
  const [deliverables, setDeliverables] = useState<DeliverableSummary[]>([]);
  const [creating, setCreating] = useState(false);
  const [newTitle, setNewTitle] = useState("");
  const [newKind, setNewKind] = useState<DeliverableKind>("research_memo");

  async function refresh() {
    try {
      const { deliverables } = await listDeliverables();
      setDeliverables(deliverables);
    } catch {
      // ignore — show empty
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!newTitle.trim()) return;
    setCreating(true);
    try {
      const d = await createDeliverable({
        title: newTitle.trim(),
        deliverable_kind: newKind,
      });
      setNewTitle("");
      await refresh();
      navigate(`/create/${d.deliverable_id}`);
    } finally {
      setCreating(false);
    }
  }

  return (
    <aside className="flex flex-col gap-4 min-h-0">
      <h2 className="text-sm font-semibold text-stone-700">
        Deliverables
      </h2>
      <form
        onSubmit={handleCreate}
        className="bg-white border border-stone-200 rounded-md p-3 space-y-2"
      >
        <input
          value={newTitle}
          onChange={(e) => setNewTitle(e.target.value)}
          placeholder="New deliverable title…"
          className="w-full px-2 py-1.5 text-sm border border-stone-300 rounded focus:outline-none focus:ring-2 focus:ring-stone-400"
        />
        <select
          value={newKind}
          onChange={(e) => setNewKind(e.target.value as DeliverableKind)}
          className="w-full px-2 py-1.5 text-xs border border-stone-300 rounded focus:outline-none focus:ring-2 focus:ring-stone-400"
        >
          {(Object.keys(DELIVERABLE_KIND_LABELS) as DeliverableKind[]).map(
            (k) => (
              <option key={k} value={k}>
                {DELIVERABLE_KIND_LABELS[k]}
              </option>
            ),
          )}
        </select>
        <button
          type="submit"
          disabled={creating || !newTitle.trim()}
          className="w-full px-3 py-1.5 bg-stone-900 hover:bg-stone-800 disabled:bg-stone-300 text-white text-xs font-medium rounded transition-colors"
        >
          {creating ? "Creating…" : "New deliverable"}
        </button>
      </form>
      <ul className="flex-1 overflow-y-auto space-y-1 min-h-0">
        {deliverables.map((d) => (
          <li key={d.deliverable_id}>
            <button
              onClick={() => navigate(`/create/${d.deliverable_id}`)}
              className="w-full text-left px-3 py-2 bg-white hover:bg-stone-100 border border-stone-200 rounded text-sm"
            >
              <div className="font-medium truncate">{d.title}</div>
              <div className="text-xs text-stone-500 flex justify-between">
                <span>{DELIVERABLE_KIND_LABELS[d.deliverable_kind] ?? d.deliverable_kind}</span>
                <span>{d.section_count} §</span>
              </div>
            </button>
          </li>
        ))}
      </ul>
      <VoiceNoteCapture />
    </aside>
  );
}

function DeliverableDetail() {
  const { deliverableId } = useParams<{ deliverableId?: string }>();
  const [detail, setDetail] = useState<DeliverableDetailResponse | null>(null);
  const [loading, setLoading] = useState(false);

  async function refresh() {
    if (!deliverableId) {
      setDetail(null);
      return;
    }
    setLoading(true);
    try {
      const d = await getDeliverable(deliverableId);
      setDetail(d);
    } catch {
      setDetail(null);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void refresh();
  }, [deliverableId]);

  if (!deliverableId) {
    return (
      <section className="flex items-center justify-center h-full text-stone-500 text-sm">
        Select or create a deliverable to begin.
      </section>
    );
  }
  if (loading && !detail) {
    return (
      <section className="text-stone-500 text-sm">Loading deliverable…</section>
    );
  }
  if (!detail) {
    return (
      <section className="text-stone-500 text-sm">
        Deliverable not found.
      </section>
    );
  }

  return (
    <section className="overflow-y-auto pr-2">
      <header className="mb-6">
        <p className="text-xs uppercase tracking-wide text-stone-500">
          {DELIVERABLE_KIND_LABELS[detail.deliverable_kind] ?? detail.deliverable_kind}
        </p>
        <h1 className="text-2xl font-semibold tracking-tight text-stone-900">
          {detail.title}
        </h1>
      </header>

      <ul className="space-y-4">
        {detail.sections.map((s) => (
          <SectionCard key={s.section_id} section={s} onChanged={refresh} />
        ))}
      </ul>

      <NewSectionForm
        deliverableId={detail.deliverable_id}
        nextIndex={detail.sections.length}
        onCreated={refresh}
      />
    </section>
  );
}

function SectionCard({
  section,
  onChanged,
}: {
  section: SectionResponse;
  onChanged: () => Promise<void> | void;
}) {
  const [showAttach, setShowAttach] = useState(false);
  const [blockId, setBlockId] = useState("");
  const [blockKind, setBlockKind] =
    useState<"insight" | "open_question" | "operator_note" | "claim">("insight");
  const [busy, setBusy] = useState(false);

  async function handleAttach(e: React.FormEvent) {
    e.preventDefault();
    if (!blockId.trim()) return;
    setBusy(true);
    try {
      await attachBlock({
        section_id: section.section_id,
        block_kind: blockKind,
        block_id: blockId.trim(),
        block_index: section.block_count,
      });
      setBlockId("");
      setShowAttach(false);
      await onChanged();
    } finally {
      setBusy(false);
    }
  }

  return (
    <li className="bg-white border border-stone-200 rounded-md p-4">
      <div className="flex items-baseline justify-between gap-3">
        <div>
          <p className="text-xs text-stone-500">
            Section {section.section_index + 1}
          </p>
          <h2 className="text-base font-semibold text-stone-900">
            {section.title || "(untitled)"}
          </h2>
        </div>
        <span className="text-xs text-stone-500">
          {section.block_count} blocks
        </span>
      </div>

      {section.prose_text ? (
        <p className="mt-3 text-sm text-stone-700 whitespace-pre-line">
          {section.prose_text}
        </p>
      ) : (
        <p className="mt-3 text-xs text-stone-400 italic">
          No prose yet. Attach blocks and run the creative_writer role
          (Sprint 14 wires this from the UI; today you can dispatch via
          the orchestrator from a notebook).
        </p>
      )}

      <div className="mt-3 flex items-center gap-2">
        <button
          onClick={() => setShowAttach((v) => !v)}
          className="text-xs text-stone-600 hover:text-stone-900 underline"
        >
          {showAttach ? "Cancel" : "Attach block"}
        </button>
      </div>

      {showAttach && (
        <form
          onSubmit={handleAttach}
          className="mt-3 flex items-center gap-2"
        >
          <select
            value={blockKind}
            onChange={(e) =>
              setBlockKind(
                e.target.value as
                  | "insight"
                  | "open_question"
                  | "operator_note"
                  | "claim",
              )
            }
            className="px-2 py-1 text-xs border border-stone-300 rounded"
          >
            <option value="insight">insight</option>
            <option value="open_question">open_question</option>
            <option value="operator_note">operator_note</option>
            <option value="claim">claim</option>
          </select>
          <input
            value={blockId}
            onChange={(e) => setBlockId(e.target.value)}
            placeholder="block_id (e.g. node-…)"
            className="flex-1 px-2 py-1 text-xs font-mono border border-stone-300 rounded"
          />
          <button
            type="submit"
            disabled={busy || !blockId.trim()}
            className="px-3 py-1 bg-stone-900 hover:bg-stone-800 disabled:bg-stone-300 text-white text-xs rounded"
          >
            Attach
          </button>
        </form>
      )}
    </li>
  );
}

function NewSectionForm({
  deliverableId,
  nextIndex,
  onCreated,
}: {
  deliverableId: string;
  nextIndex: number;
  onCreated: () => Promise<void> | void;
}) {
  const [title, setTitle] = useState("");
  const [busy, setBusy] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!title.trim()) return;
    setBusy(true);
    try {
      await createSection({
        deliverable_id: deliverableId,
        section_index: nextIndex,
        title: title.trim(),
      });
      setTitle("");
      await onCreated();
    } finally {
      setBusy(false);
    }
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="mt-6 bg-white border border-dashed border-stone-300 rounded-md p-3 flex items-center gap-2"
    >
      <input
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        placeholder={`New section title (will be #${nextIndex + 1})…`}
        className="flex-1 px-2 py-1.5 text-sm border border-stone-300 rounded focus:outline-none focus:ring-2 focus:ring-stone-400"
      />
      <button
        type="submit"
        disabled={busy || !title.trim()}
        className="px-3 py-1.5 bg-stone-900 hover:bg-stone-800 disabled:bg-stone-300 text-white text-sm rounded"
      >
        Add section
      </button>
    </form>
  );
}

function VoiceNoteCapture() {
  const [state, setState] = useState<RecordingState>("idle");
  const [transcript, setTranscript] = useState("");
  const [lastDocId, setLastDocId] = useState<string | null>(null);

  async function handleIngest() {
    if (!transcript.trim()) return;
    setState("transcribing");
    try {
      const r = await ingestVoiceNote({ transcript: transcript.trim() });
      setLastDocId(r.document_id);
      setState("ingested");
      setTranscript("");
    } catch {
      setState("idle");
    }
  }

  return (
    <div className="bg-white border border-stone-200 rounded-md p-3">
      <p className="text-xs font-semibold text-stone-700 uppercase tracking-wide">
        Quick voice note
      </p>
      <p className="mt-1 text-xs text-stone-500">
        Paste a transcript (or use the browser dictation button on iOS /
        macOS) to add a voice note straight into the graph.
      </p>
      <textarea
        value={transcript}
        onChange={(e) => setTranscript(e.target.value)}
        rows={3}
        placeholder="Transcript…"
        className="mt-2 w-full px-2 py-1.5 text-sm border border-stone-300 rounded focus:outline-none focus:ring-2 focus:ring-stone-400"
      />
      <div className="mt-2 flex items-center justify-between gap-2">
        <button
          onClick={handleIngest}
          disabled={state === "transcribing" || !transcript.trim()}
          className="px-3 py-1.5 bg-stone-900 hover:bg-stone-800 disabled:bg-stone-300 text-white text-xs rounded"
        >
          {state === "transcribing" ? "Ingesting…" : "Add voice note"}
        </button>
        {state === "ingested" && lastDocId && (
          <span className="text-xs text-emerald-700 truncate" title={lastDocId}>
            ✓ {lastDocId.slice(0, 16)}…
          </span>
        )}
      </div>
    </div>
  );
}
