/**
 * SettingsWorkstationShell - composition surface for model/budget/settings.
 *
 * Free-file: does not own Settings/index or App.tsx.
 * Injectable slots for decision tree, inventory, usage bar, prompt projection,
 * Antiek-bench, NotDiamond shadow (advisory only), and add-model.
 * Empty slots honest; never invents live meters or production ND routing.
 */

import React, { type ReactNode } from "react";
import { LemonCard } from "../../components/lemon";

export type SettingsWorkstationSlotId =
  | "decision_tree"
  | "model_inventory"
  | "usage_bar"
  | "prompt_projection"
  | "antiek_bench"
  | "notdiamond_shadow"
  | "add_model";

export interface SettingsWorkstationShellProps {
  /** Operator / settings scope id (required). */
  operatorId: string;
  operatorLabel?: string;
  slots?: Partial<Record<SettingsWorkstationSlotId, ReactNode>>;
  slotOrder?: SettingsWorkstationSlotId[];
}

const DEFAULT_ORDER: SettingsWorkstationSlotId[] = [
  "decision_tree",
  "model_inventory",
  "usage_bar",
  "prompt_projection",
  "antiek_bench",
  "notdiamond_shadow",
  "add_model",
];

const SLOT_TITLES: Record<SettingsWorkstationSlotId, string> = {
  decision_tree: "Model decision tree",
  model_inventory: "Model inventory",
  usage_bar: "Usage / budget bar",
  prompt_projection: "Prompt budget projection",
  antiek_bench: "Antiek-bench weekly",
  notdiamond_shadow: "NotDiamond shadow (advisory)",
  add_model: "Add model (BYOK)",
};

export function validateSettingsOperatorId(operatorId: string): string {
  const id = String(operatorId || "").trim();
  if (!id) {
    throw new Error("operatorId must be a non-empty string");
  }
  return id;
}

/**
 * True only when the slot has content React will visibly render.
 * null/undefined/false/true/empty-string are empty (no invent filled).
 * Arrays are filled only if any element is filled (recursive).
 * Empty React.Fragment (and fragments whose children are empty) stay empty.
 */
export function isSettingsSlotFilled(content: ReactNode): boolean {
  if (content == null || content === false || content === true) {
    return false;
  }
  if (typeof content === "string" && !content.trim()) {
    return false;
  }
  if (Array.isArray(content)) {
    if (content.length === 0) return false;
    return content.some((child) => isSettingsSlotFilled(child));
  }
  // Empty React fragments (and elements whose only children are empty)
  // must not invent filled=true.
  if (typeof content === "object" && content !== null && "props" in content) {
    const el = content as {
      type?: unknown;
      props?: { children?: ReactNode };
    };
    // Fragment with no children prop is empty (props: {}).
    if (el.type === React.Fragment) {
      return isSettingsSlotFilled(el.props?.children ?? null);
    }
    if (el.props && "children" in el.props) {
      return isSettingsSlotFilled(el.props.children as ReactNode);
    }
  }
  return true;
}

export default function SettingsWorkstationShell({
  operatorId,
  operatorLabel,
  slots = {},
  slotOrder = DEFAULT_ORDER,
}: SettingsWorkstationShellProps) {
  let operator: string;
  let operatorError: string | null = null;
  try {
    operator = validateSettingsOperatorId(operatorId);
  } catch (e) {
    operator = "";
    operatorError = e instanceof Error ? e.message : String(e);
  }

  if (operatorError) {
    return (
      <div data-testid="settings-workstation-shell">
        <div
          className="text-sm text-danger"
          data-testid="settings-workstation-error"
        >
          {operatorError}
        </div>
      </div>
    );
  }

  return (
    <div data-testid="settings-workstation-shell" className="flex flex-col gap-4">
      <LemonCard
        title="Settings workstation"
        className="settings-workstation-shell"
      >
        <p className="text-sm opacity-80" data-testid="settings-workstation-blurb">
          Model choice, budget honesty, Antiek-bench evidence, and NotDiamond
          shadow (advisory only — never production router). Slots are injectable;
          this shell does not invent meters, spend, or live ND routing.
        </p>
        <div className="mt-2 text-sm" data-testid="settings-workstation-operator">
          operator={operator}
          {operatorLabel ? ` · ${operatorLabel}` : ""}
        </div>
      </LemonCard>

      <div
        className="flex flex-col gap-3"
        data-testid="settings-workstation-slots"
      >
        {slotOrder.map((id) => {
          const content = slots[id];
          const filled = isSettingsSlotFilled(content);
          return (
            <section
              key={id}
              data-testid={`settings-workstation-slot-${id}`}
              data-slot={id}
              data-filled={filled ? "true" : "false"}
              className="rounded border border-border p-2"
            >
              <h3 className="text-sm font-medium mb-2">{SLOT_TITLES[id]}</h3>
              {filled ? (
                <div data-testid={`settings-workstation-slot-body-${id}`}>
                  {content}
                </div>
              ) : (
                <div
                  className="text-xs opacity-70"
                  data-testid={`settings-workstation-slot-empty-${id}`}
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
