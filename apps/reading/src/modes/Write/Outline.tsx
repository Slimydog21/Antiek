import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";
import { Link } from "react-router-dom";
import type { Editor } from "@tiptap/react";

import ModelPicker from "../../components/ModelPicker";
import {
  fetchComposerProjection,
  type ComposerCandidateView,
  type ComposerModelProjection,
} from "../../api/composerProjection";

import {
  createSection,
  type SectionResponse,
} from "../../lib/api";
import AIActionFailure from "../../shared/AIActionFailure";
import Thinking from "../../shared/Thinking";
import { toast } from "../../components/lemon/LemonToast";
import FloatMenu from "../shared/FloatMenu/FloatMenu";
import { useFloatMenuSelection } from "../shared/FloatMenu/useFloatMenuSelection";
import type { FloatMenuSelection } from "../shared/FloatMenu/useFloatMenuSelection";
import type { RewriteIntent } from "../shared/FloatMenu/floatMenuActions";
import type { PaletteDragPayload } from "../CreationStudio/BlockPalette";
import { parsePaletteDrag } from "./Repository/dragToOutline";
import { WriteEditor } from "./Editor/Editor";
import { EDIT_CAPTURE_POLICY } from "./EditCapture";
import SubAgentProposal from "./SubAgentProposal";
import { sectionProse } from "./sectionProse";
import VoiceToDraft from "./VoiceToDraft";
import Xray from "./Xray";
import {
  blockDisplayText,
  getSectionBlocks,
  moveBlock,
  placeBlock,
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
 * the shared Brain thinking beat, and is HONEST — an empty section asks for
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
  /** The piece's backing research folder (deliverables.investigation_root_id,
   * SPR-09 M1). It buckets the voice-to-draft VOICE_CAPTURED event (M4) and is
   * the parent of a spun sub-agent (M4). Falls back to the operator bucket. */
  investigationId?: string | null;
  /** The cockpit's section tab (1.n): show this section alone. Every
   * section stays MOUNTED underneath (hidden, never unmounted), so a tab
   * switch keeps each editor, its draft and its pending save (F-02:
   * "never losing an edit on a tab switch"). null = the whole piece. */
  scopeSectionId?: string | null;
}

export default function Outline({
  deliverableId,
  sections,
  onChanged,
  registerAddHandler,
  investigationId,
  scopeSectionId = null,
}: OutlineProps) {
  // A scope naming no section of this piece shows the whole piece.
  const scoped = scopeSectionId !== null && sections.some((s) => s.section_id === scopeSectionId);
  // The section a tapped repository block lands in: the scoped section, else
  // the last one (the writer is composing top-down). A null active section
  // means "no section yet"; the tap then nudges the writer to add one.
  const activeSection = scoped
    ? sections.find((s) => s.section_id === scopeSectionId)!
    : sections.length
      ? sections[sections.length - 1]
      : null;
  const activeSectionId = activeSection?.section_id ?? null;

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
  const activeBlockCount = activeSection?.block_count ?? 0;
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
              key={`${deliverableId}:${s.section_id}`}
              deliverableId={deliverableId}
              section={s}
              sectionNumber={i + 1}
              hidden={scoped && s.section_id !== scopeSectionId}
              onChanged={onChanged}
              investigationId={investigationId ?? "__operator__"}
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
  hidden = false,
  onChanged,
  investigationId,
}: {
  deliverableId: string;
  section: SectionResponse;
  sectionNumber: number;
  /** Out of the cockpit's section scope: kept mounted, not shown. */
  hidden?: boolean;
  onChanged: () => Promise<void> | void;
  investigationId: string;
}) {
  const [blocks, setBlocks] = useState<OutlineBlockView[]>([]);
  const [dropHover, setDropHover] = useState(false);
  const [busy, setBusy] = useState(false);

  const [proseSession] = useState(() =>
    sectionProse(deliverableId, section.section_id, section.prose_text, section.prose_provenance ?? {}),
  );
  const prose = useSyncExternalStore(proseSession.subscribe, proseSession.getSnapshot);
  const generating = prose.generation.status === "generating";
  const genResult = prose.generation.status === "result" ? prose.generation.result : null;
  const genError = prose.generation.status === "error" ? prose.generation : null;
  const saveState = prose.save;
  const draftContent = prose.draft === null ? null : proseToEditorHtml(prose.draft);
  const draftRevision = prose.revision;
  const proseText = prose.saved;
  const proseProvenance = prose.provenance;
  const [projection, setProjection] = useState<ComposerModelProjection | null>(null);
  const [projectionError, setProjectionError] = useState<string | null>(null);
  const [modelChoice, setModelChoice] = useState<ComposerCandidateView | null>(null);
  const editorRef = useRef<Editor | null>(null);
  const handleContentChange = useCallback((text: string) => {
    proseSession.edit(text, editorRef.current?.getJSON() ?? null);
  }, [proseSession]);
  const [view, setView] = useState<"draft" | "xray">("draft");
  const [proposal, setProposal] = useState<{ text: string } | null>(null);
  // F7: the child investigation a sub-agent accept actually spawned. The
  // proposal PRODUCES this id (SubAgentProposal.tsx calls
  // `onAccept(child.investigation_id)`); it used to be discarded here, so the
  // writer paid for a spawn and had no way back to it. Retained and linked
  // below, mirroring the Reading companion's child-investigation row
  // (modes/Reading/ReadingCompanion.tsx:259).
  const [spawnedChild, setSpawnedChild] = useState<string | null>(null);

  // M4: the FloatMenu host over the rendered editor. The page region is the
  // selection SCOPE; highlighting prose opens the SHARED FloatMenu with the
  // Write-only rewrite actions (imported, not re-implemented — D-3).
  const editorScopeRef = useRef<HTMLDivElement>(null);
  const selection = useFloatMenuSelection({ scopeRef: editorScopeRef, minLength: 4 });

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

  useEffect(() => {
    proseSession.seed(section.prose_text, section.prose_provenance ?? {});
  }, [proseSession, section.prose_text, section.prose_provenance]);

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

  useEffect(() => {
    const editor = editorRef.current;
    if (editor && prose.document && JSON.stringify(editor.getJSON()) !== JSON.stringify(prose.document)) {
      editor.commands.setContent(prose.document, { emitUpdate: false });
    }
    editor?.setEditable(prose.available && !generating, false);
  }, [prose.available, prose.document, generating, draftRevision, draftContent]);

  async function handleGenerate() {
    editorRef.current?.setEditable(false, false);
    await proseSession.generate();
  }

  // M3 + M4: regenerate the section (the drag-in-X-ray gesture, and the
  // rewrite / make-stronger actions, both regenerate this section from its
  // blocks via the SHIPPED generate path — never a new model path). The
  // creative_writer re-anchors per-block, so the regenerated prose stays cited.
  const handleGenerateRef = useRef(handleGenerate);
  handleGenerateRef.current = handleGenerate;
  const handleRegenerate = useCallback(
    async (_paragraphIndex?: number) => {
      // This sprint's generate endpoint is section-granular (creative_writer
      // expands a section). A per-paragraph regenerate maps onto a section
      // regenerate that re-anchors all paragraphs; the affected paragraph is
      // necessarily refreshed. (A true single-paragraph endpoint is a named
      // follow-up — see handoff Open questions.)
      await handleGenerateRef.current();
    },
    [],
  );

  // M4: the FloatMenu rewrite intents → the SHIPPED paths.
  const onRewrite = useCallback(
    (intent: RewriteIntent, _sel: FloatMenuSelection) => {
      // §9.0: a withheld selection arrives as null — refuse, never send a
      // withheld body to a model or a spawn.
      if (intent.safeText === null) {
        toast.warn(
          "That selection includes a restricted source, so it can't be sent to rewrite or a sub-agent.",
        );
        return;
      }
      window.getSelection()?.removeAllRanges(); // collapse so the menu closes
      if (intent.kind === "sub_agent") {
        // Spin-a-sub-agent → launch a search + return an accept/reject proposal.
        setProposal({ text: intent.safeText });
        return;
      }
      // rewrite / make stronger → regenerate the section from its blocks (the
      // cited, per-block creative_writer path). The highlighted span sits in
      // the section being regenerated.
      void handleRegenerate();
    },
    [handleRegenerate],
  );

  // CK-5: apply the model's edited span AS AN EDITOR TRANSACTION over the
  // selected text (the editor's own selection when it still holds that text,
  // else the text's first place in a paragraph). The editor's onUpdate then
  // captures and autosaves it exactly as it would a keystroke, so the editor,
  // the X-ray and the server agree (R3-M5: splicing the X-ray's copy alone
  // left the edit nowhere a reload or the next keystroke could keep it).
  const handleApplyEdit = useCallback(
    (editedText: string, sel: FloatMenuSelection) => {
      if (proseSession.getSnapshot().generation.status === "generating") {
        toast.warn("Wait for the draft to finish before applying this edit.");
        return;
      }
      if (!sel.text) return;
      const ed = editorRef.current;
      const range = ed ? locateText(ed, sel.text) : null;
      if (!ed || !range) {
        toast.warn("That passage changed before the edit came back, so the edit was not applied.");
        return;
      }
      ed.view.dispatch(ed.state.tr.insertText(editedText, range.from, range.to));
      window.getSelection()?.removeAllRanges();
    },
    [proseSession],
  );

  const canGenerate = prose.dispatchAllowed && blocks.length > 0 && !generating;

  // Advisory model-driver projection for the writing surface (BYOT directive).
  // The picker choice is recorded locally and shown honestly as advisory: the
  // shipped generate endpoint (generateSection) does not yet accept an
  // owner-model authority for the writing path — binding is a documented
  // follow-up (HANDOFF-2026-08-12). Never fabricates a bound selection.
  useEffect(() => {
    let cancelled = false;
    void fetchComposerProjection({
      task: "writing",
      bounded_usage: [
        { unit: "input_token", maximum: 50_000 },
        { unit: "output_token", maximum: 20_000 },
      ],
    })
      .then((r) => {
        if (!cancelled) {
          setProjection(r);
          setProjectionError(null);
        }
      })
      .catch((e: unknown) => {
        if (!cancelled) {
          setProjectionError(e instanceof Error ? e.message : String(e));
          setProjection(null);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <section
      hidden={hidden}
      data-section-card={section.section_id}
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
        (dropHover ? "border-sun-deep ring-2 ring-sun/40" : "border-rule dark:border-charcoal-1")
      }
    >
      <header className="mb-2 flex items-baseline justify-between gap-3">
        <h3 className="font-serif text-base font-semibold text-ink dark:text-bright">
          <span className="mr-2 text-xs text-ink-mute dark:text-moonlight">{sectionNumber}.</span>
          {section.title || "(untitled section)"}
        </h3>
        {busy && <span className="text-xs text-ink-mute dark:text-moonlight">working…</span>}
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
              className="flex cursor-grab items-start gap-2 rounded border-l-2 border-sun-deep/50 bg-sun-deep/5 py-1.5 pl-2 pr-2 active:cursor-grabbing"
              title="Drag to reorder"
            >
              <span className="mt-1 shrink-0 font-mono text-xxs font-bold uppercase tracking-wider text-sun-deep">
                {provenanceLabel(b)}
              </span>
              <p className="min-w-0 flex-1 font-serif text-sm leading-relaxed text-ink dark:text-bright">
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
      <div className="flex flex-wrap items-center gap-3">
        {projection && (
          <ModelPicker
            candidates={projection.ranked_candidates}
            selected={modelChoice ? { provider: modelChoice.provider, model: modelChoice.model } : null}
            onSelect={(c) => setModelChoice(c)}
            error={projectionError}
            label="Model driver"
            note={
              modelChoice
                ? `Advisory — "${modelChoice.provider} / ${modelChoice.model}" recorded for this draft; the writing endpoint binds server-authority in a follow-up.`
                : "Advisory — leave Auto for the curated default."
            }
          />
        )}
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
        {/* M4: speak an idea into the section as a user-sourced block. */}
        <VoiceToDraft
          sectionId={section.section_id}
          deliverableId={deliverableId}
          investigationId={investigationId}
          blockIndex={blocks.length}
          onDrafted={async () => {
            await refreshBlocks();
            await onChanged();
          }}
        />
        {/* M3: draft ↔ X-ray toggle (shown once there's persisted prose). */}
        {proseText && (
          <button
            type="button"
            onClick={() => setView((v) => (v === "xray" ? "draft" : "xray"))}
            className="text-xs text-ink-soft underline hover:text-ink dark:text-starlight"
          >
            {view === "xray" ? "draft" : "X-ray"}
          </button>
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

      {/* M4: the spin-a-sub-agent proposal (search + accept/reject). */}
      {proposal && (
        <div className="mt-3">
          <SubAgentProposal
            claimText={proposal.text}
            parentInvestigationId={investigationId}
            onAccept={(childInvestigationId) => {
              setProposal(null);
              setSpawnedChild(childInvestigationId);
            }}
            onReject={() => setProposal(null)}
          />
        </div>
      )}

      {/* F7: the accepted child investigation returns to its writer. The spawn
          already happened; without this the id lived only in the callback. */}
      {spawnedChild && (
        <div
          data-testid="write-sub-agent-spawned"
          className="mt-3 flex items-center justify-between gap-2 rounded-md border border-rule bg-ice-0 px-3 py-2 text-sm dark:bg-charcoal-2"
        >
          <span className="text-shadow-1 dark:text-moonlight">
            Sub-agent research started.
          </span>
          <span className="flex items-center gap-3">
            <Link
              to={`/inv/${encodeURIComponent(spawnedChild)}`}
              className="font-mono text-xs text-shadow-1 hover:text-ink hover:underline dark:text-moonlight dark:hover:text-bright"
            >
              open research
            </Link>
            <button
              type="button"
              onClick={() => setSpawnedChild(null)}
              className="font-mono text-xs text-shadow-1 hover:text-ink dark:text-moonlight dark:hover:text-bright"
            >
              dismiss
            </button>
          </span>
        </div>
      )}

      {/* M3 X-ray view — paragraph ↔ blocks over the PERSISTED provenance.
          Toggled with the draft; no edit loss (the editor stays mounted,
          hidden, while the X-ray reads the persisted map). */}
      {view === "xray" && proseText && (
        <div className="mt-3 rounded border border-rule p-3 dark:border-charcoal-1">
          <Xray
            proseText={proseText}
            proseProvenance={proseProvenance}
            blocks={blocks}
            // `idx` is the affected paragraph; handleRegenerate intentionally
            // re-drafts the whole SECTION this sprint (the shipped endpoint is
            // section-granular — D-2/D-3). The index is passed through for when
            // a per-paragraph endpoint lands; today it is deliberately ignored.
            onRegenerateParagraph={(idx) => void handleRegenerate(idx)}
          />
        </div>
      )}

      {/* The real editor (M4) — mounted when a draft generated. Edits are
          CAPTURED only (EDIT_CAPTURE_POLICY: train is false, gated G8/Loop-3).
          The bare textarea is retired; this is the editing surface. The editor
          region is the FloatMenu selection SCOPE: highlighting prose opens the
          SHARED FloatMenu with Write's rewrite actions (imported, D-3). */}
      {draftContent != null && (
        <div
          data-write-editor-host=""
          // Hidden, never unmounted, during the X-ray: the editor keeps its
          // document and its undo history across the toggle (R3-H2).
          hidden={view === "xray"}
          className="mt-3 rounded border border-rule p-3 dark:border-charcoal-1"
        >
          {generating && (
            <p role="status" className="mb-2 text-xs text-ink-mute dark:text-moonlight">
              Generating a draft… Editing will resume when it finishes.
            </p>
          )}
          {genResult?.status === "generated" &&
            genResult.unsupported_paragraphs &&
            genResult.unsupported_paragraphs.length > 0 && (
              <p className="mb-2 text-xs text-shadow-1 dark:text-moonlight">
                {genResult.unsupported_paragraphs.length} paragraph(s) flagged
                unsupported — verify before keeping.
              </p>
            )}
          <div ref={editorScopeRef}>
            <WriteEditor
              key={draftRevision}
              editorRef={editorRef}
              deliverableId={deliverableId}
              sectionId={section.section_id}
              initialContent={draftContent}
              investigationId={investigationId}
              // SPR-02: persist coarse prose_text on edit (mirrors the shape
              // CreationStudio uses), debounced, with an honest save indicator.
              onContentChange={handleContentChange}
            />
          </div>
          {/* The SHARED FloatMenu (imported), extended with Write's rewrite
              actions via the rewriteActions prop. Read/Research hosts pass
              nothing → unchanged. onDeepResearch reuses the spawn path. */}
          <FloatMenu
            selection={selection}
            investigationId={investigationId}
            onDeepResearch={(safeText) => {
              if (safeText === null) return;
              window.getSelection()?.removeAllRanges();
              setProposal({ text: safeText });
            }}
            rewriteActions={{ onRewrite }}
            editContext={{ deliverableId, sectionId: section.section_id }}
            onApplyEdit={handleApplyEdit}
          />
          {/* Honest save indicator (SPR-02). The "saved as you write" promise
              is now backed by real persistence state: it never reads "saved"
              while a save is pending or has failed. (Capture-not-train boundary
              from SPR-07 M4 still holds — EDIT_CAPTURE_POLICY.capture records
              edits and trains NO model; that is gated in EditCapture.ts.) */}
          {EDIT_CAPTURE_POLICY.capture && (
            <div
              className="mt-2 flex items-center gap-2 text-xxs"
              role="status"
              aria-live="polite"
            >
              {saveState.status === "idle" && (
                <span className="text-ink-mute dark:text-moonlight">
                  Your edits are saved as you write.
                </span>
              )}
              {saveState.status === "pending" && (
                <span className="text-ink-mute dark:text-moonlight">Saving…</span>
              )}
              {saveState.status === "paused" && (
                <span className="text-ink-mute dark:text-moonlight">Your edit is kept here. Saving will resume after sign-in is confirmed.</span>
              )}
              {saveState.status === "saved" && (
                <span className="text-ink-mute dark:text-moonlight">Saved.</span>
              )}
              {saveState.status === "error" && (
                <span className="flex items-center gap-2 text-emperor">
                  <span>Couldn&rsquo;t save your last edit ({saveState.message}).</span>
                  <button
                    type="button"
                    onClick={() => void proseSession.flush()}
                    className="underline"
                  >
                    Retry
                  </button>
                </span>
              )}
            </div>
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

/** Where `text` sits in the editor: its own selection when that still holds
 *  the text (whitespace-insensitive), else the first paragraph containing it.
 *  Null when the text is no longer in the document. */
function locateText(ed: Editor, text: string): { from: number; to: number } | null {
  const norm = (s: string) => s.replace(/\s+/g, " ").trim();
  const want = norm(text);
  if (!want) return null;
  const { from, to } = ed.state.selection;
  if (to > from && norm(ed.state.doc.textBetween(from, to, " ")) === want) return { from, to };
  const needle = text.trim();
  let found: { from: number; to: number } | null = null;
  ed.state.doc.descendants((node, pos) => {
    if (found) return false;
    if (!node.isTextblock) return true;
    const at = node.textContent.indexOf(needle);
    if (at < 0) return false;
    const start = textblockPos(node, pos, at);
    const end = textblockPos(node, pos, at + needle.length);
    if (start != null && end != null) found = { from: start, to: end };
    return false;
  });
  return found;
}

/** The document position of character `index` of a textblock's text. */
function textblockPos(
  block: Editor["state"]["doc"],
  blockPos: number,
  index: number,
): number | null {
  let seen = 0;
  let result: number | null = null;
  block.forEach((child, offset) => {
    if (result != null) return;
    const len = child.isText ? (child.text ?? "").length : child.textContent.length;
    if (child.isText && index <= seen + len) result = blockPos + 1 + offset + (index - seen);
    seen += len;
  });
  return result;
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
