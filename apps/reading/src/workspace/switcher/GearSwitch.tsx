/**
 * GearSwitch.tsx — SPR-04 M2: the geared switch's surface. LAZY chunk
 * (GearSwitchHost dynamic-imports it): it may name the contracts, the
 * feeder and the stores through gearActions.ts.
 *
 *   GearSwitchView     presentational (stories): a chip and, when `ui` is
 *                      set, the dialog with the current gear's tablist.
 *   GearSwitchContent  connected: derives the model from the SPR-06 tree
 *                      store + selection store; `surface="topbar"` mounts
 *                      the ONE <PreBackendTreeFeed /> line and owns the
 *                      dialog; `surface="zen"` is a click-only chip that
 *                      fires the same window toggle.
 *
 * Keys are element-level (the dialog's onKeyDown → the pure reducer);
 * Escape is ALSO declared as a window keyboard owner ("gear.escape",
 * scope overlay, eligible only while focus is inside) so the ownership
 * diagnostics see it. The dialog is aria-modal with
 * data-keymap-owner="gear.toggle": inside it the dispatcher fires only
 * the switch's own toggle, the prefix never arms, and no chord reaches a
 * pane or tab action (shortcuts.ts focusContext).
 *
 * Copy for an empty strip lives HERE, never in the model: a pre-backend
 * gear 2 never asserts absence (F2: the feeder publishes `ready` with
 * zero investigations while the first fetch is in flight).
 */
import {
  useCallback,
  useEffect,
  useId,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type ReactNode,
} from "react";

import { durationMs, notch, press } from "../../design/motion";
import { prefersReducedMotion } from "../../design/theme";
import { useContextTree, useIsSelected, useSelection } from "../contracts";
import { PreBackendTreeFeed } from "../contracts/adapters/preBackend";
import { registerKeyboardOwner } from "../keyboardOwnership";
import { runGearEffect } from "./gearActions";
import { normalizeUi, openUi, stepSwitcher, type GearEffect, type SwitcherInput, type SwitcherKey, type SwitcherUi } from "./switcherKeys";
import { deriveSwitcher, type EmptyReason, type Gear, type GearStrip, type GearTab, type SwitcherModel } from "./switcherModel";

// ---------------------------------------------------------------------------
// Copy (consumer-side; the model only names reasons)
// ---------------------------------------------------------------------------

/** The chip's and the strips' words for a status that is not ready. */
export function statusCopy(model: SwitcherModel): string | null {
  switch (model.status) {
    case "unfed": return "Projects not loaded";
    case "loading": return "Loading projects";
    case "error": return model.error ?? "Projects failed to load";
    case "stale": return "Project not in the list";
    default: return null;
  }
}

export function emptyCopy(reason: EmptyReason, model: SwitcherModel): string {
  const title = model.path[0]?.label ?? "this project";
  switch (reason) {
    case "no-children": return `No sub-projects under ${title}.`;
    case "not-linked": return "Investigations aren't linked to projects yet; they're listed under the Default project.";
    case "none-listed": return "No investigations listed yet.";
    case "no-agents": return "No agents open here.";
    case "unfed": return "Projects not loaded";
    case "loading": return "Loading projects";
    case "error": return model.error ?? "Projects failed to load";
    case "stale-project": return "Project not in the list";
  }
}

export function domId(key: GearTab["key"]): string {
  const i = key.indexOf(":");
  return `gear-tab-${key.slice(0, i)}-${key.slice(i + 1)}`;
}

// ---------------------------------------------------------------------------
// Presentational pieces
// ---------------------------------------------------------------------------

const MUTED = "text-shadow-1 dark:text-moonlight";
const CHIP =
  press +
  " shadow-z2 dark:shadow-z2-night inline-flex max-w-[40vw] items-center gap-1.5 rounded-hog " +
  "border border-ink dark:border-bright bg-ice-1 dark:bg-charcoal-1 px-2 py-0.5 font-mono text-xs " +
  "text-ink dark:text-bright whitespace-nowrap overflow-hidden focus-visible:outline focus-visible:outline-2 focus-visible:outline-sun";
const TAB =
  press +
  " shadow-z1 dark:shadow-z1-night rounded-hog border border-ink dark:border-bright bg-ice-0 dark:bg-charcoal-2 " +
  "px-2 py-1 text-sm text-ink dark:text-bright max-w-[16rem] truncate " +
  "aria-selected:bg-sun aria-selected:text-ink focus-visible:outline focus-visible:outline-2 focus-visible:outline-sun";
const DIALOG =
  notch +
  " absolute left-0 top-[calc(100%+6px)] z-50 min-w-[20rem] max-w-[min(90vw,42rem)] p-3 " +
  "bg-ice-0 dark:bg-charcoal-2 text-ink dark:text-bright border-edge border-sun rounded-hog-lg " +
  "shadow-z2 dark:shadow-z2-night outline-none";

export interface GearChipProps {
  model: SwitcherModel;
  /** Undefined on a chip that does not own the dialog (the zen chip). */
  open?: boolean;
  dialogId?: string;
  onClick?: () => void;
}

export function GearChip({ model, open, dialogId, onClick }: GearChipProps) {
  const status = statusCopy(model);
  return (
    <button
      type="button"
      aria-haspopup="dialog"
      aria-expanded={open === undefined ? undefined : open}
      aria-controls={open && dialogId ? dialogId : undefined}
      aria-label={status ? `Switch gear: ${status}` : "Switch gear"}
      data-gear-chip=""
      className={CHIP}
      onClick={onClick}
    >
      {status ?? (model.path.length === 0 ? "Switch gear" : model.path.map((t, i) => (
        <span key={t.key} className="inline-flex min-w-0 items-center gap-1">
          {i > 0 && <span aria-hidden="true" className={MUTED}>·</span>}
          <span className={`text-xxs uppercase tracking-wider ${MUTED}`}>{t.kindLabel}</span>
          <span className="truncate">{t.label}</span>
        </span>
      )))}
    </button>
  );
}

interface RowProps {
  tab: GearTab;
  selected: boolean;
  cursor: boolean;
  onClick?: () => void;
}

function TabButton({ tab, selected, cursor, onClick }: RowProps) {
  return (
    <button
      type="button"
      role="tab"
      id={domId(tab.key)}
      data-gear-tab={tab.key}
      data-cross={tab.agent?.scope === "cross-project" ? "true" : undefined}
      aria-selected={selected}
      tabIndex={cursor ? 0 : -1}
      title={tab.kindLabel}
      className={TAB}
      onClick={onClick}
    >
      {tab.label}
    </button>
  );
}

/** A gear-1 or agent row reads the contract's row selector, so it
 *  re-renders only when its own answer flips. Never a sub-project row:
 *  `useIsSelected(id, "subproject")` matches only the DEEPEST node
 *  (selection.ts:159-166), and the strip pins gear 2 at depth 1. */
function LiveRow(props: Omit<RowProps, "selected">) {
  const selected = useIsSelected(props.tab.id, props.tab.role);
  return <TabButton {...props} selected={selected} />;
}

export interface GearDialogViewProps {
  model: SwitcherModel;
  ui: SwitcherUi;
  dialogId: string;
  notchOn?: boolean;
  /** Rows read the selection store (the connected surface) or the model (stories). */
  live?: boolean;
  dialogRef?: React.Ref<HTMLDivElement>;
  onKeyDown?: (e: ReactKeyboardEvent<HTMLDivElement>) => void;
  onBackdrop?: () => void;
  onTabClick?: (key: GearTab["key"]) => void;
}

export function GearDialogView({ model, ui, dialogId, notchOn, live, dialogRef, onKeyDown, onBackdrop, onTabClick }: GearDialogViewProps) {
  const strip: GearStrip = model.strips[ui.gear - 1];
  const status = statusCopy(model);
  const rows: ReactNode[] = [];
  strip.tabs.forEach((tab, i) => {
    if (strip.crossProjectFrom !== null && i === strip.crossProjectFrom) {
      rows.push(
        <span key="divider" aria-hidden="true" role="presentation" className={`basis-full pt-1 font-mono text-xxs uppercase tracking-wider ${MUTED}`}>
          Across projects
        </span>,
      );
    }
    const cursor = tab.key === ui.cursor;
    const onClick = onTabClick ? () => onTabClick(tab.key) : undefined;
    // Gear-2 rows light from the model (depth 1 on the path); gear-3 node
    // rows never light (drill targets); project and agent rows read the
    // contract's row selector when connected.
    const selected = ui.gear === 2 ? tab.selected : tab.role === "subproject" ? false : tab.selected;
    rows.push(
      live && tab.role !== "subproject"
        ? <LiveRow key={tab.key} tab={tab} cursor={cursor} onClick={onClick} />
        : <TabButton key={tab.key} tab={tab} selected={selected} cursor={cursor} onClick={onClick} />,
    );
  });
  return (
    <>
      <div data-gear-backdrop="" aria-hidden="true" className="fixed inset-0 z-50" onMouseDown={onBackdrop} />
      <div
        ref={dialogRef}
        id={dialogId}
        role="dialog"
        aria-modal="true"
        aria-label="Switch gear"
        data-keymap-owner="gear.toggle"
        data-gear-switch=""
        data-gear={ui.gear}
        data-notch={notchOn ? "true" : undefined}
        tabIndex={-1}
        className={DIALOG}
        onKeyDown={onKeyDown}
      >
        <div className={`mb-2 font-mono text-xxs uppercase tracking-wider ${MUTED}`}>
          Gear {ui.gear} of 3 · {strip.heading}
          {status !== null && <span className="normal-case tracking-normal"> · {status}</span>}
        </div>
        <div role="tablist" aria-level={ui.gear} aria-orientation="horizontal" aria-label={strip.heading} className="flex flex-wrap items-center gap-2">
          {rows}
        </div>
        {strip.empty !== null && (
          <p className={`mt-1 text-xs ${MUTED}`}>{emptyCopy(strip.empty, model)}</p>
        )}
        <p className={`mt-3 font-mono text-xxs ${MUTED}`} aria-hidden="true">
          ← → hop · Enter clicks in · Backspace clicks back · Esc closes
        </p>
      </div>
    </>
  );
}

export interface GearSwitchViewProps {
  model: SwitcherModel;
  /** null = closed. */
  ui: SwitcherUi | null;
  notchOn?: boolean;
  surface?: "topbar" | "zen";
}

/** Static composition for stories and visual baselines. */
export function GearSwitchView({ model, ui, notchOn, surface = "topbar" }: GearSwitchViewProps) {
  const dialogId = useId();
  return (
    <div className="relative inline-block" data-gear-host={surface}>
      <GearChip model={model} open={surface === "topbar" ? ui !== null : undefined} dialogId={dialogId} />
      {ui && <GearDialogView model={model} ui={ui} dialogId={dialogId} notchOn={notchOn} />}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Connected
// ---------------------------------------------------------------------------

function useSwitcherModel(): SwitcherModel {
  const tree = useContextTree();
  const selection = useSelection((s) => s.selection);
  return useMemo(() => deriveSwitcher(tree, selection), [tree, selection]);
}

const SWITCHER_KEYS: ReadonlySet<string> = new Set<SwitcherKey>(["ArrowLeft", "ArrowRight", "Home", "End", "Enter", "Backspace", "Escape", "h", "l"]);
const FOCUSABLE = 'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

interface GearDialogProps {
  model: SwitcherModel;
  dialogId: string;
  onClose: () => void;
}

/** Mounted only while open: its state, timer, owner and opener focus live
 *  and die with it. */
function GearDialog({ model, dialogId, onClose }: GearDialogProps) {
  const [ui, setUi] = useState<SwitcherUi>(() => openUi(model));
  const liveUi = normalizeUi(model, ui);
  const [notchOn, setNotchOn] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const timer = useRef<number | null>(null);
  const tree = useContextTree();
  const treeRef = useRef(tree);
  treeRef.current = tree;
  const modelRef = useRef(model);
  modelRef.current = model;
  const uiRef = useRef(liveUi);
  uiRef.current = liveUi;
  const closeRef = useRef(onClose);
  closeRef.current = onClose;

  // Focus returns to whatever had it when the switch opened.
  useLayoutEffect(() => {
    const opener = document.activeElement;
    return () => {
      if (opener instanceof HTMLElement && opener.isConnected) opener.focus();
    };
  }, []);

  // The cursor tab (or the dialog itself over an empty strip) holds focus
  // on open and on every ui change.
  useLayoutEffect(() => {
    const root = ref.current;
    if (!root) return;
    const target = liveUi.cursor === null
      ? root
      : [...root.querySelectorAll<HTMLElement>("[data-gear-tab]")].find((el) => el.dataset.gearTab === liveUi.cursor) ?? root;
    if (document.activeElement !== target) target.focus();
  }, [liveUi.cursor, liveUi.gear]);

  const bump = useCallback(() => {
    if (prefersReducedMotion()) return;
    if (timer.current !== null) window.clearTimeout(timer.current);
    setNotchOn(true);
    timer.current = window.setTimeout(() => {
      timer.current = null;
      setNotchOn(false);
    }, durationMs.fast);
  }, []);
  useEffect(() => () => {
    if (timer.current !== null) window.clearTimeout(timer.current);
  }, []);

  const runEffect = useCallback((effect: GearEffect) => {
    switch (effect.type) {
      case "close":
        closeRef.current();
        return;
      case "notch":
        return;
      case "select-agent": {
        // Close first (the opener gets focus back on unmount), then run on
        // the next microtask (reviewer 2 graft 2).
        closeRef.current();
        const tree = treeRef.current;
        void Promise.resolve().then(() => runGearEffect(effect, tree));
        return;
      }
      default:
        // Gear 1 and 2 keep the dialog open and focus inside it.
        void runGearEffect(effect, treeRef.current);
    }
  }, []);

  const dispatch = useCallback((input: SwitcherInput) => {
    const before = uiRef.current;
    const { ui: next, effect } = stepSwitcher(modelRef.current, before, input);
    if (next !== before || effect !== null) bump();
    if (next !== before) {
      uiRef.current = next;
      setUi(next);
    }
    if (effect) runEffect(effect);
  }, [bump, runEffect]);

  // A project asked for at gear 1 arrives through the selection mirror
  // (the picker's choose → tabTreeStore → useSelection).
  const projectId = useSelection((s) => s.selection.projectId);
  const seenProject = useRef(projectId);
  useEffect(() => {
    if (seenProject.current === projectId) return;
    seenProject.current = projectId;
    dispatch({ type: "project-arrived", id: projectId });
  }, [projectId, dispatch]);

  // Escape as a declared window owner (diagnostics + a key dispatched at
  // the window while focus is inside); the element handler below takes
  // the ordinary case first and marks it defaultPrevented.
  useEffect(() => registerKeyboardOwner(window, {
    id: "gear.escape",
    scope: "overlay",
    eligible: (e) => e.key === "Escape" && !e.defaultPrevented && !!ref.current?.contains(document.activeElement),
  }, (e) => {
    e.preventDefault();
    dispatch("Escape");
  }), [dispatch]);

  const onKeyDown = (e: ReactKeyboardEvent<HTMLDivElement>) => {
    if (e.ctrlKey || e.metaKey || e.altKey) return; // chords are the dispatcher's (only the switch's own toggle fires)
    if (e.key === "Tab") {
      // LemonModal's trap, element-level: Tab never leaves the dialog.
      const root = ref.current;
      if (!root) return;
      const items = [...root.querySelectorAll<HTMLElement>(FOCUSABLE)].filter((el) => el.tabIndex >= 0);
      e.preventDefault();
      if (items.length === 0) { root.focus(); return; }
      const at = items.indexOf(document.activeElement as HTMLElement);
      const next = e.shiftKey ? (at <= 0 ? items.length - 1 : at - 1) : (at === -1 || at === items.length - 1 ? 0 : at + 1);
      items[next].focus();
      return;
    }
    if (e.shiftKey && e.key.length === 1) return;
    if (!SWITCHER_KEYS.has(e.key)) return;
    e.preventDefault();
    dispatch(e.key as SwitcherKey);
  };

  return (
    <GearDialogView
      model={model}
      ui={liveUi}
      dialogId={dialogId}
      notchOn={notchOn}
      live
      dialogRef={ref}
      onKeyDown={onKeyDown}
      onBackdrop={() => dispatch("Escape")}
      onTabClick={(key) => dispatch({ type: "click", key })}
    />
  );
}

export interface GearSwitchContentProps {
  surface: "topbar" | "zen";
  /** Topbar only: the host owns open/close (it is the one toggle listener). */
  open?: boolean;
  /** Fires the window toggle (toggleGearSwitch); both chips share it. */
  onToggle: () => void;
  onClose?: () => void;
}

function TopbarSwitch({ open, onToggle, onClose }: Omit<GearSwitchContentProps, "surface">) {
  const model = useSwitcherModel();
  const dialogId = useId();
  return (
    <div className="relative inline-block" data-gear-host="topbar">
      <PreBackendTreeFeed />
      <GearChip model={model} open={open === true} dialogId={dialogId} onClick={onToggle} />
      {open && <GearDialog model={model} dialogId={dialogId} onClose={onClose ?? onToggle} />}
    </div>
  );
}

function ZenChip({ onToggle }: Pick<GearSwitchContentProps, "onToggle">) {
  const model = useSwitcherModel();
  return (
    <div className="relative inline-block" data-gear-host="zen">
      <GearChip model={model} onClick={onToggle} />
    </div>
  );
}

export function GearSwitchContent(props: GearSwitchContentProps) {
  if (props.surface === "zen") return <ZenChip onToggle={props.onToggle} />;
  return <TopbarSwitch open={props.open} onToggle={props.onToggle} onClose={props.onClose} />;
}

export default GearSwitchContent;

export type { Gear };
