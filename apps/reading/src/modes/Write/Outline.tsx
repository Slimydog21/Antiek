import { useCallback, useEffect, useState } from "react";

import { ApiError, createSection, type SectionResponse } from "../../lib/api";
import AIActionFailure from "../../shared/AIActionFailure";
import Thinking from "../../shared/Thinking";
import type { PaletteDragPayload } from "../CreationStudio/BlockPalette";
import { parsePaletteDrag } from "./Repository/dragToOutline";
import { WriteEditor } from "./Editor/Editor";
import { EDIT_CAPTURE_POLICY } from "./EditCapture";
import {
  blockDisplayText,
  generateSection,
  getSectionBlocks,
  moveBlock,
  placeBlock,
  type GenerationResult,
  type OutlineBlockView,
  type RepositoryHit,
} from "./writeApi";

/**
 * The outline — arrange blocks, reorder, add sections, generate, edit
 * (Product Depth SPR-07 M2+M3+M4).
 *
 * The legible heart of the Write loop, beside the block repository. Blocks
 * land in a section by TAP (the repository's onAdd) or DRAG (the shipped
 * `PaletteDragPayload` envelope), reorder within/across sections by drag, and
 * sections add inline. It reads like an outline, not a form, and — the
 * load-bearing SPR-07 invariant — NO id is ever rendered: a block shows its
 * text + provenance, never its `node_id`/`outline_block_id`.
 *
 * It is the input the draft generation consumes: one "Generate draft" button
 * per section calls the shipped `/write/sections/{id}/generate` endpoint with
 * the shared Werner thinking beat, and is HONEST — an empty section asks for
 * blocks (never a hang), no key surfaces `AIActionFailure` (never a fake
 * draft), a gap/gate-fail is shown plainly. Generated prose loads into the
 * shipped `WriteEditor` (the real TipTap surface, retiring the textarea),
 * where edits are CAPTURED — and only captured (`EDIT_CAPTURE_POLICY`;
 * training is gated G8/Loop-3).
 *
 * The data model is the shipped §10 one (deliverable → sections → outline
 * blocks); this surface composes it, it does not invent a parallel shape.
 */

export interface OutlineProps {
  deliverableId: string;
  /** The deliverable's sections (from getDeliverable). */
  sections: SectionResponse[];
  /** Refresh the deliverable after a section/block change. */
  onChanged: () => Promise<void> | void;
  /** A tap-to-add request the host wires to the active section (M1↔M2). */
  registerAddHandler?: (handler: (hit: RepositoryHit) => void) => void;
}

export default function Outline({
  deliverableId,
  sections,
  onChanged,
  registerAddHandler,
}: OutlineProps) {
  // The section a tapped repository block lands in (the last section, by
  // default — the writer is composing top-down). A null active section means
  // "no section yet"; the tap then nudges the writer to add one.
  const activeSectionId = sections.length ? sections[sections.length - 1].section_id : null;

  const addTappedBlock = useCallback(
    async (hit: RepositoryHit, sectionId: string | null, blockCount: number) => {
      if (!sectionId) return;
      await placeBlock({
        section_id: sectionId,
        block_kind: "insight",
        provenance_kind: "graph_node",
        node_id: hit.node_id, // the SAME node — provenance preserved, no copy
        block_index: blockCount,
        deliverable_id: deliverableId,
      });
      await onChanged();
    },
    [deliverableId, onChanged],
  );

  // Expose a tap handler bound to the active (last) section so the sibling
  // repository can place into the outline. The handler is re-registered when
  // the active section or its block count changes.
  const activeBlockCount =
    sections.length ? sections[sections.length - 1].block_count : 0;
  useEffect(() => {
    registerAddHandler?.((hit) =>
      void addTappedBlock(hit, activeSectionId, activeBlockCount),
    );
  }, [registerAddHandler, addTappedBlock, activeSectionId, activeBlockCount]);

  return (
    <div className="flex h-full min-h-0 flex-col" data-mode="write-outline">
      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto pr-1">
        {sections.length === 0 ? (
          <p className="px-1 py-6 font-serif text-sm italic text-ink-mute dark:text-moonlight">
            An empty outline. Add a section below, then tap blocks from your
            repository (or drag them) to build it up.
          </p>
        ) : (
          sections.map((s, i) => (
            <SectionCard
              key={s.section_id}
              deliverableId={deliverableId}
              section={s}
              sectionNumber={i + 1}
              onChanged={onChanged}
            />
          ))
        )}
      </div>

      <NewSectionForm
        deliverableId={deliverableId}
        nextIndex={sections.length}
        onCreated={onChanged}
      />
    </div>
  );
}

function SectionCard({
  deliverableId,
  section,
  sectionNumber,
  onChanged,
}: {
  deliverableId: string;
  section: SectionResponse;
  sectionNumber: number;
  onChanged: () => Promise<void> | void;
}) {
  const [blocks, setBlocks] = useState<OutlineBlockView[]>([]);
  const [dropHover, setDropHover] = useState(false);
  const [busy, setBusy] = useState(false);

  // Generation state (M3).
  const [generating, setGenerating] = useState(false);
  const [genResult, setGenResult] = useState<GenerationResult | null>(null);
  const [genError, setGenError] = useState<{ reason: string | null } | null>(null);
  // The prose loaded into the real editor (M4). null = not yet generated.
  const [draftContent, setDraftContent] = useState<string | null>(null);

  const refreshBlocks = useCallback(async () => {
    try {
      setBlocks(await getSectionBlocks(section.section_id));
    } catch {
      setBlocks([]);
    }
  }, [section.section_id]);

  useEffect(() => {
    void refreshBlocks();
  }, [refreshBlocks, section.block_count]);

  async function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    setDropHover(false);
    const payload: PaletteDragPayload | null = parsePaletteDrag(e.dataTransfer);
    if (!payload) return;
    setBusy(true);
    try {
      await placeBlock({
        section_id: section.section_id,
        block_kind: "insight",
        provenance_kind: "graph_node",
        node_id: payload.block_id,
        block_index: blocks.length,
        deliverable_id: deliverableId,
      });
      await refreshBlocks();
      await onChanged();
    } finally {
      setBusy(false);
    }
  }

  // Reorder within the section by drag (M2). The dragged block carries its
  // outline_block_id in dataTransfer; the drop computes the new index.
  const REORDER_MIME = "application/x-antiek-outline-block";

  async function handleReorderDrop(e: React.DragEvent, toIndex: number) {
    const obid = e.dataTransfer.getData(REORDER_MIME);
    if (!obid) return;
    e.preventDefault();
    e.stopPropagation();
    setBusy(true);
    try {
      await moveBlock(obid, section.section_id, toIndex);
      await refreshBlocks();
      await onChanged();
    } finally {
      setBusy(false);
    }
  }

  async function handleGenerate() {
    setGenerating(true);
    setGenResult(null);
    setGenError(null);
    try {
      const r = await generateSection(section.section_id);
      setGenResult(r);
      if (r.status === "generated" && r.prose_text) {
        // Load the real prose into the editor (M4). Plain prose becomes
        // editable paragraphs; the editor mounts in place of the textarea.
        setDraftContent(proseToEditorHtml(r.prose_text));
      }
    } catch (e) {
      // Honest no-key / no-result: a 503 (provider not configured) or any
      // backend abort surfaces AIActionFailure — never a fabricated draft.
      const reason = e instanceof ApiError && e.status === 503 ? null : String(e);
      setGenError({ reason: reason === "null" ? null : reason });
    } finally {
      setGenerating(false);
    }
  }

  const canGenerate = blocks.length > 0 && !generating;

  return (
    <section
      onDragOver={(e) => {
        if (e.dataTransfer.types.includes("application/x-antiek-block")) {
          e.preventDefault();
          e.dataTransfer.dropEffect = "copy";
          setDropHover(true);
        }
      }}
      onDragLeave={() => setDropHover(false)}
      onDrop={handleDrop}
      className={
        "rounded-md border bg-ice-0 p-4 transition-colors dark:bg-charcoal-2 " +
        (dropHover ? "border-ocean ring-2 ring-ocean/40" : "border-rule dark:border-charcoal-1")
      }
    >
      <header className="mb-2 flex items-baseline justify-between gap-3">
        <h3 className="font-serif text-base font-semibold text-ink dark:text-bright">
          <span className="mr-2 text-xs text-ink-mute dark:text-moonlight">{sectionNumber}.</span>
          {section.title || "(untitled section)"}
        </h3>
        {busy && <span className="text-[11px] text-ink-mute dark:text-moonlight">working…</span>}
      </header>

      {/* Blocks — text + provenance only, never an id (SPR-07 M2 no-UUID gate). */}
      {blocks.length > 0 ? (
        <ol className="mb-3 space-y-1">
          {blocks.map((b, idx) => (
            <li
              key={b.outline_block_id}
              draggable
              onDragStart={(e) => {
                e.dataTransfer.setData(REORDER_MIME, b.outline_block_id);
                e.dataTransfer.effectAllowed = "move";
              }}
              onDragOver={(e) => {
                if (e.dataTransfer.types.includes(REORDER_MIME)) {
                  e.preventDefault();
                  e.dataTransfer.dropEffect = "move";
                }
              }}
              onDrop={(e) => void handleReorderDrop(e, idx)}
              className="flex cursor-grab items-start gap-2 rounded border-l-2 border-ocean/50 bg-ocean/5 py-1.5 pl-2 pr-2 active:cursor-grabbing"
              title="Drag to reorder"
            >
              <span className="mt-1 shrink-0 font-mono text-[10px] font-bold uppercase tracking-wider text-ocean">
                {provenanceLabel(b)}
              </span>
              <p className="min-w-0 flex-1 font-serif text-[14px] leading-relaxed text-ink dark:text-bright">
                {blockDisplayText(b)}
              </p>
            </li>
          ))}
        </ol>
      ) : (
        <p className="mb-3 text-xs italic text-ink-mute dark:text-moonlight">
          Empty. Tap a block from your repository, or drag one here.
        </p>
      )}

      {/* Generate (M3) + honest states. */}
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={() => void handleGenerate()}
          disabled={!canGenerate}
          title={
            blocks.length === 0
              ? "Add blocks first — a draft is written from your blocks, never fabricated."
              : "Generate a cited draft from these blocks"
          }
          className="rounded bg-ink px-3 py-1.5 text-sm text-white hover:bg-shadow-2 disabled:bg-glacial-1 dark:disabled:bg-slate-1"
        >
          Generate draft
        </button>
        {generating && <Thinking size={24} status="drafting from your blocks…" />}
        {blocks.length === 0 && (
          <span className="text-xs text-ink-mute dark:text-moonlight">
            Add at least one block to draft from.
          </span>
        )}
      </div>

      {/* Honest failure (no key / abort) — never a fake draft. */}
      {genError && (
        <AIActionFailure
          className="mt-3"
          title="The draft didn't complete"
          reason={genError.reason}
          onRetry={() => void handleGenerate()}
        />
      )}

      {/* Honest non-failure non-prose outcomes. */}
      {genResult?.status === "gap" && (
        <p className="mt-3 text-xs italic text-ink-mute dark:text-moonlight">
          {genResult.detail ?? "Nothing to draft yet — add blocks first."}
        </p>
      )}
      {genResult?.status === "gate_failed" && (
        <p className="mt-3 text-xs text-emperor">
          The draft didn't meet the voice and style bar — {genResult.detail ?? "left unkept."}
        </p>
      )}

      {/* The real editor (M4) — mounted when a draft generated. Edits are
          CAPTURED only (EDIT_CAPTURE_POLICY: train is false, gated G8/Loop-3).
          The bare textarea is retired; this is the editing surface. */}
      {draftContent != null && (
        <div className="mt-3 rounded border border-rule p-3 dark:border-charcoal-1">
          {genResult?.status === "generated" &&
            genResult.unsupported_paragraphs &&
            genResult.unsupported_paragraphs.length > 0 && (
              <p className="mb-2 text-[11px] text-shadow-1 dark:text-moonlight">
                {genResult.unsupported_paragraphs.length} paragraph(s) flagged
                unsupported — verify before keeping.
              </p>
            )}
          <WriteEditor
            deliverableId={deliverableId}
            sectionId={section.section_id}
            initialContent={draftContent}
            className="font-serif text-[15px] leading-relaxed text-ink dark:text-bright"
          />
          {/* capture-not-train boundary (SPR-07 M4): the editor records edits
              (EDIT_CAPTURE_POLICY.capture); it trains NO model — that is gated.
              The assertion lives in EditCapture.ts; this footer is the visible
              acknowledgement to the writer, not a training trigger. */}
          {EDIT_CAPTURE_POLICY.capture && (
            <p className="mt-2 text-[10px] text-ink-mute dark:text-moonlight">
              Your edits are saved as you write.
            </p>
          )}
        </div>
      )}
    </section>
  );
}

/** Human provenance label for a block — what kind, never an id. */
function provenanceLabel(b: OutlineBlockView): string {
  if (b.is_user_originated || b.provenance_kind !== "graph_node") return "yours";
  return b.block_kind === "open_question" ? "question" : b.block_kind;
}

/** Plain prose → editor HTML (paragraphs). Inline `[b: …]` citations the
 * model emits are left as text here; the structured citation chips are the
 * generation path's lossless `<antiek-cite>` round-trip, handled when the
 * generation endpoint emits structured content. */
function proseToEditorHtml(prose: string): string {
  return prose
    .split(/\n{2,}/)
    .map((p) => p.trim())
    .filter(Boolean)
    .map((p) => `<p>${escapeHtml(p)}</p>`)
    .join("");
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
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
      className="mt-3 flex items-center gap-2 rounded-md border border-dashed border-rule p-2 dark:border-charcoal-1"
    >
      <input
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        placeholder={`Add section #${nextIndex + 1}…`}
        className="flex-1 rounded border border-rule px-2 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-sun dark:border-charcoal-1"
      />
      <button
        type="submit"
        disabled={busy || !title.trim()}
        className="rounded bg-ink px-3 py-1.5 text-sm text-white hover:bg-shadow-2 disabled:bg-glacial-1 dark:disabled:bg-slate-1"
      >
        Add section
      </button>
    </form>
  );
}
