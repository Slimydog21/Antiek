import { useState } from "react";

import LemonButton from "../../components/lemon/LemonButton";
import { LemonModal } from "../../components/lemon/LemonModal";

import type { NotebookBlockResponse, NotebookResponse } from "./types";

interface Props {
  notebook: NotebookResponse;
  onAppendBlock: (req: {
    block_type: string;
    content: unknown;
    ref_id?: string | null;
  }) => Promise<void>;
  onDeleteBlock?: (blockId: string) => Promise<void>;
  onMoveBlock?: (blockId: string, direction: "up" | "down") => Promise<void>;
  onEditBlock?: (blockId: string, content: Record<string, unknown>) => Promise<void>;
}

/**
 * NotebookCanvas — renders the ordered blocks in serif typography
 * per master-spec §5.5 voice-and-style discipline.
 *
 * Sprint 18-19 scaffold: read-only-ish rendering + a thin
 * append-prose affordance. Full TipTap-based block editor lands
 * after the spike that decides Lemon UI vs custom (per Sprint 17
 * Lemon UI evaluation gate). Drag-drop block reordering lands
 * Sprint 19-20 alongside command palette + ubiquitous AI per
 * §14.1.
 */
export default function NotebookCanvas({
  notebook,
  onAppendBlock,
  onDeleteBlock,
  onMoveBlock,
  onEditBlock,
}: Props) {
  const blockCount = notebook.blocks.length;
  return (
    <article className="max-w-3xl mx-auto px-8 py-10 space-y-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-serif text-ink dark:text-bright leading-tight">
          {notebook.title}
        </h1>
        <p className="text-xs font-mono text-shadow-1 dark:text-moonlight">
          {blockCount} {blockCount === 1 ? "block" : "blocks"} ·{" "}
          updated {notebook.updated_at}
        </p>
      </header>

      <div className="space-y-4">
        {notebook.blocks.map((block, idx) => (
          <div key={block.block_id} className="group relative">
            <BlockOrEditor block={block} onEditBlock={onEditBlock} />
            {(onDeleteBlock || onMoveBlock) && (
              <BlockControls
                blockId={block.block_id}
                position={idx}
                isFirst={idx === 0}
                isLast={idx === blockCount - 1}
                onDeleteBlock={onDeleteBlock}
                onMoveBlock={onMoveBlock}
              />
            )}
          </div>
        ))}
      </div>

      <AppendProseAffordance onAppendBlock={onAppendBlock} />
    </article>
  );
}

function BlockOrEditor({
  block,
  onEditBlock,
}: {
  block: NotebookBlockResponse;
  onEditBlock: Props["onEditBlock"];
}) {
  const [editing, setEditing] = useState<boolean>(false);
  const [draft, setDraft] = useState<string>(
    String(block.content_json.text ?? ""),
  );

  if (!onEditBlock || block.block_type !== "prose") {
    return <BlockView block={block} />;
  }
  if (editing) {
    return (
      <div className="space-y-2">
        <textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          rows={Math.max(3, Math.min(12, draft.split("\n").length + 1))}
          className="w-full text-base font-serif text-ink dark:text-bright border border-rule dark:border-charcoal-1 rounded p-2 leading-relaxed"
        />
        <div className="flex gap-2 text-xs font-mono">
          <button
            type="button"
            onClick={async () => {
              await onEditBlock(block.block_id, { text: draft });
              setEditing(false);
            }}
            className="px-2 py-1 rounded-md bg-ink text-white hover:bg-shadow-2"
          >
            Save
          </button>
          <button
            type="button"
            onClick={() => {
              setDraft(String(block.content_json.text ?? ""));
              setEditing(false);
            }}
            className="px-2 py-1 rounded-md border border-rule dark:border-charcoal-1 text-ink dark:text-bright hover:bg-ice-1 dark:bg-charcoal-2"
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
      onDoubleClick={() => setEditing(true)}
      onKeyDown={(e) => {
        if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
          setEditing(true);
        }
      }}
      className="cursor-text"
      title="Double-click or ⌘Enter to edit"
    >
      <BlockView block={block} />
    </div>
  );
}

function BlockControls({
  blockId,
  position,
  isFirst,
  isLast,
  onDeleteBlock,
  onMoveBlock,
}: {
  blockId: string;
  position: number;
  isFirst: boolean;
  isLast: boolean;
  onDeleteBlock: Props["onDeleteBlock"];
  onMoveBlock: Props["onMoveBlock"];
}) {
  // Destructive delete confirms via the house modal (LemonModal), never
  // window.confirm — same pattern as CommandPalette's layout-wipe confirm.
  const [confirmingDelete, setConfirmingDelete] = useState<boolean>(false);
  return (
    <div className="absolute -right-2 top-0 -translate-y-1/2 opacity-0 group-hover:opacity-100 transition-opacity flex gap-1">
      {onMoveBlock && (
        <>
          <button
            type="button"
            disabled={isFirst}
            title="Move up"
            onClick={() => void onMoveBlock(blockId, "up")}
            className="w-6 h-6 rounded bg-ice-0 dark:bg-charcoal-2 border border-rule dark:border-charcoal-1 text-xs font-mono text-ink dark:text-bright hover:bg-ice-1 dark:bg-charcoal-2 disabled:opacity-30 disabled:cursor-not-allowed"
          >
            ↑
          </button>
          <button
            type="button"
            disabled={isLast}
            title="Move down"
            onClick={() => void onMoveBlock(blockId, "down")}
            className="w-6 h-6 rounded bg-ice-0 dark:bg-charcoal-2 border border-rule dark:border-charcoal-1 text-xs font-mono text-ink dark:text-bright hover:bg-ice-1 dark:bg-charcoal-2 disabled:opacity-30 disabled:cursor-not-allowed"
          >
            ↓
          </button>
        </>
      )}
      {onDeleteBlock && (
        <>
          <button
            type="button"
            title="Delete block"
            onClick={() => setConfirmingDelete(true)}
            className="w-6 h-6 rounded bg-ice-0 dark:bg-charcoal-2 border border-rule dark:border-charcoal-1 text-xs font-mono text-emperor"
          >
            ×
          </button>
          <LemonModal
            open={confirmingDelete}
            onClose={() => setConfirmingDelete(false)}
            title={`Delete block ${position + 1}?`}
            size="sm"
            forceUserAction
            footer={
              <div className="flex items-center justify-end gap-2">
                <LemonButton
                  variant="secondary"
                  onClick={() => setConfirmingDelete(false)}
                >
                  Cancel
                </LemonButton>
                <LemonButton
                  variant="danger"
                  onClick={() => {
                    setConfirmingDelete(false);
                    void onDeleteBlock(blockId);
                  }}
                >
                  Delete block
                </LemonButton>
              </div>
            }
          >
            <p className="text-sm text-ink dark:text-bright">
              This deletes the row from the substrate.
            </p>
          </LemonModal>
        </>
      )}
    </div>
  );
}

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
        </figure>
      );
    case "chat_exchange":
      return (
        <blockquote className="border-l-4 border-rule dark:border-charcoal-1 pl-4 py-1 text-sm text-ink dark:text-bright">
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

function ClaimReferenceBlock({ claimId, text }: { claimId: string | null; text: string }) {
  if (!claimId) {
    return (
      <div className="text-xs italic text-shadow-1 dark:text-moonlight">
        [tombstone: claim deleted; prior text: {text}]
      </div>
    );
  }
  return (
    <div className="border-l-2 border-sun-deep pl-3 py-1">
      <p className="text-sm text-ink dark:text-bright font-serif">{text || `(claim ${claimId})`}</p>
      <p className="mt-1 text-xs font-mono text-shadow-1 dark:text-moonlight">claim: {claimId}</p>
    </div>
  );
}

function NoteReferenceBlock({ noteId, text }: { noteId: string | null; text: string }) {
  if (!noteId) {
    return (
      <div className="text-xs italic text-shadow-1 dark:text-moonlight">
        [tombstone: note deleted; prior text: {text}]
      </div>
    );
  }
  return (
    <div className="border-l-2 border-sun pl-3 py-1">
      <p className="text-sm text-ink dark:text-bright font-serif">{text || `(note ${noteId})`}</p>
      <p className="mt-1 text-xs font-mono text-shadow-1 dark:text-moonlight">note: {noteId}</p>
    </div>
  );
}

function RegionEmbedBlock({ regionId, excerpt }: { regionId: string | null; excerpt: string }) {
  return (
    <div className="rounded-md bg-ice-1 dark:bg-charcoal-2 border border-rule dark:border-charcoal-1 px-3 py-2">
      <p className="text-xs font-mono text-shadow-1 dark:text-moonlight mb-1">
        region: {regionId ?? "(no ref)"}
      </p>
      <p className="text-sm text-ink dark:text-bright font-serif italic">
        {excerpt || "(no excerpt cached)"}
      </p>
    </div>
  );
}

function QuestionCardBlock({ questionId, text }: { questionId: string | null; text: string }) {
  return (
    <div className="border-l-2 border-aurora pl-3 py-1">
      <p className="text-sm text-ink dark:text-bright font-serif">{text || `(question ${questionId})`}</p>
      <p className="mt-1 text-xs font-mono text-shadow-1 dark:text-moonlight">open: {questionId}</p>
    </div>
  );
}

function MasterMdSectionBlock({ sectionId, heading }: { sectionId: string | null; heading: string }) {
  return (
    <div className="border border-dashed border-rule dark:border-charcoal-1 rounded-md px-3 py-2">
      <p className="text-xs font-mono text-shadow-1 dark:text-moonlight mb-1">
        master.md section: {sectionId ?? "(no ref)"}
      </p>
      <h3 className="text-base font-serif text-ink dark:text-bright">
        {heading || "(section heading)"}
      </h3>
    </div>
  );
}

function CrossDocLinkBlock({
  fromDoc,
  toDoc,
  questionId,
}: { fromDoc: string; toDoc: string; questionId: string }) {
  return (
    <div className="rounded-md bg-ice-1 dark:bg-charcoal-2 border border-rule dark:border-charcoal-1 px-3 py-2">
      <p className="text-xs font-mono text-shadow-1 dark:text-moonlight">
        {fromDoc} → {toDoc} · question: {questionId}
      </p>
    </div>
  );
}

/** The block kinds the append picker can create via its modal form. */
type AppendKind = "prose" | "question_card" | "latex" | "claim_card" | "region_embed";

/** Per-kind form shape: one primary field (always required) + an optional
 *  secondary field for the two embed kinds. Replacing the old prompt() pair
 *  per kind with one modal keeps the operator in the document. */
const APPEND_FORMS: Record<
  AppendKind,
  {
    title: string;
    primaryLabel: string;
    primaryMultiline?: boolean;
    secondaryLabel?: string;
    submitLabel: string;
    build: (primary: string, secondary: string) => {
      block_type: string;
      content: unknown;
      ref_id?: string | null;
    };
  }
> = {
  prose: {
    title: "Add prose",
    primaryLabel: "Prose text",
    primaryMultiline: true,
    submitLabel: "Add prose",
    build: (text) => ({ block_type: "prose", content: { text } }),
  },
  question_card: {
    title: "Add question card",
    primaryLabel: "Question text (will surface as a parked question)",
    primaryMultiline: true,
    submitLabel: "Add question",
    build: (text) => ({
      block_type: "question_card",
      content: { question_text: text },
    }),
  },
  latex: {
    title: "Add LaTeX",
    primaryLabel: "LaTeX source",
    primaryMultiline: true,
    submitLabel: "Add LaTeX",
    build: (text) => ({ block_type: "latex", content: { latex: text } }),
  },
  claim_card: {
    title: "Embed claim reference",
    primaryLabel: "Claim ID to embed",
    secondaryLabel: "Display text for the claim (optional)",
    submitLabel: "Embed claim",
    build: (claimId, text) => ({
      block_type: "claim_card",
      content: { text },
      ref_id: claimId,
    }),
  },
  region_embed: {
    title: "Embed region",
    primaryLabel: "Region ID to embed",
    secondaryLabel: "Cached excerpt text (optional)",
    submitLabel: "Embed region",
    build: (regionId, excerpt) => ({
      block_type: "region_embed",
      content: { excerpt },
      ref_id: regionId,
    }),
  },
};

function AppendProseAffordance({
  onAppendBlock,
}: { onAppendBlock: Props["onAppendBlock"] }) {
  const [pickerOpen, setPickerOpen] = useState<boolean>(false);
  const [dialog, setDialog] = useState<AppendKind | null>(null);
  const [primary, setPrimary] = useState<string>("");
  const [secondary, setSecondary] = useState<string>("");

  const openDialog = (kind: AppendKind) => {
    setPrimary("");
    setSecondary("");
    setDialog(kind);
    setPickerOpen(false);
  };

  const submit = () => {
    if (!dialog) return;
    const form = APPEND_FORMS[dialog];
    const value = primary.trim();
    if (!value) return; // primary field is required for every kind
    void onAppendBlock(form.build(value, secondary.trim()));
    setDialog(null);
  };

  const form = dialog ? APPEND_FORMS[dialog] : null;

  return (
    <div className="space-y-2">
      <button
        type="button"
        onClick={() => setPickerOpen((v) => !v)}
        className="text-xs font-mono text-shadow-1 dark:text-moonlight hover:text-ink dark:text-bright underline-offset-2 hover:underline transition-colors"
      >
        {pickerOpen ? "× close block picker" : "+ add block"}
      </button>
      {pickerOpen && (
        <div className="border border-rule dark:border-charcoal-1 rounded-md p-3 grid grid-cols-2 gap-2">
          <PickerButton label="Prose" onClick={() => openDialog("prose")} />
          <PickerButton label="Question card" onClick={() => openDialog("question_card")} />
          <PickerButton label="LaTeX" onClick={() => openDialog("latex")} />
          <PickerButton label="Claim reference" onClick={() => openDialog("claim_card")} />
          <PickerButton label="Region embed" onClick={() => openDialog("region_embed")} />
        </div>
      )}

      {/* Append dialog — the house modal, not window.prompt. Submit on
          Enter (single-line fields) or the button; Esc/outside-click cancels. */}
      <LemonModal
        open={dialog !== null}
        onClose={() => setDialog(null)}
        title={form?.title ?? "Add block"}
        size="sm"
        footer={
          <div className="flex items-center justify-end gap-2">
            <LemonButton variant="secondary" onClick={() => setDialog(null)}>
              Cancel
            </LemonButton>
            <LemonButton
              variant="primary"
              disabledReason={!primary.trim() ? `Fill in ${form?.primaryLabel ?? "the first field"} first` : null}
              onClick={submit}
            >
              {form?.submitLabel ?? "Add"}
            </LemonButton>
          </div>
        }
      >
        {form && (
          <form
            className="space-y-3"
            onSubmit={(e) => {
              e.preventDefault();
              submit();
            }}
          >
            <label className="block space-y-1">
              <span className="text-xs font-mono text-shadow-1 dark:text-moonlight">
                {form.primaryLabel}
              </span>
              {form.primaryMultiline ? (
                <textarea
                  value={primary}
                  onChange={(e) => setPrimary(e.target.value)}
                  rows={4}
                  className="w-full text-base font-serif text-ink dark:text-bright border border-rule dark:border-charcoal-1 rounded p-2 leading-relaxed"
                />
              ) : (
                <input
                  type="text"
                  value={primary}
                  onChange={(e) => setPrimary(e.target.value)}
                  className="w-full text-sm font-mono text-ink dark:text-bright border border-rule dark:border-charcoal-1 rounded p-2"
                />
              )}
            </label>
            {form.secondaryLabel && (
              <label className="block space-y-1">
                <span className="text-xs font-mono text-shadow-1 dark:text-moonlight">
                  {form.secondaryLabel}
                </span>
                <input
                  type="text"
                  value={secondary}
                  onChange={(e) => setSecondary(e.target.value)}
                  className="w-full text-sm font-mono text-ink dark:text-bright border border-rule dark:border-charcoal-1 rounded p-2"
                />
              </label>
            )}
          </form>
        )}
      </LemonModal>
    </div>
  );
}

function PickerButton({
  label,
  onClick,
}: { label: string; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="px-3 py-1.5 rounded-md border border-rule dark:border-charcoal-1 bg-ice-0 dark:bg-charcoal-2 text-xs font-mono text-ink dark:text-bright hover:bg-ice-1 dark:bg-charcoal-2 transition-colors text-left"
    >
      {label}
    </button>
  );
}
