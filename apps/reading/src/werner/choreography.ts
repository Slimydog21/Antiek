import {
  PRODUCT_ACTIVATE_EVENT,
  type ProductActivateDetail,
} from "../components/hotkeys";
import type { WernerStageController } from "./WernerStage";
import { EMOTE_KINDS, type EmoteKind } from "./emotes";

/**
 * Werner choreography (SPR-10) — the "waddle to the activated control" layer.
 *
 * The operator's voice note: when a button is activated, Werner waddles over
 * and gives it a cute Tom-&-Jerry bump, then returns to idle — and this must
 * be IDENTICAL whether the user clicked or pressed the hotkey.
 *
 * Click === hotkey is STRUCTURAL here, not a parallel pair of handlers we keep
 * in sync. SPR-08 funnels BOTH a click and a hotkey through one emit point
 * (`emitProductActivate`) firing one event (PRODUCT_ACTIVATE_EVENT). This
 * listener subscribes to that single event, so a click and a hotkey arrive as
 * the same CustomEvent and run the same code path. There is no second branch
 * to drift — the parity is a property of there being one event, which is why
 * the tests can prove it by dispatching the same event with source:"click"
 * and source:"hotkey" and asserting identical behaviour.
 *
 * Target resolution: the activated control is found at runtime via
 * `document.querySelector('[data-product-id="<productId>"]')`. A concurrent
 * sprint adds that attribute to the NavRail buttons; this listener does not
 * own the markup, only the lookup. Missing element, zero-size element, or an
 * off-screen element → graceful no-op inside WernerStage.waddleToEl (no throw,
 * no waddle to nowhere).
 *
 * Interruption: the stage is latest-wins (one action timer, cleared on every
 * new command), so a burst of activations cancels the in-flight waddle and
 * heads to the last target — Werner is never left stuck mid-walk.
 *
 * Reduced motion: the stage, frozen by the mascot's reduced-motion guard,
 * turns a waddle-to-button into a small in-place acknowledgment emote instead
 * of a screen-crossing walk (handled in WernerStage.waddleToEl). This listener
 * is identical on both paths — it just asks the stage to waddle; the stage
 * decides the reduced-motion form.
 */

export interface ChoreographyOptions {
  /** Resolve the activated control from its detail. Default: query the DOM by
   *  `[data-product-id]`. Overridable so tests can inject a fake element
   *  without touching real markup. */
  resolveTarget?: (detail: ProductActivateDetail) => Element | null;
  /** The window to listen on (default the global). Injectable for tests. */
  target?: Pick<Window, "addEventListener" | "removeEventListener">;
}

/** Build the selector for a product's on-bar control. Exported so a test (or
 *  the concurrent NavRail sprint) can assert the exact attribute contract. */
export function productSelector(detail: ProductActivateDetail): string {
  // CSS.escape guards against an exotic productId breaking the selector.
  const id =
    typeof CSS !== "undefined" && typeof CSS.escape === "function"
      ? CSS.escape(detail.productId)
      : detail.productId;
  return `[data-product-id="${id}"]`;
}

function defaultResolveTarget(detail: ProductActivateDetail): Element | null {
  if (typeof document === "undefined") return null;
  return document.querySelector(productSelector(detail));
}

/**
 * Distinct living-TV emotes per product door (Antiek is the home of the penguin).
 * Unknown products keep the classic Tom-&-Jerry "hit" bump.
 */
export function emoteForProductDoor(productId: string): EmoteKind {
  switch (productId) {
    case "research":
    case "library":
    case "investigations":
    case "documents":
    case "notebooks":
      return "thinking";
    case "read":
    case "speak":
    case "arcade":
    case "sources":
      return "curious";
    case "write":
    case "home":
    case "create":
      return "happy";
    case "more":
    case "settings":
    case "billing":
    case "pricing":
      return "noted";
    case "midnight-oil":
    case "midnight_oil":
      return "sleeping";
    default:
      return "hit";
  }
}

/**
 * Wire the choreography. Returns a teardown function that removes the
 * listener. Call once (the mascot mounts it in an effect, cleaned up on
 * unmount). It never mounts twice — the mascot owns the single instance.
 */
export function installChoreography(
  stage: WernerStageController,
  options: ChoreographyOptions = {},
): () => void {
  const resolve = options.resolveTarget ?? defaultResolveTarget;
  const win = options.target ?? (typeof window !== "undefined" ? window : null);
  if (!win) return () => {};

  const onActivate = (event: Event) => {
    const detail = (event as CustomEvent<ProductActivateDetail>).detail;
    if (!detail || !detail.productId) return;
    const el = resolve(detail);
    // Living-TV: product doors get distinct emotes (not a generic hit for all).
    // waddleToEl no-ops on missing/off-screen targets and downshifts under
    // reduced-motion. Latest-wins interruption is the stage's job.
    const emote = emoteForProductDoor(detail.productId);
    stage.waddleToEl(el, emote);
  };

  win.addEventListener(PRODUCT_ACTIVATE_EVENT, onActivate as EventListener);
  return () => {
    win.removeEventListener(PRODUCT_ACTIVATE_EVENT, onActivate as EventListener);
  };
}

/**
 * The opt-in attribute (SPR-10 M4). Any element carrying `data-werner-target`
 * — or whose ancestor carries it — makes Werner waddle to it + emote when
 * clicked, generalizing the choreography beyond the product bar to ANY UI
 * button that opts in. The attribute VALUE, when it names a valid emote kind
 * (e.g. `data-werner-target="curious"`), picks the emote; bare presence
 * defaults to "hit". Product-bar buttons use `data-product-id` + the activation
 * event instead, so the two paths are disjoint (no double-waddle).
 */
export const WERNER_TARGET_ATTR = "data-werner-target";

function emoteFromAttr(raw: string | null): EmoteKind {
  return raw && (EMOTE_KINDS as readonly string[]).includes(raw)
    ? (raw as EmoteKind)
    : "hit";
}

export interface TargetChoreographyOptions {
  /** The document to attach the capture-phase click listener to. Injectable
   *  for tests; defaults to the global document. */
  target?: Pick<Document, "addEventListener" | "removeEventListener">;
}

/**
 * Wire the opt-in CLICK choreography: a click on any element carrying
 * `data-werner-target` (or a descendant of one) makes Werner waddle to that
 * element and play its emote. Returns a teardown.
 *
 * It listens in the CAPTURE phase and is strictly read-only — it never calls
 * preventDefault / stopPropagation — so the clicked control's own behaviour is
 * untouched; Werner's reaction rides alongside it. waddleToEl is the single
 * decision point (missing/off-screen → no-op; reduced motion → in-place emote),
 * exactly as the activation-event path. Latest-wins interruption is the stage's
 * job, so a spam of opt-in clicks heads to the last target without stacking.
 */
export function installTargetChoreography(
  stage: WernerStageController,
  options: TargetChoreographyOptions = {},
): () => void {
  const doc =
    options.target ?? (typeof document !== "undefined" ? document : null);
  if (!doc) return () => {};

  const onClick = (event: Event) => {
    const start = event.target;
    if (!(start instanceof Element)) return;
    const el = start.closest(`[${WERNER_TARGET_ATTR}]`);
    if (!el) return;
    stage.waddleToEl(el, emoteFromAttr(el.getAttribute(WERNER_TARGET_ATTR)));
  };

  doc.addEventListener("click", onClick as EventListener, true);
  return () => {
    doc.removeEventListener("click", onClick as EventListener, true);
  };
}
