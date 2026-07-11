/**
 * ReadingWorkstationShell - composition surface for HTML reading + research.
 *
 * Free-file: does not own Reading/index, App.tsx, or rrv-712 product path.
 * Injectable slots for HTML reader, highlight→twin, floating deep research,
 * draft/full merge, collective pack, and twin workstation.
 * Empty slots honest; never invents research dispatch or merge completion.
 */

import React, { type ReactNode } from "react";
import { LemonCard } from "../../components/lemon";

export type ReadingWorkstationSlotId =
  | "html_reader"
  | "highlight_twin"
  | "floating_deep_research"
  | "draft_merge"
  | "full_merge"
  | "collective_pack"
  | "twin_workstation";

export interface ReadingWorkstationShellProps {
  /** Parent reading asset / document id (required). */
  assetId: string;
  assetLabel?: string;
  slots?: Partial<Record<ReadingWorkstationSlotId, ReactNode>>;
  slotOrder?: ReadingWorkstationSlotId[];
}

const DEFAULT_ORDER: ReadingWorkstationSlotId[] = [
  "html_reader",
  "highlight_twin",
  "floating_deep_research",
  "draft_merge",
  "full_merge",
  "collective_pack",
  "twin_workstation",
];

const SLOT_TITLES: Record<ReadingWorkstationSlotId, string> = {
  html_reader: "HTML reader",
  highlight_twin: "Highlight → twin notes",
  floating_deep_research: "Floating deep research",
  draft_merge: "Draft merge (provisional)",
  full_merge: "Full merge authorize",
  collective_pack: "Collective deep research pack",
  twin_workstation: "Twin note substrate",
};

export function validateReadingAssetId(assetId: string): string {
  const id = String(assetId || "").trim();
  if (!id) {
    throw new Error("assetId must be a non-empty string");
  }
  return id;
}

/**
 * True only when the slot has content React will visibly render.
 * null/undefined/false/true/empty-string are empty (no invent filled).
 * Arrays are filled only if any element is filled (recursive).
 * Empty React.Fragment stays empty.
 */
export function isReadingSlotFilled(content: ReactNode): boolean {
  if (content == null || content === false || content === true) {
    return false;
  }
  if (typeof content === "string" && !content.trim()) {
    return false;
  }
  if (Array.isArray(content)) {
    if (content.length === 0) return false;
    return content.some((child) => isReadingSlotFilled(child));
  }
  if (typeof content === "object" && content !== null && "props" in content) {
    const el = content as {
      type?: unknown;
      props?: { children?: ReactNode };
    };
    if (el.type === React.Fragment) {
      return isReadingSlotFilled(el.props?.children ?? null);
    }
    if (el.props && "children" in el.props) {
      return isReadingSlotFilled(el.props.children as ReactNode);
    }
  }
  return true;
}

export default function ReadingWorkstationShell({
  assetId,
  assetLabel,
  slots = {},
  slotOrder = DEFAULT_ORDER,
}: ReadingWorkstationShellProps) {
  let asset: string;
  let assetError: string | null = null;
  try {
    asset = validateReadingAssetId(assetId);
  } catch (e) {
    asset = "";
    assetError = e instanceof Error ? e.message : String(e);
  }

  if (assetError) {
    return (
      <div data-testid="reading-workstation-shell">
        <div
          className="text-sm text-danger"
          data-testid="reading-workstation-error"
        >
          {assetError}
        </div>
      </div>
    );
  }

  return (
    <div data-testid="reading-workstation-shell" className="flex flex-col gap-4">
      <LemonCard
        title="Reading workstation"
        className="reading-workstation-shell"
      >
        <p className="text-sm opacity-80" data-testid="reading-workstation-blurb">
          HTML-native reading with highlight→research branches, floating deep
          research instances, draft/full merge, and collective packs. Reading and
          research share this loop; slots are injectable and never invent merge
          or live dispatch.
        </p>
        <div className="mt-2 text-sm" data-testid="reading-workstation-asset">
          asset={asset}
          {assetLabel ? ` · ${assetLabel}` : ""}
        </div>
      </LemonCard>

      <div
        className="flex flex-col gap-3"
        data-testid="reading-workstation-slots"
      >
        {slotOrder.map((id) => {
          const content = slots[id];
          const filled = isReadingSlotFilled(content);
          return (
            <section
              key={id}
              data-testid={`reading-workstation-slot-${id}`}
              data-slot={id}
              data-filled={filled ? "true" : "false"}
              className="rounded border border-border p-2"
            >
              <h3 className="text-sm font-medium mb-2">{SLOT_TITLES[id]}</h3>
              {filled ? (
                <div data-testid={`reading-workstation-slot-body-${id}`}>
                  {content}
                </div>
              ) : (
                <div
                  className="text-xs opacity-70"
                  data-testid={`reading-workstation-slot-empty-${id}`}
                >
                  Slot empty - mount panel when available (no invent).
                </div>
              )}
            </section>
          );
        })}
      </div>
    </div>
  );
}
