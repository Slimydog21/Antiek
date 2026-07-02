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

import LemonButton from "../../components/lemon/LemonButton";
import { PLAN_MAX_NODE_DEPTH, type PlanNode, type PlanTree } from "../../api/research";

export type PlanEdit =
  | { op: "add_child" | "remove" | "reword"; target_local_id: string; question?: string }
  | { op: "set_budget"; target_local_id: string; budget_usd?: number; max_depth?: number }
  | { op: "split"; target_local_id: string; into: string[] };

export interface PlanEditorProps {
  tree: PlanTree;
  launchable: boolean;
  busy?: boolean;
  onEdit: (edit: PlanEdit) => void;
  onApprove: () => void;
  onLaunch: () => void;
}

export default function PlanEditor({ tree, launchable, busy, onEdit, onApprove, onLaunch }: PlanEditorProps) {
  const leafCount = countLeaves(tree.root);
  return (
    <div className="flex h-full flex-col gap-3">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold text-ink dark:text-bright">Cascade plan</h2>
          <p className="text-[11px] text-shadow-1 dark:text-moonlight">
            {leafCount} focused {leafCount === 1 ? "research" : "researches"} ·{" "}
            {tree.approval.state === "approved" ? "approved" : "draft (edit, then approve)"}
          </p>
        </div>
        <div className="flex gap-2">
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
  const [budgeting, setBudgeting] = useState(false);
  const [splitting, setSplitting] = useState(false);
  const [draft, setDraft] = useState(node.question);
  const [budgetDraft, setBudgetDraft] = useState(node.budget_usd === null ? "" : String(node.budget_usd));
  const [depthDraft, setDepthDraft] = useState(node.max_depth === null ? "" : String(node.max_depth));
  const [splitDraft, setSplitDraft] = useState("");
  const canEditDepth = node.children.length > 0;
  const parsedBudget = parseOptionalNumber(budgetDraft);
  const parsedDepth = canEditDepth ? parseOptionalInteger(depthDraft) : undefined;
  const budgetValid = !budgetDraft.trim() || parsedBudget !== undefined;
  const depthValid = !canEditDepth || !depthDraft.trim() || parsedDepth !== undefined;
  const budgetChanged = parsedBudget !== undefined && parsedBudget !== node.budget_usd;
  const depthChanged = parsedDepth !== undefined && parsedDepth !== node.max_depth;
  const canSaveLimits = budgetValid && depthValid && (budgetChanged || depthChanged);
  const splitTargets = splitQuestions(splitDraft);

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
              <button
                className="text-[11px] text-shadow-1 hover:text-aurora dark:text-moonlight"
                disabled={busy}
                onClick={() => {
                  setBudgetDraft(node.budget_usd === null ? "" : String(node.budget_usd));
                  setDepthDraft(node.max_depth === null ? "" : String(node.max_depth));
                  setBudgeting((v) => !v);
                  setSplitting(false);
                }}
              >
                budget
              </button>
              <button
                className="text-[11px] text-shadow-1 hover:text-aurora dark:text-moonlight"
                disabled={busy}
                onClick={() => {
                  setSplitDraft("");
                  setSplitting((v) => !v);
                  setBudgeting(false);
                }}
              >
                split
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
      {budgeting && (
        <form
          className="ml-5 mt-1 flex flex-wrap items-end gap-2 rounded border border-ice-3 bg-ice-1 p-2 dark:border-slate-2 dark:bg-charcoal-1"
          onSubmit={(e) => {
            e.preventDefault();
            if (!canSaveLimits) return;
            onEdit({
              op: "set_budget",
              target_local_id: node.local_id,
              ...(parsedBudget === undefined ? {} : { budget_usd: parsedBudget }),
              ...(parsedDepth === undefined ? {} : { max_depth: parsedDepth }),
            });
            setBudgeting(false);
          }}
        >
          <label className="flex flex-col gap-1 text-[11px] text-shadow-1 dark:text-moonlight">
            budget USD
            <input
              className="w-24 rounded border border-ice-4 bg-ice-0 px-2 py-1 text-sm text-ink dark:border-slate-2 dark:bg-charcoal-2 dark:text-bright"
              value={budgetDraft}
              inputMode="decimal"
              onChange={(e) => setBudgetDraft(e.target.value)}
            />
          </label>
          <label className="flex flex-col gap-1 text-[11px] text-shadow-1 dark:text-moonlight">
            max depth
            <input
              className="w-20 rounded border border-ice-4 bg-ice-0 px-2 py-1 text-sm text-ink dark:border-slate-2 dark:bg-charcoal-2 dark:text-bright"
              value={depthDraft}
              disabled={!canEditDepth}
              inputMode="numeric"
              onChange={(e) => setDepthDraft(e.target.value)}
            />
          </label>
          <LemonButton size="sm" variant="primary" type="submit" disabled={busy || !canSaveLimits}>Save limits</LemonButton>
        </form>
      )}
      {splitting && (
        <form
          className="ml-5 mt-1 flex flex-col gap-2 rounded border border-ice-3 bg-ice-1 p-2 dark:border-slate-2 dark:bg-charcoal-1"
          onSubmit={(e) => {
            e.preventDefault();
            if (splitTargets.length >= 2) {
              onEdit({ op: "split", target_local_id: node.local_id, into: splitTargets });
              setSplitting(false);
            }
          }}
        >
          <textarea
            className="min-h-20 rounded border border-ice-4 bg-ice-0 px-2 py-1 text-sm text-ink dark:border-slate-2 dark:bg-charcoal-2 dark:text-bright"
            value={splitDraft}
            onChange={(e) => setSplitDraft(e.target.value)}
            aria-label="split sub-questions"
            placeholder="One focused sub-question per line"
          />
          <div className="flex justify-end">
            <LemonButton size="sm" variant="primary" type="submit" disabled={busy || splitTargets.length < 2}>Split</LemonButton>
          </div>
        </form>
      )}
      {node.children.map((c) => (
        <PlanNodeRow key={c.local_id} node={c} depth={depth + 1} busy={busy} onEdit={onEdit} />
      ))}
    </div>
  );
}

function parseOptionalNumber(value: string): number | undefined {
  const trimmed = value.trim();
  if (!trimmed) return undefined;
  const parsed = Number(trimmed);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : undefined;
}

function parseOptionalInteger(value: string): number | undefined {
  const trimmed = value.trim();
  if (!trimmed) return undefined;
  if (!/^[1-9]\d*$/.test(trimmed)) return undefined;
  const parsed = Number(trimmed);
  return Number.isSafeInteger(parsed) && parsed <= PLAN_MAX_NODE_DEPTH
    ? parsed
    : undefined;
}

function splitQuestions(value: string): string[] {
  return value
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
}

function countLeaves(node: PlanNode): number {
  if (!node.children.length) return 1;
  return node.children.reduce((n, c) => n + countLeaves(c), 0);
}
