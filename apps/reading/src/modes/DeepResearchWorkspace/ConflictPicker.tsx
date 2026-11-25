/**
 * ConflictPicker.tsx — the SPR-00 verdict's side-by-side diff picker
 * (conflict picking = (i), the arena's C winner), re-implemented cleanly —
 * spike code is never merged, and C's own strip/picker sources are not on
 * disk; the verdict's recorded substance is the contract: fork passage vs
 * incoming claim, side by side, a word-level diff, and copy at the decision
 * point that makes a wrong accept LOUD.
 *
 * One card per conflicted item. The fork side is honest about what it
 * holds: the pinned passage's quote for an anchor conflict, the other
 * thread's identical claim for a cross-member pair, and the operator's own
 * flag for a manual conflict. The choices are the SPR-02 resolution
 * vocabulary — accept (the claim is appended to the fork, its source
 * named), keep_fork (the fork stands; the claim stays out), skip (not this
 * merge) — and the accept control names what it does in place:
 * "Merge anyway — your fork keeps its passage AND gains this claim."
 * Nothing here resolves anything; the choice rides the commit call.
 */
import { wordDiff } from "./wordDiff";
import type { ForkMergeConflict, ForkMergeItem } from "../../api/forkMerge";

export type PickerChoice = "accept" | "keep_fork" | "skip";

export function refKey(ref: { investigation_id: string; node_id: string }): string {
  return `${ref.investigation_id}${ref.node_id}`;
}

interface PickerItem {
  ref: { investigation_id: string; node_id: string };
  /** The incoming claim (the item's text). */
  incoming: string;
  /** What the fork side holds, when there is something to show. */
  forkSide: string | null;
  /** Why this is conflicted, in operator words. */
  reason: string;
}

function conflictReason(kind: string): string {
  switch (kind) {
    case "anchor_passage":
      return "A passage pinned on your fork from this same research says something different.";
    case "cross_member_pair":
      return "Another research you're reviewing reached the same claim.";
    default:
      return "You flagged this for review.";
  }
}

/** One picker card per conflicted item; an item in several conflicts shows
 *  its FIRST conflict's fork side (the resolutions are per item — SPR-02). */
export function pickerItems(
  conflicts: ForkMergeConflict[],
  items: ForkMergeItem[],
): PickerItem[] {
  const byRef = new Map(items.map((i) => [refKey(i), i]));
  const seen = new Map<string, PickerItem>();
  for (const conflict of conflicts) {
    for (const ref of conflict.item_refs) {
      const key = refKey(ref);
      if (seen.has(key)) continue;
      const item = byRef.get(key);
      if (!item) continue;
      let forkSide: string | null = null;
      if (conflict.kind === "anchor_passage") forkSide = conflict.anchor_quote;
      else if (conflict.kind === "cross_member_pair") {
        const other = conflict.item_refs.find((r) => refKey(r) !== key);
        forkSide = (other && byRef.get(refKey(other))?.text) ?? null;
      }
      seen.set(key, {
        ref,
        incoming: item.text,
        forkSide,
        reason: conflictReason(conflict.kind),
      });
    }
  }
  return [...seen.values()];
}

export default function ConflictPicker({
  conflicts,
  items,
  choices,
  onChoose,
}: {
  conflicts: ForkMergeConflict[];
  items: ForkMergeItem[];
  choices: Record<string, PickerChoice>;
  onChoose: (ref: { investigation_id: string; node_id: string }, choice: PickerChoice) => void;
}) {
  const rows = pickerItems(conflicts, items);
  return (
    <ol className="space-y-3" data-conflict-picker>
      {rows.map((row) => {
        const key = refKey(row.ref);
        const choice = choices[key] ?? null;
        const diff = row.forkSide !== null ? wordDiff(row.forkSide, row.incoming) : null;
        return (
          <li
            key={key}
            data-conflict-item
            className="rounded-hog border-2 border-sun bg-ice-0 p-3 dark:bg-charcoal-2"
          >
            <p className="mb-2 font-mono text-xxs uppercase tracking-wide text-sun-deep dark:text-sun">
              Conflict — your call
            </p>
            <p className="mb-2 font-serif text-xs italic text-ink-soft dark:text-starlight">
              {row.reason} Nothing merges until you choose.
            </p>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              <div
                className="rounded border border-rule bg-ice-1 p-2 dark:border-charcoal-1 dark:bg-charcoal-1"
                data-picker-fork-side
              >
                <p className="mb-1 font-mono text-xxs uppercase tracking-wide text-shadow-1 dark:text-moonlight">
                  On your fork
                </p>
                <p className="font-serif text-sm leading-relaxed text-ink dark:text-bright">
                  {diff
                    ? diff.left.map((seg, i) => (
                        <span
                          key={i}
                          className={
                            seg.side === "left"
                              ? "bg-sun/25 rounded-sm px-0.5"
                              : undefined
                          }
                        >
                          {seg.text}{" "}
                        </span>
                      ))
                    : (row.forkSide ?? "Nothing pinned on your fork for this one.")}
                </p>
              </div>
              <div
                className="rounded border border-rule bg-ice-1 p-2 dark:border-charcoal-1 dark:bg-charcoal-1"
                data-picker-incoming-side
              >
                <p className="mb-1 font-mono text-xxs uppercase tracking-wide text-shadow-1 dark:text-moonlight">
                  Incoming claim
                </p>
                <p className="font-serif text-sm leading-relaxed text-ink dark:text-bright">
                  {diff
                    ? diff.right.map((seg, i) => (
                        <span
                          key={i}
                          className={
                            seg.side === "right"
                              ? "bg-emperor/15 rounded-sm px-0.5"
                              : undefined
                          }
                        >
                          {seg.text}{" "}
                        </span>
                      ))
                    : row.incoming}
                </p>
              </div>
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-2" role="group" aria-label="Resolve this conflict">
              <button
                type="button"
                data-choice="accept"
                aria-pressed={choice === "accept"}
                onClick={() => onChoose(row.ref, "accept")}
                title="The claim is appended to your fork under a note naming its source research — your fork's own passage stays"
                className={choiceButtonClass(choice === "accept")}
              >
                Merge anyway — adds to your fork
              </button>
              <button
                type="button"
                data-choice="keep_fork"
                aria-pressed={choice === "keep_fork"}
                onClick={() => onChoose(row.ref, "keep_fork")}
                title="The fork stands as it is; this claim stays out — recorded as your call"
                className={choiceButtonClass(choice === "keep_fork")}
              >
                Keep my fork as it is
              </button>
              <button
                type="button"
                data-choice="skip"
                aria-pressed={choice === "skip"}
                onClick={() => onChoose(row.ref, "skip")}
                title="Neither — leave this item out of this merge"
                className={choiceButtonClass(choice === "skip")}
              >
                Skip for now
              </button>
            </div>
            {choice === "accept" && (
              <p className="mt-1.5 font-serif text-xs italic text-ink-soft dark:text-starlight">
                Your fork keeps its passage and gains this claim, with its
                source research named. The original book is never touched.
              </p>
            )}
          </li>
        );
      })}
    </ol>
  );
}

function choiceButtonClass(active: boolean): string {
  return `rounded border px-2 py-1 font-mono text-xs focus-visible:outline focus-visible:outline-2 focus-visible:outline-sun ${
    active
      ? "border-ink bg-ink text-white dark:border-bright dark:bg-bright dark:text-ink"
      : "border-rule text-ink hover:bg-ice-2 dark:border-charcoal-1 dark:text-bright dark:hover:bg-charcoal-1"
  }`;
}
