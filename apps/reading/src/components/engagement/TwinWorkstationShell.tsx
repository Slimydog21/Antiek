/**
 * TwinWorkstationShell — composition surface for the recursive twin stack.
 *
 * Free-file: does not own Reading/index, App.tsx, or rrv-712 floating hosts.
 * Slots are injectable React nodes so stacked twin panels (#842–#859) can be
 * mounted by a future composition residual without this shell importing them.
 *
 * Requires explicit parent_asset_id context (no invent).
 */

import type { ReactNode } from "react";
import { LemonCard } from "../lemon";

export type TwinWorkstationSlotId =
  | "notes"
  | "search"
  | "compose"
  | "collective"
  | "draft_merge"
  | "finalize"
  | "highlight"
  | "note_taker";

export interface TwinWorkstationShellProps {
  /** Required parent asset context for the twin stack. */
  parentAssetId: string;
  /** Optional human label for the parent asset. */
  parentLabel?: string;
  /**
   * Injectable slot content. Missing slots render an honest empty placeholder
   * (never invent panel content).
   */
  slots?: Partial<Record<TwinWorkstationSlotId, ReactNode>>;
  /** Optional ordered slot list; defaults to full workstation order. */
  slotOrder?: TwinWorkstationSlotId[];
}

const DEFAULT_ORDER: TwinWorkstationSlotId[] = [
  "notes",
  "search",
  "highlight",
  "note_taker",
  "compose",
  "collective",
  "draft_merge",
  "finalize",
];

const SLOT_TITLES: Record<TwinWorkstationSlotId, string> = {
  notes: "Twin notes (CRUD)",
  search: "Twin search",
  compose: "Compose analysis",
  collective: "Collective pack",
  draft_merge: "Draft merge",
  finalize: "Finalize gate",
  highlight: "From highlight",
  note_taker: "LLM note-taker",
};

export function validateParentAssetId(parentAssetId: string): string {
  const id = String(parentAssetId || "").trim();
  if (!id) {
    throw new Error("parentAssetId must be a non-empty string");
  }
  return id;
}

export default function TwinWorkstationShell({
  parentAssetId,
  parentLabel,
  slots = {},
  slotOrder = DEFAULT_ORDER,
}: TwinWorkstationShellProps) {
  let parent: string;
  let parentError: string | null = null;
  try {
    parent = validateParentAssetId(parentAssetId);
  } catch (e) {
    parent = "";
    parentError = e instanceof Error ? e.message : String(e);
  }

  if (parentError) {
    return (
      <div data-testid="twin-workstation-shell">
        <div className="text-sm text-danger" data-testid="twin-workstation-error">
          {parentError}
        </div>
      </div>
    );
  }

  return (
    <div data-testid="twin-workstation-shell" className="flex flex-col gap-4">
      <LemonCard title="Twin workstation" className="twin-workstation-shell">
        <p className="text-sm opacity-80" data-testid="twin-workstation-blurb">
          Recursive note-taker workstation for parent asset context. Slots are
          composed injectably — this shell does not invent twin content or
          dispatch models.
        </p>
        <div className="mt-2 text-sm" data-testid="twin-workstation-parent">
          parent={parent}
          {parentLabel ? ` · ${parentLabel}` : ""}
        </div>
      </LemonCard>

      <div
        className="flex flex-col gap-3"
        data-testid="twin-workstation-slots"
      >
        {slotOrder.map((id) => {
          const content = slots[id];
          return (
            <section
              key={id}
              data-testid={`twin-workstation-slot-${id}`}
              data-slot={id}
              data-filled={content != null ? "true" : "false"}
              className="rounded border border-border p-2"
            >
              <h3 className="text-sm font-medium mb-2">{SLOT_TITLES[id]}</h3>
              {content != null ? (
                <div data-testid={`twin-workstation-slot-body-${id}`}>
                  {content}
                </div>
              ) : (
                <div
                  className="text-xs opacity-70"
                  data-testid={`twin-workstation-slot-empty-${id}`}
                >
                  Slot empty — mount panel when available (no invent).
                </div>
              )}
            </section>
          );
        })}
      </div>
    </div>
  );
}
