/**
 * DRW SPR-09 M2 — the cascade plan editor (the glass box).
 *
 * Renders the SPR-05 sub-question tree and supports add / remove / re-word
 * per node (the edit ops the backend exposes). Every edit round-trips
 * through the SPR-05 contract and re-opens the approval gate: Approve enables
 * Launch; editing after approval disables Launch until re-approval. Nothing
 * launches before the operator approves — that human-in-the-loop step is the
 * entire differentiator, so it is the loud, central control here.
 */

import { useState } from "react";

import thinkingArt from "../../brand/werner/poses/session/werner_thinking_session_v1.png";
import livingTvArt from "../../brand/werner/poses/session/werner_living_tv_session_v1.webp";
import LemonButton from "../../components/lemon/LemonButton";
import type { PlanNode, PlanTree } from "../../api/research";

export interface PlanEditorProps {
  tree: PlanTree;
  launchable: boolean;
  busy?: boolean;
  onEdit: (edit: {
    op: "add_child" | "remove" | "reword";
    target_local_id: string;
    question?: string;
  }) => void;
  onApprove: () => void;
  onLaunch: () => void;
}

export default function PlanEditor({ tree, launchable, busy, onEdit, onApprove, onLaunch }: PlanEditorProps) {
  const leafCount = countLeaves(tree.root);
  return (
    <div className="flex h-full flex-col gap-3">
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-2">
          <img
            src={thinkingArt}
            alt=""
            aria-hidden="true"
            data-testid="plan-editor-werner-brand"
            className="mt-0.5 h-8 w-8 shrink-0 object-contain"
          />
          <div>
            <h2 className="text-sm font-semibold text-ink dark:text-bright">
              Cascade plan
            </h2>
            <p className="text-[11px] text-shadow-1 dark:text-moonlight">
              {leafCount} focused {leafCount === 1 ? "research" : "researches"} ·{" "}
              {tree.approval.state === "approved"
                ? "approved"
                : "draft (edit, then approve)"}
            </p>
          </div>
        </div>
        <div className="flex shrink-0 gap-2">
          <LemonButton size="sm" variant="secondary" disabled={busy} onClick={onApprove}>
            {tree.approval.state === "approved" ? "Re-approve" : "Approve"}
          </LemonButton>
          <LemonButton
            size="sm"
            variant="primary"
            disabled={busy || !launchable}
            onClick={onLaunch}
            title={launchable ? `Launch ${leafCount} researches` : "Approve the plan to launch"}
          >
            Launch {leafCount}
          </LemonButton>
        </div>
      </div>
      <img
        src={livingTvArt}
        alt=""
        aria-hidden="true"
        data-testid="plan-editor-living-tv-art"
        className="h-14 w-full max-w-lg rounded-md object-cover object-center"
        loading="lazy"
        decoding="async"
      />

      <div className="flex-1 overflow-auto rounded-md border-2 border-sun bg-ice-0 p-2 dark:bg-charcoal-2">
        <PlanNodeRow node={tree.root} depth={0} isRoot busy={busy} onEdit={onEdit} />
      </div>
    </div>
  );
}

function PlanNodeRow({
  node, depth, isRoot, busy, onEdit,
}: {
  node: PlanNode;
  depth: number;
  isRoot?: boolean;
  busy?: boolean;
  onEdit: PlanEditorProps["onEdit"];
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(node.question);

  return (
    <div style={{ paddingLeft: depth * 14 }} className="py-0.5">
      <div className="group flex items-start gap-2">
        <span className="mt-1 text-shadow-1 dark:text-moonlight" aria-hidden>
          {isRoot ? "◆" : node.children.length ? "▸" : "•"}
        </span>
        {editing ? (
          <form
            className="flex flex-1 gap-1.5"
            onSubmit={(e) => {
              e.preventDefault();
              const q = draft.trim();
              if (q && q !== node.question) onEdit({ op: "reword", target_local_id: node.local_id, question: q });
              setEditing(false);
            }}
          >
            <input
              className="min-w-0 flex-1 rounded border border-ice-4 bg-ice-1 px-2 py-1 text-sm text-ink dark:border-slate-2 dark:bg-charcoal-1 dark:text-bright"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              aria-label="edit sub-question"
              autoFocus
            />
            <LemonButton size="sm" variant="primary" type="submit">Save</LemonButton>
          </form>
        ) : (
          <>
            <p className={`flex-1 text-sm ${isRoot ? "font-semibold" : ""} text-ink dark:text-bright`}>
              {node.question}
            </p>
            <div className="flex gap-1 opacity-0 transition-opacity group-hover:opacity-100">
              <button
                className="text-[11px] text-shadow-1 hover:text-aurora dark:text-moonlight"
                disabled={busy}
                onClick={() => { setDraft(node.question); setEditing(true); }}
              >
                edit
              </button>
              <button
                className="text-[11px] text-shadow-1 hover:text-aurora dark:text-moonlight"
                disabled={busy}
                onClick={() => onEdit({ op: "add_child", target_local_id: node.local_id, question: "New sub-question" })}
              >
                + sub
              </button>
              {!isRoot && (
                <button
                  className="text-[11px] text-shadow-1 hover:text-emperor dark:text-moonlight"
                  disabled={busy}
                  onClick={() => onEdit({ op: "remove", target_local_id: node.local_id })}
                >
                  remove
                </button>
              )}
            </div>
          </>
        )}
      </div>
      {node.children.map((c) => (
        <PlanNodeRow key={c.local_id} node={c} depth={depth + 1} busy={busy} onEdit={onEdit} />
      ))}
    </div>
  );
}

function countLeaves(node: PlanNode): number {
  if (!node.children.length) return 1;
  return node.children.reduce((n, c) => n + countLeaves(c), 0);
}
