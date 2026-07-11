/**
 * AntiekProductWorkstationShell - top composition of product modes.
 *
 * Free-file: does not own App.tsx / AppShell / mode indexes.
 * Injectable slots for Research, Reading, Library, Settings, Midnight Oil,
 * Twin. Empty slots honest including empty React.Fragment.
 */

import React, { type ReactNode } from "react";
import { LemonCard } from "./lemon";

export type AntiekProductSlotId =
  | "research"
  | "reading"
  | "library"
  | "settings"
  | "midnight_oil"
  | "twin";

export interface AntiekProductWorkstationShellProps {
  /** Operator scope id (required). */
  operatorId: string;
  operatorLabel?: string;
  slots?: Partial<Record<AntiekProductSlotId, ReactNode>>;
  slotOrder?: AntiekProductSlotId[];
}

const DEFAULT_ORDER: AntiekProductSlotId[] = [
  "research",
  "reading",
  "library",
  "settings",
  "midnight_oil",
  "twin",
];

const SLOT_TITLES: Record<AntiekProductSlotId, string> = {
  research: "Research workstation",
  reading: "Reading workstation",
  library: "Library / marketplace",
  settings: "Settings / models / budget",
  midnight_oil: "Midnight Oil unattended",
  twin: "Twin note substrate",
};

export function validateProductOperatorId(operatorId: string): string {
  const id = String(operatorId || "").trim();
  if (!id) {
    throw new Error("operatorId must be a non-empty string");
  }
  return id;
}

export function isProductSlotFilled(content: ReactNode): boolean {
  if (content == null || content === false || content === true) {
    return false;
  }
  if (typeof content === "string" && !content.trim()) {
    return false;
  }
  if (Array.isArray(content)) {
    if (content.length === 0) return false;
    return content.some((child) => isProductSlotFilled(child));
  }
  if (typeof content === "object" && content !== null && "props" in content) {
    const el = content as {
      type?: unknown;
      props?: { children?: ReactNode };
    };
    if (el.type === React.Fragment) {
      return isProductSlotFilled(el.props?.children ?? null);
    }
    if (el.props && "children" in el.props) {
      return isProductSlotFilled(el.props.children as ReactNode);
    }
  }
  return true;
}

export default function AntiekProductWorkstationShell({
  operatorId,
  operatorLabel,
  slots = {},
  slotOrder = DEFAULT_ORDER,
}: AntiekProductWorkstationShellProps) {
  let operator: string;
  let operatorError: string | null = null;
  try {
    operator = validateProductOperatorId(operatorId);
  } catch (e) {
    operator = "";
    operatorError = e instanceof Error ? e.message : String(e);
  }

  if (operatorError) {
    return (
      <div data-testid="antiek-product-workstation-shell">
        <div
          className="text-sm text-danger"
          data-testid="antiek-product-workstation-error"
        >
          {operatorError}
        </div>
      </div>
    );
  }

  return (
    <div
      data-testid="antiek-product-workstation-shell"
      className="flex flex-col gap-4"
    >
      <LemonCard
        title="Antiek product workstation"
        className="antiek-product-workstation-shell"
      >
        <p
          className="text-sm opacity-80"
          data-testid="antiek-product-workstation-blurb"
        >
          Unified knowledge graph / thought-partner surface: research, reading
          (HTML-native), library marketplace, settings (models + budget +
          Antiek-bench), Midnight Oil unattended, and recursive twins. Slots are
          injectable composition shells — this root never invents live dispatch
          or mounts App routes.
        </p>
        <div
          className="mt-2 text-sm"
          data-testid="antiek-product-workstation-operator"
        >
          operator={operator}
          {operatorLabel ? ` · ${operatorLabel}` : ""}
        </div>
      </LemonCard>

      <div
        className="flex flex-col gap-3"
        data-testid="antiek-product-workstation-slots"
      >
        {slotOrder.map((id) => {
          const content = slots[id];
          const filled = isProductSlotFilled(content);
          return (
            <section
              key={id}
              data-testid={`antiek-product-workstation-slot-${id}`}
              data-slot={id}
              data-filled={filled ? "true" : "false"}
              className="rounded border border-border p-2"
            >
              <h3 className="text-sm font-medium mb-2">{SLOT_TITLES[id]}</h3>
              {filled ? (
                <div
                  data-testid={`antiek-product-workstation-slot-body-${id}`}
                >
                  {content}
                </div>
              ) : (
                <div
                  className="text-xs opacity-70"
                  data-testid={`antiek-product-workstation-slot-empty-${id}`}
                >
                  Slot empty - mount workstation shell when available (no
                  invent).
                </div>
              )}
            </section>
          );
        })}
      </div>
    </div>
  );
}
