import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";

import {
  ApiError,
  createSection,
  updateSectionProse,
  type SectionResponse,
} from "../../lib/api";
import AIActionFailure from "../../shared/AIActionFailure";
import Thinking from "../../shared/Thinking";
import FloatMenu from "../shared/FloatMenu/FloatMenu";
import { useFloatMenuSelection } from "../shared/FloatMenu/useFloatMenuSelection";
import type { FloatMenuSelection } from "../shared/FloatMenu/useFloatMenuSelection";
import type { RewriteIntent } from "../shared/FloatMenu/floatMenuActions";
import type { PaletteDragPayload } from "../CreationStudio/BlockPalette";
import { parsePaletteDrag } from "./Repository/dragToOutline";
import { WriteEditor } from "./Editor/Editor";
import { EDIT_CAPTURE_POLICY } from "./EditCapture";
import SubAgentProposal from "./SubAgentProposal";
import VoiceToDraft from "./VoiceToDraft";
import Xray from "./Xray";
import {
  blockDisplayText,
  commissionQuestionInterviews,
  generateSection,
  getSectionBlocks,
  moveBlock,
  placeBlock,
  type GenerationResult,
  type OutlineBlockView,
  type RepositoryHit,
} from "./writeApi";

export function blockKindForNodeType(
  nodeType: string,
): "insight" | "open_question" | "claim" | null {
  if (nodeType === "insight") return "insight";
  if (nodeType === "question") return "open_question";
  if (nodeType === "claim") return "claim";
  return null;
}

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

/** Debounce for autosaving a manual prose edit. Long enough to coalesce a
 * burst of keystrokes into one PATCH, short enough that a pause persists. */
const PROSE_SAVE_DEBOUNCE_MS = 800;

/** Honest save state for a section's prose. The "saved as you write" promise is
 * backed by this — it is never rendered "saved" while a save is pending/failed. */
type ProseSaveState =
  | { status: "idle" }
  | { status: "pending" }
  | { status: "saved" }
  | { status: "error"; message: string };

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
}

export default function Outline({
  deliverableId,
  sections,
  onChanged,
  registerAddHandler,
  investigationId,
}: OutlineProps) {
  // The section a tapped repository block lands in (the last section, by
  // default — the writer is composing top-down). A null active section means
  // "no section yet"; the tap then nudges the writer to add one.
  const activeSectionId = sections.length ? sections[sections.length - 1].section_id : null;

  const addTappedBlock = useCallback(
    async (hit: RepositoryHit, sectionId: string | null, blockCount: number) => {
      if (!sectionId) return;
      const blockKind = blockKindForNodeType(hit.node_type);
      if (!blockKind) return;
      await placeBlock({
        section_id: sectionId,
        block_kind: blockKind,
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
  onChanged,
  investigationId,
}: {
  deliverableId: string;
  section: SectionResponse;
  sectionNumber: number;
  onChanged: () => Promise<void> | void;
  investigationId: string;
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
  // M3: draft ↔ X-ray toggle. The X-ray reads the PERSISTED prose_provenance.
  const [view, setView] = useState<"draft" | "xray">("draft");
  // The persisted prose + provenance for the X-ray. Seeds from the section
  // (read back from GET /deliverables/{id}) so a reload still X-rays; updates
  // on each generation.
  const [proseText, setProseText] = useState<string | null>(section.prose_text);
  const [proseProvenance, setProseProvenance] = useState<Record<string, string[]>>(
    section.prose_provenance ?? {},
  );
  // M4: the spin-a-sub-agent proposal over a highlighted claim (null = closed).
  const [proposal, setProposal] = useState<{ text: string } | null>(null);

  // SPR-02: manual prose edits persist to prose_text — the SAME column export
  // (app.py:2890) and reload (app.py:2573) read. Mirrors CreationStudio's
  // updateSectionProse call shape, but debounced (onContentChange fires per
  // keystroke) and with an HONEST indicator: the persistence error is surfaced,
  // never swallowed the way the edit.captured telemetry is (Editor.tsx ~86).
  const [saveState, setSaveState] = useState<ProseSaveState>({ status: "idle" });
  // The value we know the server holds (seed = the section's persisted prose;
  // updated on generate, on a confirmed save, and on a parent re-fetch).
  const savedProseRef = useRef<string | null>(section.prose_text);
  // The most recent editor text, so a retry re-sends the current draft.
  const latestProseRef = useRef<string>(section.prose_text ?? "");
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const persistProse = useCallback(
    async (plainText: string) => {
      const original = savedProseRef.current;
      // Empty prose is rejected by the API (min_length=1) and would blank a
      // draft — mirror CreationStudio's non-empty guard.
      if (!plainText.trim()) return;
      // Unchanged since the last confirmed save — nothing to persist.
      if (plainText === original) {
        setSaveState({ status: "saved" });
        return;
      }
      setSaveState({ status: "pending" });
      try {
        await updateSectionProse(section.section_id, {
          prose_text: plainText,
          original_text: original ?? undefined,
          promote_to_graph: false,
        });
        savedProseRef.current = plainText;
        setProseText(plainText); // keep the X-ray / reload view in sync
        setSaveState({ status: "saved" });
      } catch (e) {
        // Do NOT swallow (contrast Editor.tsx's edit.captured .catch(()=>{})):
        // a lost save must be visible so the "saved" promise is never a lie.
        const message =
          e instanceof ApiError
            ? `HTTP ${e.status}`
            : e instanceof Error
              ? e.message
              : String(e);
        setSaveState({ status: "error", message });
      }
    },
    [section.section_id],
  );

  const handleContentChange = useCallback(
    (plainText: string) => {
      latestProseRef.current = plainText;
      // A keystroke means unsaved work is in flight — reflect it at once so a
      // stale "Saved" never sits over an edit mid-debounce.
      setSaveState({ status: "pending" });
      if (saveTimer.current) clearTimeout(saveTimer.current);
      saveTimer.current = setTimeout(() => {
        void persistProse(plainText);
      }, PROSE_SAVE_DEBOUNCE_MS);
    },
    [persistProse],
  );

  // Clear a pending debounce on unmount (never fire a save after teardown).
  useEffect(
    () => () => {
      if (saveTimer.current) clearTimeout(saveTimer.current);
    },
    [],
  );

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

  // Keep the persisted prose/provenance in sync if the section reloads.
  useEffect(() => {
    setProseText(section.prose_text);
    setProseProvenance(section.prose_provenance ?? {});
    // The re-fetched value is server truth — reset the autosave baseline so the
    // next edit diffs against it (not a stale local snapshot).
    savedProseRef.current = section.prose_text;
  }, [section.prose_text, section.prose_provenance]);

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
        // M3: capture the PERSISTED provenance so the X-ray can read it back
        // (the server persisted it via SECTION_DRAFT_GENERATED — the link
        // exists in the graph, this is just the immediate echo).
        setProseText(r.prose_text);
        setProseProvenance(r.prose_provenance ?? {});
        // The server persisted this prose (SECTION_DRAFT_GENERATED) — it is the
        // autosave baseline the first manual edit diffs against.
        savedProseRef.current = r.prose_text;
        setSaveState({ status: "idle" });
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

  // M3 + M4: regenerate the section (the drag-in-X-ray gesture, and the
  // rewrite / make-stronger actions, both regenerate this section from its
  // blocks via the SHIPPED generate path — never a new model path). The
  // creative_writer re-anchors per-block, so the regenerated prose stays cited.
  const handleRegenerate = useCallback(
    async (_paragraphIndex?: number) => {
      // This sprint's generate endpoint is section-granular (creative_writer
      // expands a section). A per-paragraph regenerate maps onto a section
      // regenerate that re-anchors all paragraphs; the affected paragraph is
      // necessarily refreshed. (A true single-paragraph endpoint is a named
      // follow-up — see handoff Open questions.)
      await handleGenerate();
    },
    // handleGenerate is stable enough for this sprint's surface.
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  );

  // M4: the FloatMenu rewrite intents → the SHIPPED paths.
  const onRewrite = useCallback(
    (intent: RewriteIntent, _sel: FloatMenuSelection) => {
      // §9.0: a withheld selection arrives as null — refuse, never send a
      // withheld body to a model or a spawn.
      if (intent.safeText === null) {
        window.alert(
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

  // CK-5: apply the model's edited span. Splice it into the section prose,
  // replacing the first occurrence of the current selection's text; the
  // existing prose-autosave then persists it (the same path a manual
  // keystroke takes), so provenance + single-writer discipline are unchanged.
  const handleApplyEdit = useCallback(
    (editedText: string) => {
      const sel = selection;
      if (!sel || !sel.text) return;
      setProseText((prev) => (prev == null ? prev : prev.replace(sel.text, editedText)));
      window.getSelection()?.removeAllRanges();
    },
    [selection],
  );

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
              {b.block_kind === "open_question" && b.provenance_kind === "graph_node" && (
                <CommissionInterviewButton
                  outlineBlockId={b.outline_block_id}
                  deliverableId={deliverableId}
                />
              )}
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
      {genResult?.status === "citation_failed" && (
        <p className="mt-3 text-xs text-emperor">
          The draft was not kept because its citations did not match the attached evidence —{" "}
          {genResult.detail ?? "regenerate before editing."}
        </p>
      )}

      {/* M4: the spin-a-sub-agent proposal (search + accept/reject). */}
      {proposal && (
        <div className="mt-3">
          <SubAgentProposal
            claimText={proposal.text}
            parentInvestigationId={investigationId}
            onAccept={() => setProposal(null)}
            onReject={() => setProposal(null)}
          />
        </div>
      )}

      {/* M3 X-ray view — paragraph ↔ blocks over the PERSISTED provenance.
          Toggled with the draft; no edit loss (the editor stays mounted in the
          draft view, the X-ray reads the persisted map). */}
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
      {draftContent != null && view === "draft" && (
        <div className="mt-3 rounded border border-rule p-3 dark:border-charcoal-1">
          <div ref={editorScopeRef}>
            <WriteEditor
              deliverableId={deliverableId}
              sectionId={section.section_id}
              initialContent={draftContent}
              investigationId={investigationId}
              // SPR-02: persist coarse prose_text on edit (mirrors the shape
              // CreationStudio uses), debounced, with an honest save indicator.
              onContentChange={handleContentChange}
              className="font-serif text-[15px] leading-relaxed text-ink dark:text-bright"
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
              className="mt-2 flex items-center gap-2 text-[10px]"
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
              {saveState.status === "saved" && (
                <span className="text-ink-mute dark:text-moonlight">Saved.</span>
              )}
              {saveState.status === "error" && (
                <span className="flex items-center gap-2 text-emperor">
                  <span>Couldn&rsquo;t save your last edit ({saveState.message}).</span>
                  <button
                    type="button"
                    onClick={() => void persistProse(latestProseRef.current)}
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

function CommissionInterviewButton({
  outlineBlockId,
  deliverableId,
}: {
  outlineBlockId: string;
  deliverableId: string;
}) {
  const [state, setState] = useState<
    | { phase: "idle" }
    | { phase: "working" }
    | { phase: "ready"; path: string }
    | { phase: "failed"; message: string }
  >({ phase: "idle" });

  if (state.phase === "ready") {
    return (
      <Link
        to={state.path}
        className="shrink-0 text-[11px] font-medium text-ocean underline"
        onClick={(event) => event.stopPropagation()}
      >
        Invite people →
      </Link>
    );
  }

  return (
    <div className="shrink-0 text-right">
      <button
        type="button"
        disabled={state.phase === "working"}
        onClick={(event) => {
          event.stopPropagation();
          setState({ phase: "working" });
          void commissionQuestionInterviews(outlineBlockId, deliverableId)
            .then((result) => setState({ phase: "ready", path: result.speak_path }))
            .catch((error: unknown) =>
              setState({
                phase: "failed",
                message: error instanceof Error ? error.message : String(error),
              }),
            );
        }}
        className="rounded border border-ocean/40 px-2 py-1 text-[11px] text-ocean disabled:opacity-50"
      >
        {state.phase === "working" ? "Opening…" : "Ask people"}
      </button>
      {state.phase === "failed" && (
        <p className="mt-1 max-w-40 text-[10px] text-emperor" role="alert">
          {state.message}
        </p>
      )}
    </div>
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
    .split(/\n\s*\n/)
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
