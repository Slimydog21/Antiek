/**
 * ResearchWorkstationShell - composition surface for the research loop.
 *
 * Free-file: does not own ResearchWorkstation/index, App.tsx, or rrv-712.
 * Injectable slots for source preflight, source pack, cascade launch, and
 * twin workstation. Empty slots honest; session context required.
 */

import type { ReactNode } from "react";
import { LemonCard } from "../lemon";

export type ResearchWorkstationSlotId =
  | "source_preflight"
  | "source_pack"
  | "cascade_launch"
  | "twin_workstation"
  | "model_decision"
  | "usage_bar";

export interface ResearchWorkstationShellProps {
  /** Required session / investigation context id. */
  sessionId: string;
  sessionLabel?: string;
  slots?: Partial<Record<ResearchWorkstationSlotId, ReactNode>>;
  slotOrder?: ResearchWorkstationSlotId[];
}

const DEFAULT_ORDER: ResearchWorkstationSlotId[] = [
  "source_preflight",
  "source_pack",
  "cascade_launch",
  "model_decision",
  "usage_bar",
  "twin_workstation",
];

const SLOT_TITLES: Record<ResearchWorkstationSlotId, string> = {
  source_preflight: "Source policy preflight",
  source_pack: "Deep research source pack",
  cascade_launch: "Cascade launch",
  twin_workstation: "Twin note substrate",
  model_decision: "Model decision tree",
  usage_bar: "Usage / budget bar",
};

export function validateSessionId(sessionId: string): string {
  const id = String(sessionId || "").trim();
  if (!id) {
    throw new Error("sessionId must be a non-empty string");
  }
  return id;
}

/**
 * True only when the slot has content React will visibly render.
 * null/undefined/false/true/empty-string are empty (no invent filled).
 */
export function isResearchSlotFilled(content: ReactNode): boolean {
  if (content == null || content === false || content === true) {
    return false;
  }
  if (typeof content === "string" && !content.trim()) {
    return false;
  }
  return true;
}

export default function ResearchWorkstationShell({
  sessionId,
  sessionLabel,
  slots = {},
  slotOrder = DEFAULT_ORDER,
}: ResearchWorkstationShellProps) {
  let session: string;
  let sessionError: string | null = null;
  try {
    session = validateSessionId(sessionId);
  } catch (e) {
    session = "";
    sessionError = e instanceof Error ? e.message : String(e);
  }

  if (sessionError) {
    return (
      <div data-testid="research-workstation-shell">
        <div
          className="text-sm text-danger"
          data-testid="research-workstation-error"
        >
          {sessionError}
        </div>
      </div>
    );
  }

  return (
    <div data-testid="research-workstation-shell" className="flex flex-col gap-4">
      <LemonCard
        title="Research workstation"
        className="research-workstation-shell"
      >
        <p className="text-sm opacity-80" data-testid="research-workstation-blurb">
          Live research loop composition: preflight sources, build knowledge
          packs, launch cascades, and ground twins. Slots are injectable; this
          shell does not invent research content or dispatch models.
        </p>
        <div className="mt-2 text-sm" data-testid="research-workstation-session">
          session={session}
          {sessionLabel ? ` · ${sessionLabel}` : ""}
        </div>
      </LemonCard>

      <div
        className="flex flex-col gap-3"
        data-testid="research-workstation-slots"
      >
        {slotOrder.map((id) => {
          const content = slots[id];
          const filled = isResearchSlotFilled(content);
          return (
            <section
              key={id}
              data-testid={`research-workstation-slot-${id}`}
              data-slot={id}
              data-filled={filled ? "true" : "false"}
              className="rounded border border-border p-2"
            >
              <h3 className="text-sm font-medium mb-2">{SLOT_TITLES[id]}</h3>
              {filled ? (
                <div data-testid={`research-workstation-slot-body-${id}`}>
                  {content}
                </div>
              ) : (
                <div
                  className="text-xs opacity-70"
                  data-testid={`research-workstation-slot-empty-${id}`}
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
