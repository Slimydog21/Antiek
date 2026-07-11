/**
 * MidnightOilWorkstationShell - composition for unattended deep research mode.
 *
 * Free-file: does not own MidnightOil/index or App.tsx.
 * Injectable slots for price ceiling, unattended brief, launch gate, spend
 * consent. Empty slots honest; never invents live spend authorization.
 */

import type { ReactNode } from "react";
import { LemonCard } from "../../components/lemon";

export type MidnightOilSlotId =
  | "price_ceiling"
  | "unattended_brief"
  | "launch_gate"
  | "spend_consent"
  | "job_status";

export interface MidnightOilWorkstationShellProps {
  operatorId: string;
  slots?: Partial<Record<MidnightOilSlotId, ReactNode>>;
  slotOrder?: MidnightOilSlotId[];
}

const DEFAULT_ORDER: MidnightOilSlotId[] = [
  "price_ceiling",
  "unattended_brief",
  "spend_consent",
  "launch_gate",
  "job_status",
];

const SLOT_TITLES: Record<MidnightOilSlotId, string> = {
  price_ceiling: "Recommended price ceiling",
  unattended_brief: "Unattended brief (time + goals)",
  launch_gate: "Launch gate",
  spend_consent: "Spend consent receipt",
  job_status: "Job status",
};

export function validateOperatorId(operatorId: string): string {
  const id = String(operatorId || "").trim();
  if (!id) {
    throw new Error("operatorId must be a non-empty string");
  }
  return id;
}

export function isMoSlotFilled(content: ReactNode): boolean {
  if (content == null || content === false || content === true) {
    return false;
  }
  if (typeof content === "string" && !content.trim()) {
    return false;
  }
  if (Array.isArray(content)) {
    if (content.length === 0) return false;
    return content.some((child) => isMoSlotFilled(child));
  }
  return true;
}

export default function MidnightOilWorkstationShell({
  operatorId,
  slots = {},
  slotOrder = DEFAULT_ORDER,
}: MidnightOilWorkstationShellProps) {
  let operator: string;
  let operatorError: string | null = null;
  try {
    operator = validateOperatorId(operatorId);
  } catch (e) {
    operator = "";
    operatorError = e instanceof Error ? e.message : String(e);
  }

  if (operatorError) {
    return (
      <div data-testid="mo-workstation-shell">
        <div className="text-sm text-danger" data-testid="mo-workstation-error">
          {operatorError}
        </div>
      </div>
    );
  }

  return (
    <div data-testid="mo-workstation-shell" className="flex flex-col gap-4">
      <LemonCard title="Midnight Oil" className="mo-workstation-shell">
        <p className="text-sm opacity-80" data-testid="mo-workstation-blurb">
          Unattended deep research: set time and goals, approve a price ceiling,
          bind spend consent, then evaluate the launch gate. This shell never
          authorizes live spend or dispatches workers.
        </p>
        <div className="mt-2 text-sm" data-testid="mo-workstation-operator">
          operator={operator}
        </div>
        <div className="text-xs opacity-70" data-testid="mo-workstation-live">
          live_execution_authorized=false (composition only)
        </div>
      </LemonCard>

      <div className="flex flex-col gap-3" data-testid="mo-workstation-slots">
        {slotOrder.map((id) => {
          const content = slots[id];
          const filled = isMoSlotFilled(content);
          return (
            <section
              key={id}
              data-testid={`mo-workstation-slot-${id}`}
              data-slot={id}
              data-filled={filled ? "true" : "false"}
              className="rounded border border-border p-2"
            >
              <h3 className="text-sm font-medium mb-2">{SLOT_TITLES[id]}</h3>
              {filled ? (
                <div data-testid={`mo-workstation-slot-body-${id}`}>
                  {content}
                </div>
              ) : (
                <div
                  className="text-xs opacity-70"
                  data-testid={`mo-workstation-slot-empty-${id}`}
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
