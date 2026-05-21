import { useState } from "react";

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
        <h1 className="text-2xl font-serif text-stone-900 leading-tight">
          {notebook.title}
        </h1>
        <p className="text-xs font-mono text-stone-500">
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
          className="w-full text-base font-serif text-stone-900 border border-stone-200 rounded p-2 leading-relaxed"
        />
        <div className="flex gap-2 text-xs font-mono">
          <button
            type="button"
            onClick={async () => {
              await onEditBlock(block.block_id, { text: draft });
              setEditing(false);
            }}
            className="px-2 py-1 rounded-md bg-stone-900 text-white hover:bg-stone-800"
          >
            Save
          </button>
          <button
            type="button"
            onClick={() => {
              setDraft(String(block.content_json.text ?? ""));
              setEditing(false);
            }}
            className="px-2 py-1 rounded-md border border-stone-200 text-stone-700 hover:bg-stone-50"
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
  return (
    <div className="absolute -right-2 top-0 -translate-y-1/2 opacity-0 group-hover:opacity-100 transition-opacity flex gap-1">
      {onMoveBlock && (
        <>
          <button
            type="button"
            disabled={isFirst}
            title="Move up"
            onClick={() => void onMoveBlock(blockId, "up")}
            className="w-6 h-6 rounded bg-white border border-stone-200 text-xs font-mono text-stone-700 hover:bg-stone-50 disabled:opacity-30 disabled:cursor-not-allowed"
          >
            ↑
          </button>
          <button
            type="button"
            disabled={isLast}
            title="Move down"
            onClick={() => void onMoveBlock(blockId, "down")}
            className="w-6 h-6 rounded bg-white border border-stone-200 text-xs font-mono text-stone-700 hover:bg-stone-50 disabled:opacity-30 disabled:cursor-not-allowed"
          >
            ↓
          </button>
        </>
      )}
      {onDeleteBlock && (
        <button
          type="button"
          title="Delete block"
          onClick={() => {
            if (
              window.confirm(
                `Delete block ${position + 1}? This deletes the row from the substrate.`,
              )
            ) {
              void onDeleteBlock(blockId);
            }
          }}
          className="w-6 h-6 rounded bg-white border border-stone-200 text-xs font-mono text-red-700 hover:bg-red-50"
        >
          ×
        </button>
      )}
    </div>
  );
}

function BlockView({ block }: { block: NotebookBlockResponse }) {
  switch (block.block_type) {
    case "prose":
      return (
        <p className="text-base font-serif text-stone-900 leading-relaxed">
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
        <pre className="text-sm font-mono bg-stone-50 border border-stone-200 rounded-md p-3 text-stone-700">
          {String(block.content_json.latex ?? "")}
        </pre>
      );
    case "image":
      return (
        <figure className="border border-stone-200 rounded-md overflow-hidden">
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
        <blockquote className="border-l-4 border-stone-200 pl-4 py-1 text-sm text-stone-700">
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
        <div className="text-xs font-mono text-stone-500 italic">
          [unknown block_type: {block.block_type}]
        </div>
      );
  }
}

function ClaimReferenceBlock({ claimId, text }: { claimId: string | null; text: string }) {
  if (!claimId) {
    return (
      <div className="text-xs italic text-stone-500">
        [tombstone: claim deleted; prior text: {text}]
      </div>
    );
  }
  return (
    <div className="border-l-2 border-emerald-300 pl-3 py-1">
      <p className="text-sm text-stone-900 font-serif">{text || `(claim ${claimId})`}</p>
      <p className="mt-1 text-xs font-mono text-stone-500">claim: {claimId}</p>
    </div>
  );
}

function NoteReferenceBlock({ noteId, text }: { noteId: string | null; text: string }) {
  if (!noteId) {
    return (
      <div className="text-xs italic text-stone-500">
        [tombstone: note deleted; prior text: {text}]
      </div>
    );
  }
  return (
    <div className="border-l-2 border-amber-300 pl-3 py-1">
      <p className="text-sm text-stone-900 font-serif">{text || `(note ${noteId})`}</p>
      <p className="mt-1 text-xs font-mono text-stone-500">note: {noteId}</p>
    </div>
  );
}

function RegionEmbedBlock({ regionId, excerpt }: { regionId: string | null; excerpt: string }) {
  return (
    <div className="rounded-md bg-stone-50 border border-stone-200 px-3 py-2">
      <p className="text-xs font-mono text-stone-500 mb-1">
        region: {regionId ?? "(no ref)"}
      </p>
      <p className="text-sm text-stone-800 font-serif italic">
        {excerpt || "(no excerpt cached)"}
      </p>
    </div>
  );
}

function QuestionCardBlock({ questionId, text }: { questionId: string | null; text: string }) {
  return (
    <div className="border-l-2 border-blue-300 pl-3 py-1">
      <p className="text-sm text-stone-900 font-serif">{text || `(question ${questionId})`}</p>
      <p className="mt-1 text-xs font-mono text-stone-500">open: {questionId}</p>
    </div>
  );
}

function MasterMdSectionBlock({ sectionId, heading }: { sectionId: string | null; heading: string }) {
  return (
    <div className="border border-dashed border-stone-300 rounded-md px-3 py-2">
      <p className="text-xs font-mono text-stone-500 mb-1">
        master.md section: {sectionId ?? "(no ref)"}
      </p>
      <h3 className="text-base font-serif text-stone-900">
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
    <div className="rounded-md bg-stone-50 border border-stone-200 px-3 py-2">
      <p className="text-xs font-mono text-stone-500">
        {fromDoc} → {toDoc} · question: {questionId}
      </p>
    </div>
  );
}

function AppendProseAffordance({
  onAppendBlock,
}: { onAppendBlock: Props["onAppendBlock"] }) {
  const [pickerOpen, setPickerOpen] = useState<boolean>(false);

  const appendProse = () => {
    const text = prompt("Prose text:");
    if (text && text.trim()) {
      void onAppendBlock({
        block_type: "prose",
        content: { text: text.trim() },
      });
    }
    setPickerOpen(false);
  };
  const appendQuestion = () => {
    const text = prompt("Question text (will surface as a parked question):");
    if (text && text.trim()) {
      void onAppendBlock({
        block_type: "question_card",
        content: { question_text: text.trim() },
      });
    }
    setPickerOpen(false);
  };
  const appendLatex = () => {
    const text = prompt("LaTeX source:");
    if (text && text.trim()) {
      void onAppendBlock({
        block_type: "latex",
        content: { latex: text.trim() },
      });
    }
    setPickerOpen(false);
  };
  const appendClaimReference = () => {
    const claimId = prompt("Claim ID to embed:");
    if (!claimId || !claimId.trim()) {
      setPickerOpen(false);
      return;
    }
    const text = prompt("Display text for the claim:") ?? "";
    void onAppendBlock({
      block_type: "claim_card",
      content: { text: text.trim() },
      ref_id: claimId.trim(),
    });
    setPickerOpen(false);
  };
  const appendRegionRef = () => {
    const regionId = prompt("Region ID to embed:");
    if (!regionId || !regionId.trim()) {
      setPickerOpen(false);
      return;
    }
    const excerpt = prompt("Cached excerpt text (optional):") ?? "";
    void onAppendBlock({
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
        onClick={() => setPickerOpen((v) => !v)}
        className="text-xs font-mono text-stone-500 hover:text-stone-900 underline-offset-2 hover:underline transition-colors"
      >
        {pickerOpen ? "× close block picker" : "+ add block"}
      </button>
      {pickerOpen && (
        <div className="border border-stone-200 rounded-md p-3 grid grid-cols-2 gap-2">
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
}: { label: string; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="px-3 py-1.5 rounded-md border border-stone-200 bg-white text-xs font-mono text-stone-700 hover:bg-stone-50 transition-colors text-left"
    >
      {label}
    </button>
  );
}
