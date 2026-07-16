import { useState } from "react";

import type { NotebookBlockResponse, NotebookResponse } from "./types";

interface Props {
  notebook: NotebookResponse;
  onAppendBlock: (req: {
    block_type: string;
    content: unknown;
    ref_id?: string | null;
  }) => void;
  onDeleteBlock?: (blockId: string) => void;
  onMoveBlock?: (blockId: string, direction: "up" | "down") => void;
  onEditBlock?: (blockId: string, content: Record<string, unknown>) => void;
  /** true while a mutation is in flight; disables conflicting controls. */
  mutationPending?: boolean;
}

/**
 * NotebookCanvas — renders the ordered blocks in semantic block grammar.
 *
 * Each block type has a distinct visual treatment that identifies it by type
 * and reference ID without claiming the referenced entity is current/resolved.
 *
 * Cached text from references is labeled as cached display text — never called
 * "resolved" or "live". Null references render as tombstones; they never
 * disappear and never become empty prose blocks.
 *
 * Controls are focus-visible (not hover-only) and fully keyboard-accessible.
 * While a mutation is pending, conflicting controls are disabled.
 */
export default function NotebookCanvas({
  notebook,
  onAppendBlock,
  onDeleteBlock,
  onMoveBlock,
  onEditBlock,
  mutationPending,
}: Props) {
  const blockCount = notebook.blocks.length;
  return (
    <article className="max-w-3xl mx-auto px-8 py-10 space-y-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-serif text-ink dark:text-bright leading-tight">
          {notebook.title}
        </h1>
        <p className="text-xs font-mono text-shadow-1 dark:text-moonlight">
          {blockCount} {blockCount === 1 ? "block" : "blocks"} · updated{" "}
          {notebook.updated_at}
        </p>
      </header>

      <div className="space-y-4">
        {notebook.blocks.map((block, idx) => (
          <div key={block.block_id} className="rf-block relative">
            {onEditBlock && block.block_type === "prose" ? (
              <InlineProseEditor
                block={block}
                onEditBlock={onEditBlock}
                disabled={mutationPending}
              />
            ) : (
              <BlockView block={block} />
            )}
            {(onDeleteBlock || onMoveBlock) && (
              <BlockControls
                blockId={block.block_id}
                position={idx}
                isFirst={idx === 0}
                isLast={idx === blockCount - 1}
                onDeleteBlock={onDeleteBlock}
                onMoveBlock={onMoveBlock}
                disabled={mutationPending}
              />
            )}
          </div>
        ))}
      </div>

      <AppendBlockAffordance
        onAppendBlock={onAppendBlock}
        disabled={mutationPending}
      />
    </article>
  );
}

// ── Block controls (focus-visible, keyboard-accessible) ──────────

function BlockControls({
  blockId,
  position,
  isFirst,
  isLast,
  onDeleteBlock,
  onMoveBlock,
  disabled,
}: {
  blockId: string;
  position: number;
  isFirst: boolean;
  isLast: boolean;
  onDeleteBlock?: Props["onDeleteBlock"];
  onMoveBlock?: Props["onMoveBlock"];
  disabled?: boolean;
}) {
  return (
    <div className="rf-controls absolute -right-2 top-0 -translate-y-1/2 flex gap-1">
      {onMoveBlock && (
        <>
          <button
            type="button"
            disabled={isFirst || disabled}
            aria-label={`Move block ${position + 1} up`}
            onClick={() => onMoveBlock(blockId, "up")}
            className="rf-control w-6 h-6 rounded bg-ice-0 dark:bg-charcoal-2 border border-rule dark:border-charcoal-1 text-xs font-mono text-ink dark:text-bright hover:bg-ice-1 dark:hover:bg-charcoal-2 disabled:opacity-30 disabled:cursor-not-allowed"
          >
            ↑
          </button>
          <button
            type="button"
            disabled={isLast || disabled}
            aria-label={`Move block ${position + 1} down`}
            onClick={() => onMoveBlock(blockId, "down")}
            className="rf-control w-6 h-6 rounded bg-ice-0 dark:bg-charcoal-2 border border-rule dark:border-charcoal-1 text-xs font-mono text-ink dark:text-bright hover:bg-ice-1 dark:hover:bg-charcoal-2 disabled:opacity-30 disabled:cursor-not-allowed"
          >
            ↓
          </button>
        </>
      )}
      {onDeleteBlock && (
        <button
          type="button"
          disabled={disabled}
          aria-label={`Delete block ${position + 1}`}
          onClick={() => {
            if (
              window.confirm(
                `Delete block ${position + 1}? This deletes the row from the substrate.`,
              )
            ) {
              onDeleteBlock(blockId);
            }
          }}
          className="rf-control w-6 h-6 rounded bg-ice-0 dark:bg-charcoal-2 border border-rule dark:border-charcoal-1 text-xs font-mono text-emperor hover:bg-red-50 disabled:opacity-30 disabled:cursor-not-allowed"
        >
          ×
        </button>
      )}
    </div>
  );
}

// ── Inline prose editor (keyboard: double-click, ⌘Enter, Esc, Save) ──

function InlineProseEditor({
  block,
  onEditBlock,
  disabled,
}: {
  block: NotebookBlockResponse;
  onEditBlock: Props["onEditBlock"];
  disabled?: boolean;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(String(block.content_json.text ?? ""));

  if (!onEditBlock) return null;

  const cancel = () => {
    setDraft(String(block.content_json.text ?? ""));
    setEditing(false);
  };
  const save = () => {
    if (disabled) return;
    onEditBlock(block.block_id, { text: draft });
    setEditing(false);
  };

  if (editing) {
    return (
      <div className="mt-2 space-y-2">
        <textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Escape") cancel();
            if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) save();
          }}
          rows={Math.max(3, Math.min(12, draft.split("\n").length + 1))}
          aria-label="Edit prose block"
          className="w-full text-base font-serif text-ink dark:text-bright border border-rule dark:border-charcoal-1 rounded p-2 leading-relaxed bg-white dark:bg-charcoal-2"
        />
        <div className="flex gap-2 text-xs font-mono">
          <button
            type="button"
            disabled={disabled}
            onClick={save}
            className="px-2 py-1 rounded-md bg-ink text-white hover:bg-shadow-2 disabled:opacity-50"
          >
            Save
          </button>
          <button
            type="button"
            onClick={cancel}
            className="px-2 py-1 rounded-md border border-rule dark:border-charcoal-1 text-ink dark:text-bright hover:bg-ice-1 dark:hover:bg-charcoal-2"
          >
            Cancel
          </button>
        </div>
      </div>
    );
  }

  return (
    <div
      role="button"
      tabIndex={0}
      aria-label="Edit prose block"
      aria-disabled={disabled || undefined}
      onDoubleClick={() => { if (!disabled) setEditing(true); }}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          if (!disabled) setEditing(true);
        }
      }}
      className="cursor-text"
      title="Double-click or ⌘Enter to edit"
    >
      <BlockView block={block} />
    </div>
  );
}

// ── Semantic block grammar ───────────────────────────────────────
//
// Each block type has a distinct visual treatment. References carry
// their type label and ID. Cached text is labeled as cached; never
// called resolved or live. Null references render tombstones.

function BlockView({ block }: { block: NotebookBlockResponse }) {
  switch (block.block_type) {
    case "prose":
      return (
        <p className="text-base font-serif text-ink dark:text-bright leading-relaxed">
          {String(block.content_json.text ?? "")}
        </p>
      );
    case "claim_card":
      return (
        <ClaimReferenceBlock
          claimId={block.ref_id}
          text={String(block.content_json.text ?? "")}
        />
      );
    case "note":
      return (
        <NoteReferenceBlock
          noteId={block.ref_id}
          text={String(block.content_json.text ?? "")}
        />
      );
    case "region_embed":
      return (
        <RegionEmbedBlock
          regionId={block.ref_id}
          excerpt={String(block.content_json.excerpt ?? "")}
        />
      );
    case "question_card":
      return (
        <QuestionCardBlock
          questionId={block.ref_id}
          text={String(block.content_json.question_text ?? "")}
        />
      );
    case "master_md_section":
      return (
        <MasterMdSectionBlock
          sectionId={block.ref_id}
          heading={String(block.content_json.heading ?? "")}
        />
      );
    case "latex":
      return (
        <pre className="text-sm font-mono bg-ice-1 dark:bg-charcoal-2 border border-rule dark:border-charcoal-1 rounded-md p-3 text-ink dark:text-bright">
          {String(block.content_json.latex ?? "")}
        </pre>
      );
    case "image":
      return (
        <figure className="border border-rule dark:border-charcoal-1 rounded-md overflow-hidden">
          {block.content_json.url ? (
            <img
              src={String(block.content_json.url)}
              alt={String(block.content_json.alt ?? "")}
              className="max-w-full"
            />
          ) : null}
          <figcaption className="text-xs font-mono text-shadow-1 dark:text-moonlight px-2 py-1">
            image{block.ref_id ? `: ${block.ref_id}` : ""}
          </figcaption>
        </figure>
      );
    case "chat_exchange":
      return (
        <blockquote className="border-l-4 border-rule dark:border-charcoal-1 pl-4 py-1 text-sm text-ink dark:text-bright">
          <p className="text-xs font-mono text-shadow-1 dark:text-moonlight mb-1">
            chat exchange
          </p>
          {String(block.content_json.exchange ?? "")}
        </blockquote>
      );
    case "cross_doc_link":
      return (
        <CrossDocLinkBlock
          fromDoc={String(block.content_json.from_document_id ?? "")}
          toDoc={String(block.content_json.to_document_id ?? "")}
          questionId={String(block.content_json.question_id ?? "")}
        />
      );
    default:
      return (
        <div className="text-xs font-mono text-shadow-1 dark:text-moonlight italic">
          [unknown block_type: {block.block_type}]
        </div>
      );
  }
}

/** Claim reference — cached text labeled as cached; tombstone when null. */
function ClaimReferenceBlock({
  claimId,
  text,
}: {
  claimId: string | null;
  text: string;
}) {
  if (!claimId) {
    return (
      <div className="rf-tombstone rf-claim-tombstone text-xs italic text-shadow-1 dark:text-moonlight border-l-2 border-gray-300 pl-3 py-1">
        [tombstone: claim deleted; prior text: {text}]
      </div>
    );
  }
  return (
    <div className="rf-claim border-l-2 border-emerald-300 pl-3 py-1">
      <p className="text-sm text-ink dark:text-bright font-serif">
        {text || `(claim ${claimId})`}
      </p>
      <p className="mt-1 text-xs font-mono text-shadow-1 dark:text-moonlight">
        claim: {claimId} · cached text
      </p>
    </div>
  );
}

/** Note reference — cached text labeled as cached; tombstone when null. */
function NoteReferenceBlock({
  noteId,
  text,
}: {
  noteId: string | null;
  text: string;
}) {
  if (!noteId) {
    return (
      <div className="rf-tombstone rf-note-tombstone text-xs italic text-shadow-1 dark:text-moonlight border-l-2 border-gray-300 pl-3 py-1">
        [tombstone: note deleted; prior text: {text}]
      </div>
    );
  }
  return (
    <div className="rf-note border-l-2 border-amber-300 pl-3 py-1">
      <p className="text-sm text-ink dark:text-bright font-serif">
        {text || `(note ${noteId})`}
      </p>
      <p className="mt-1 text-xs font-mono text-shadow-1 dark:text-moonlight">
        note: {noteId} · cached text
      </p>
    </div>
  );
}

/** Region embed — cached excerpt labeled as cached. */
function RegionEmbedBlock({
  regionId,
  excerpt,
}: {
  regionId: string | null;
  excerpt: string;
}) {
  return (
    <div className="rf-region rounded-md bg-ice-1 dark:bg-charcoal-2 border border-rule dark:border-charcoal-1 px-3 py-2">
      <p className="text-xs font-mono text-shadow-1 dark:text-moonlight mb-1">
        region: {regionId ?? "(no ref)"} · cached excerpt
      </p>
      <p className="text-sm text-ink dark:text-bright font-serif italic">
        {excerpt || "(no excerpt cached)"}
      </p>
    </div>
  );
}

/** Question card. */
function QuestionCardBlock({
  questionId,
  text,
}: {
  questionId: string | null;
  text: string;
}) {
  if (!questionId) {
    return (
      <div className="rf-tombstone text-xs italic text-shadow-1 dark:text-moonlight">
        [tombstone: question reference unavailable; cached text: {text}]
      </div>
    );
  }
  return (
    <div className="rf-question border-l-2 border-blue-300 pl-3 py-1">
      <p className="text-sm text-ink dark:text-bright font-serif">
        {text || `(question ${questionId})`}
      </p>
      <p className="mt-1 text-xs font-mono text-shadow-1 dark:text-moonlight">
        question: {questionId} · cached text
      </p>
    </div>
  );
}

/** Master.md section link. */
function MasterMdSectionBlock({
  sectionId,
  heading,
}: {
  sectionId: string | null;
  heading: string;
}) {
  return (
    <div className="rf-master-section border border-dashed border-rule dark:border-charcoal-1 rounded-md px-3 py-2">
      <p className="text-xs font-mono text-shadow-1 dark:text-moonlight mb-1">
        master.md section: {sectionId ?? "(no ref)"}
      </p>
      <h3 className="text-base font-serif text-ink dark:text-bright">
        {heading || "(section heading)"}
      </h3>
    </div>
  );
}

/** Cross-document link. */
function CrossDocLinkBlock({
  fromDoc,
  toDoc,
  questionId,
}: {
  fromDoc: string;
  toDoc: string;
  questionId: string;
}) {
  return (
    <div className="rf-cross-doc rounded-md bg-ice-1 dark:bg-charcoal-2 border border-rule dark:border-charcoal-1 px-3 py-2">
      <p className="text-xs font-mono text-shadow-1 dark:text-moonlight">
        {fromDoc} → {toDoc} · question: {questionId}
      </p>
    </div>
  );
}

// ── Append block affordance ──────────────────────────────────────

function AppendBlockAffordance({
  onAppendBlock,
  disabled,
}: {
  onAppendBlock: Props["onAppendBlock"];
  disabled?: boolean;
}) {
  const [pickerOpen, setPickerOpen] = useState(false);

  const appendProse = () => {
    const text = prompt("Prose text:");
    if (text?.trim()) onAppendBlock({ block_type: "prose", content: { text: text.trim() } });
    setPickerOpen(false);
  };
  const appendQuestion = () => {
    const text = prompt("Question text (will surface as a parked question):");
    if (text?.trim())
      onAppendBlock({
        block_type: "question_card",
        content: { question_text: text.trim() },
      });
    setPickerOpen(false);
  };
  const appendLatex = () => {
    const text = prompt("LaTeX source:");
    if (text?.trim())
      onAppendBlock({ block_type: "latex", content: { latex: text.trim() } });
    setPickerOpen(false);
  };
  const appendClaimReference = () => {
    const claimId = prompt("Claim ID to embed:");
    if (!claimId?.trim()) {
      setPickerOpen(false);
      return;
    }
    const text = prompt("Display text for the claim:") ?? "";
    onAppendBlock({
      block_type: "claim_card",
      content: { text: text.trim() },
      ref_id: claimId.trim(),
    });
    setPickerOpen(false);
  };
  const appendRegionRef = () => {
    const regionId = prompt("Region ID to embed:");
    if (!regionId?.trim()) {
      setPickerOpen(false);
      return;
    }
    const excerpt = prompt("Cached excerpt text (optional):") ?? "";
    onAppendBlock({
      block_type: "region_embed",
      content: { excerpt: excerpt.trim() },
      ref_id: regionId.trim(),
    });
    setPickerOpen(false);
  };

  return (
    <div className="space-y-2">
      <button
        type="button"
        disabled={disabled}
        onClick={() => setPickerOpen((v) => !v)}
        className="text-xs font-mono text-shadow-1 dark:text-moonlight hover:text-ink dark:hover:text-bright underline-offset-2 hover:underline transition-colors disabled:opacity-50"
      >
        {pickerOpen ? "× close block picker" : "+ add block"}
      </button>
      {pickerOpen && (
        <div
          className="border border-rule dark:border-charcoal-1 rounded-md p-3 grid grid-cols-2 gap-2"
          role="group"
          aria-label="Block type picker"
        >
          <PickerButton label="Prose" onClick={appendProse} />
          <PickerButton label="Question card" onClick={appendQuestion} />
          <PickerButton label="LaTeX" onClick={appendLatex} />
          <PickerButton label="Claim reference" onClick={appendClaimReference} />
          <PickerButton label="Region embed" onClick={appendRegionRef} />
        </div>
      )}
    </div>
  );
}

function PickerButton({
  label,
  onClick,
}: {
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="px-3 py-1.5 rounded-md border border-rule dark:border-charcoal-1 bg-ice-0 dark:bg-charcoal-2 text-xs font-mono text-ink dark:text-bright hover:bg-ice-1 dark:hover:bg-charcoal-2 transition-colors text-left"
    >
      {label}
    </button>
  );
}
