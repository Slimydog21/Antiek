import { cloneElement, useId } from "react";
import type { ReactElement } from "react";

import "./Tooltip.css";

/**
 * Tooltip: the CSS-only tip (Tooltip.css) plus the accessible description.
 *
 *   <Tooltip tip="Opens the reader in a new window">
 *     <button …>Pop out</button>
 *   </Tooltip>
 *
 * The child gets `data-tip` (the visible tip, shown on hover and on keyboard
 * focus) and `aria-describedby` pointing at a hidden span with the same words,
 * so a screen reader hears them too. The child must be focusable for the
 * keyboard half to work; a disabled control should stay focusable
 * (aria-disabled, as LemonButton's disabledReason does) rather than use the
 * native `disabled` attribute, which drops it from the tab order.
 *
 * `tipProps` is the same wiring for a component that renders its own element
 * (LemonButton, LemonMenuItem) and cannot be wrapped.
 */
export type TipPlacement = { placement?: "top" | "bottom"; align?: "center" | "start" | "end" };

export function tipProps(
  tip: string | null | undefined,
  id: string,
  describedBy: string | undefined,
  { placement = "top", align = "center" }: TipPlacement = {},
) {
  if (!tip) return { "aria-describedby": describedBy };
  return {
    "data-tip": tip,
    "data-tip-placement": placement === "top" ? undefined : placement,
    "data-tip-align": align === "center" ? undefined : align,
    "aria-describedby": describedBy ? `${describedBy} ${id}` : id,
  };
}

/** The hidden description a data-tip element points aria-describedby at. */
export function TipText({ id, tip }: { id: string; tip: string | null | undefined }) {
  if (!tip) return null;
  return (
    <span id={id} hidden>
      {tip}
    </span>
  );
}

type Props = TipPlacement & {
  tip: string | null | undefined;
  children: ReactElement<{ "aria-describedby"?: string }>;
};

export function Tooltip({ tip, children, placement, align }: Props) {
  const id = useId();
  const extra = tipProps(tip, id, children.props["aria-describedby"], { placement, align });
  return (
    <>
      {cloneElement(children, extra)}
      <TipText id={id} tip={tip} />
    </>
  );
}

export default Tooltip;
