/**
 * LibraryWorkstationShell - marketplace to HTML-host composition surface.
 *
 * Free-file: does not own Library/index or App.tsx.
 * Injectable slots for free-copy preflight, purchase gate, HTML host port,
 * catalog, and HTML preference. Empty slots honest; never invents purchase
 * or hosted completion.
 */

import type { ReactNode } from "react";
import { LemonCard } from "../../components/lemon";

export type LibraryWorkstationSlotId =
  | "catalog"
  | "free_copy"
  | "purchase_gate"
  | "html_host"
  | "html_preference";

export interface LibraryWorkstationShellProps {
  operatorId: string;
  slots?: Partial<Record<LibraryWorkstationSlotId, ReactNode>>;
  slotOrder?: LibraryWorkstationSlotId[];
}

const DEFAULT_ORDER: LibraryWorkstationSlotId[] = [
  "catalog",
  "free_copy",
  "purchase_gate",
  "html_host",
  "html_preference",
];

const SLOT_TITLES: Record<LibraryWorkstationSlotId, string> = {
  catalog: "Library catalog",
  free_copy: "Free-copy preflight",
  purchase_gate: "Purchase gate",
  html_host: "HTML host port",
  html_preference: "HTML view preference",
};

export function validateLibraryOperatorId(operatorId: string): string {
  const id = String(operatorId || "").trim();
  if (!id) {
    throw new Error("operatorId must be a non-empty string");
  }
  return id;
}

export function isLibrarySlotFilled(content: ReactNode): boolean {
  if (content == null || content === false || content === true) {
    return false;
  }
  if (typeof content === "string" && !content.trim()) {
    return false;
  }
  if (Array.isArray(content)) {
    if (content.length === 0) return false;
    return content.some((child) => isLibrarySlotFilled(child));
  }
  return true;
}

export default function LibraryWorkstationShell({
  operatorId,
  slots = {},
  slotOrder = DEFAULT_ORDER,
}: LibraryWorkstationShellProps) {
  let operator: string;
  let operatorError: string | null = null;
  try {
    operator = validateLibraryOperatorId(operatorId);
  } catch (e) {
    operator = "";
    operatorError = e instanceof Error ? e.message : String(e);
  }

  if (operatorError) {
    return (
      <div data-testid="library-workstation-shell">
        <div
          className="text-sm text-danger"
          data-testid="library-workstation-error"
        >
          {operatorError}
        </div>
      </div>
    );
  }

  return (
    <div data-testid="library-workstation-shell" className="flex flex-col gap-4">
      <LemonCard title="Library workstation" className="library-workstation-shell">
        <p className="text-sm opacity-80" data-testid="library-workstation-blurb">
          Marketplace honesty then HTML-native host: search free copies first,
          gate purchase intent, host only ready HTML projections. This shell
          never executes charges or invents hosted assets.
        </p>
        <div className="mt-2 text-sm" data-testid="library-workstation-operator">
          operator={operator}
        </div>
        <div className="text-xs opacity-70" data-testid="library-workstation-doctrine">
          doctrine=HTML-native; purchase_executed=false at composition
        </div>
      </LemonCard>

      <div
        className="flex flex-col gap-3"
        data-testid="library-workstation-slots"
      >
        {slotOrder.map((id) => {
          const content = slots[id];
          const filled = isLibrarySlotFilled(content);
          return (
            <section
              key={id}
              data-testid={`library-workstation-slot-${id}`}
              data-slot={id}
              data-filled={filled ? "true" : "false"}
              className="rounded border border-border p-2"
            >
              <h3 className="text-sm font-medium mb-2">{SLOT_TITLES[id]}</h3>
              {filled ? (
                <div data-testid={`library-workstation-slot-body-${id}`}>
                  {content}
                </div>
              ) : (
                <div
                  className="text-xs opacity-70"
                  data-testid={`library-workstation-slot-empty-${id}`}
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
