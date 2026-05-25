import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";

import { PanelHost } from "../../workspace/PanelHost";
import {
  attachBlock,
  createSection,
  exportDeliverable,
  getDeliverable,
  reorderBlock,
  updateSectionProse,
  type BlockKind,
  type DeliverableDetailResponse,
  type DeliverableKind,
  type ExportFormatName,
  type SectionResponse,
} from "../../lib/api";
import {
  DRAG_MIME,
  type PaletteDragPayload,
} from "./BlockPalette";
import { WriteEditor } from "../Write/Editor/Editor";

interface SectionDragPayload {
  from: "section";
  section_id: string;
  block_kind: BlockKind;
  block_id: string;
  block_index: number;
}

type DragPayload = PaletteDragPayload | SectionDragPayload;


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
/**
 * Mode C — Creation Studio.
 *
 * S10 row 10.7: "/create — left = block palette panel; right = preview
 * panel." Ported onto PanelHost with two starters:
 *   - DeliverableSidebar  docked-left  (deliverable list + voice note)
 *   - BlockPalette        docked-right (drag-drop block source)
 * The main slot renders DeliverableDetail (the canvas). The "preview"
 * panel the spec named is the export-ready Markdown render; for now
 * the operator gets it via DeliverableDetail's "Export" buttons —
 * dedicated preview panel is tracked as a follow-up.
 */
export default function CreationStudio() {
  return (
    <PanelHost
      starters={[
        {
          kind: "DeliverableSidebar",
          mode: "docked-left",
          title: "Deliverables",
          id: "create:deliverable-sidebar",
        },
        {
          kind: "BlockPalette",
          mode: "docked-right",
          title: "Block palette",
          id: "create:block-palette",
        },
      ]}
    >
      <div className="h-full bg-ice-1 dark:bg-charcoal-2 overflow-auto">
        <div className="max-w-4xl mx-auto px-6 py-6">
          <DeliverableDetail />
        </div>
      </div>
    </PanelHost>
  );
}

// DeliverableSidebar + VoiceNoteCapture extracted to sibling files
// for panel-system registration. See ./DeliverableSidebar.tsx and
// ./VoiceNoteCapture.tsx.

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
      <section className="flex items-center justify-center h-full text-shadow-1 dark:text-moonlight text-sm">
        Select or create a deliverable to begin.
      </section>
    );
  }
  if (loading && !detail) {
    return (
      <section className="text-shadow-1 dark:text-moonlight text-sm">Loading deliverable…</section>
    );
  }
  if (!detail) {
    return (
      <section className="text-shadow-1 dark:text-moonlight text-sm">
        Deliverable not found.
      </section>
    );
  }

  return (
    <section className="overflow-y-auto pr-2">
      <header className="mb-6 flex items-baseline justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-wide text-shadow-1 dark:text-moonlight">
            {DELIVERABLE_KIND_LABELS[detail.deliverable_kind] ?? detail.deliverable_kind}
          </p>
          <h1 className="text-2xl font-semibold tracking-tight text-ink dark:text-bright">
            {detail.title}
          </h1>
        </div>
        <ExportButton deliverableId={detail.deliverable_id} />
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

function ExportButton({ deliverableId }: { deliverableId: string }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);

  async function doExport(format: ExportFormatName) {
    setBusy(true);
    try {
      const r = await exportDeliverable(deliverableId, format);
      const mime =
        format === "markdown"
          ? "text/markdown"
          : format === "html"
            ? "text/html"
            : "application/json";
      const blob = new Blob([r.content], { type: mime });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = r.filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      setOpen(false);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className="px-3 py-1.5 bg-ice-4 dark:bg-charcoal-1 hover:bg-glacial-1 dark:bg-slate-1 text-ink dark:text-bright text-sm rounded"
      >
        Export
      </button>
      {open && (
        <div className="absolute right-0 mt-1 bg-ice-0 dark:bg-charcoal-2 border border-rule dark:border-charcoal-1 rounded shadow-md text-xs z-10 min-w-[140px]">
          {(["markdown", "html", "json"] as ExportFormatName[]).map((f) => (
            <button
              key={f}
              onClick={() => void doExport(f)}
              disabled={busy}
              className="block w-full text-left px-3 py-1.5 hover:bg-ice-3 dark:bg-charcoal-1 disabled:text-ink-mute dark:text-moonlight"
            >
              {f === "markdown" ? "Markdown (.md)" : f === "html" ? "HTML (.html)" : "JSON bundle (.json)"}
            </button>
          ))}
        </div>
      )}
    </div>
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
  const [blockKind, setBlockKind] = useState<BlockKind>("insight");
  const [busy, setBusy] = useState(false);
  const [dropHover, setDropHover] = useState(false);

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

  async function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setDropHover(false);
    const raw = e.dataTransfer.getData(DRAG_MIME);
    if (!raw) return;
    let payload: DragPayload;
    try {
      payload = JSON.parse(raw);
    } catch {
      return;
    }
    setBusy(true);
    try {
      if (payload.from === "palette") {
        await attachBlock({
          section_id: section.section_id,
          block_kind: payload.block_kind,
          block_id: payload.block_id,
          block_index: section.block_count,
        });
      } else if (payload.from === "section") {
        if (payload.section_id === section.section_id) {
          // No-op: dropped onto its own section. Skip.
        } else {
          await reorderBlock({
            section_id: payload.section_id,
            block_kind: payload.block_kind,
            block_id: payload.block_id,
            new_section_id: section.section_id,
            new_block_index: section.block_count,
          });
        }
      }
      await onChanged();
    } finally {
      setBusy(false);
    }
  }

  return (
    <li
      onDragOver={(e) => {
        if (e.dataTransfer.types.includes(DRAG_MIME)) {
          e.preventDefault();
          e.dataTransfer.dropEffect = "copy";
          setDropHover(true);
        }
      }}
      onDragLeave={() => setDropHover(false)}
      onDrop={handleDrop}
      className={`bg-ice-0 dark:bg-charcoal-2 border rounded-md p-4 transition-colors ${
        dropHover
          ? "border-emerald-500 ring-2 ring-emerald-300"
          : "border-rule dark:border-charcoal-1"
      }`}
    >
      <div className="flex items-baseline justify-between gap-3">
        <div>
          <p className="text-xs text-shadow-1 dark:text-moonlight">
            Section {section.section_index + 1}
          </p>
          <h2 className="text-base font-semibold text-ink dark:text-bright">
            {section.title || "(untitled)"}
          </h2>
        </div>
        <span className="text-xs text-shadow-1 dark:text-moonlight">
          {section.block_count} blocks
        </span>
      </div>

      <ProseEditor section={section} onSaved={onChanged} />


      <div className="mt-3 flex items-center gap-2">
        <button
          onClick={() => setShowAttach((v) => !v)}
          className="text-xs text-ink-soft dark:text-starlight hover:text-ink dark:text-bright underline"
        >
          {showAttach ? "Cancel" : "Attach by id"}
        </button>
        <span className="text-xs text-ink-mute dark:text-moonlight">
          · or drag from the palette →
        </span>
        {busy && <span className="text-xs text-ink-mute dark:text-moonlight">working…</span>}
      </div>

      {showAttach && (
        <form
          onSubmit={handleAttach}
          className="mt-3 flex items-center gap-2"
        >
          <select
            value={blockKind}
            onChange={(e) => setBlockKind(e.target.value as BlockKind)}
            className="px-2 py-1 text-xs border border-rule dark:border-charcoal-1 rounded"
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
            className="flex-1 px-2 py-1 text-xs font-mono border border-rule dark:border-charcoal-1 rounded"
          />
          <button
            type="submit"
            disabled={busy || !blockId.trim()}
            className="px-3 py-1 bg-ink hover:bg-shadow-2 disabled:bg-glacial-1 dark:bg-slate-1 text-white text-xs rounded"
          >
            Attach
          </button>
        </form>
      )}
    </li>
  );
}

function ProseEditor({
  section,
  onSaved,
}: {
  section: SectionResponse;
  onSaved: () => Promise<void> | void;
}) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(section.prose_text || "");
  const [promote, setPromote] = useState(false);
  const [busy, setBusy] = useState(false);
  const [lastStatus, setLastStatus] = useState<"saved" | "saved_and_promoted" | null>(null);

  // If the section is refreshed from above with new prose, mirror it.
  useEffect(() => {
    setText(section.prose_text || "");
  }, [section.section_id, section.prose_text]);

  async function handleSave() {
    if (!text.trim()) return;
    setBusy(true);
    try {
      const r = await updateSectionProse(section.section_id, {
        prose_text: text,
        original_text: section.prose_text || undefined,
        promote_to_graph: promote,
      });
      setLastStatus(r.status);
      setEditing(false);
      await onSaved();
    } finally {
      setBusy(false);
    }
  }

  if (!editing) {
    return (
      <div className="mt-3">
        {section.prose_text ? (
          <p className="text-sm text-ink dark:text-bright whitespace-pre-line">
            {section.prose_text}
          </p>
        ) : (
          <p className="text-xs text-ink-mute dark:text-moonlight italic">
            No prose yet. Drag blocks from the palette →, then click
            Edit to add prose. (Sprint 14+ wires the creative_writer
            role to generate from attached blocks.)
          </p>
        )}
        <div className="mt-2 flex items-center gap-3">
          <button
            onClick={() => setEditing(true)}
            className="text-xs text-ink-soft dark:text-starlight hover:text-ink dark:text-bright underline"
          >
            Edit prose
          </button>
          {lastStatus && (
            <span
              className={`text-xs ${
                lastStatus === "saved_and_promoted"
                  ? "text-emerald-700"
                  : "text-shadow-1 dark:text-moonlight"
              }`}
            >
              {lastStatus === "saved_and_promoted"
                ? "✓ saved & promoted to graph"
                : "✓ saved"}
            </span>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="mt-3">
      {/* SPR-04: the structured TipTap block editor replaces the plain
          textarea. Granular edit.captured events flow automatically from
          inside WriteEditor; the coarse prose_text save path below stays
          for backward-compat with existing deliverables. */}
      <div className="w-full px-3 py-2 text-sm border border-rule dark:border-charcoal-1 rounded font-serif focus-within:ring-2 focus-within:ring-sun">
        <WriteEditor
          deliverableId={section.deliverable_id}
          sectionId={section.section_id}
          initialContent={text}
          onContentChange={setText}
        />
      </div>
      <div className="mt-2 flex items-center justify-between gap-3">
        <label className="flex items-center gap-1.5 text-xs text-ink dark:text-bright">
          <input
            type="checkbox"
            checked={promote}
            onChange={(e) => setPromote(e.target.checked)}
          />
          Promote to graph as operator-asserted claim
        </label>
        <div className="flex items-center gap-2">
          <button
            onClick={() => {
              setEditing(false);
              setText(section.prose_text || "");
            }}
            disabled={busy}
            className="px-3 py-1 text-xs text-ink-soft dark:text-starlight hover:text-ink dark:text-bright"
          >
            Cancel
          </button>
          <button
            onClick={handleSave}
            disabled={busy || !text.trim()}
            className="px-3 py-1 bg-ink hover:bg-shadow-2 disabled:bg-glacial-1 dark:bg-slate-1 text-white text-xs rounded"
          >
            {busy ? "Saving…" : promote ? "Save & promote" : "Save"}
          </button>
        </div>
      </div>
    </div>
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
      className="mt-6 bg-ice-0 dark:bg-charcoal-2 border border-dashed border-rule dark:border-charcoal-1 rounded-md p-3 flex items-center gap-2"
    >
      <input
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        placeholder={`New section title (will be #${nextIndex + 1})…`}
        className="flex-1 px-2 py-1.5 text-sm border border-rule dark:border-charcoal-1 rounded focus:outline-none focus:ring-2 focus:ring-sun"
      />
      <button
        type="submit"
        disabled={busy || !title.trim()}
        className="px-3 py-1.5 bg-ink hover:bg-shadow-2 disabled:bg-glacial-1 dark:bg-slate-1 text-white text-sm rounded"
      >
        Add section
      </button>
    </form>
  );
}

// VoiceNoteCapture moved to ./VoiceNoteCapture.tsx for panel reuse.
