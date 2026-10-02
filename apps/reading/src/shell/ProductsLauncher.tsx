import { useEffect, useId, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { LemonModal } from "../components/lemon/LemonModal";
import { LemonTag } from "../components/lemon/LemonTag";
import { openWindow, windowKindForRoute } from "../components/windows/openWindow";
import { MAX_WINDOWS, useWindows } from "../workspace/windowsStore";
import { MODE_TAXONOMY, WORKFLOWS, WORKFLOW_ORDER, type ModeEntry, type Workflow } from "./workflowTaxonomy";

const BARE_ROUTES = new Set(MODE_TAXONOMY.flatMap((mode) => mode.route && !mode.route.includes(":") ? [mode.route] : []));
const RUN_LABELS: Record<string, string> = {
  OperatorDashboard: "Operator console", TrustCenter: "Trust & safety", PrivacyDashboard: "Privacy & deletion",
  Billing: "Billing & usage", Settings: "Settings", Coordination: "Coordination",
};
type Product = Exclude<Workflow, "shared">;
type LauncherItem =
  | { kind: "home"; id: string; label: string }
  | { kind: "product"; id: string; label: string; workflow: Product; matchesProduct: boolean }
  | { kind: "mode"; id: string; label: string; mode: ModeEntry; target: string | null };

// Keep the existing destination rules: shared details need a selected object;
// workflow detail entries without an index open their workflow's real door.
function modeDestination(mode: ModeEntry): string | null {
  if (!mode.built || !mode.route) return null;
  if (!mode.route.includes(":")) return mode.route;
  const index = mode.route.split("/:")[0];
  if (BARE_ROUTES.has(index)) return index;
  return mode.workflow === "shared" ? null : WORKFLOWS[mode.workflow].defaultRoute;
}
function operable(item: LauncherItem): boolean { return item.kind !== "mode" || item.target !== null; }
function inventory(query: string): LauncherItem[] {
  const matches = (text: string) => text.toLowerCase().includes(query);
  const modeMatches = (mode: ModeEntry) => [mode.label, mode.blurb, mode.id, RUN_LABELS[mode.id] ?? ""].some(matches);
  const items: LauncherItem[] = [{ kind: "home", id: "home", label: "Antiek home — what you can do, and where to start" }];
  const appendMode = (mode: ModeEntry) => items.push({
    kind: "mode", id: `mode:${mode.id}`, mode, target: modeDestination(mode),
    label: mode.workflow === "shared" ? RUN_LABELS[mode.id] ?? mode.label : mode.label,
  });
  for (const workflow of WORKFLOW_ORDER) {
    const product = WORKFLOWS[workflow];
    const matchesProduct = matches(product.label) || matches(product.tagline);
    const modes = MODE_TAXONOMY.filter((mode) => mode.workflow === workflow && (matchesProduct || modeMatches(mode)));
    if (!matchesProduct && modes.length === 0) continue;
    items.push({ kind: "product", id: `product:${workflow}`, workflow, label: product.label, matchesProduct });
    modes.forEach(appendMode);
  }
  MODE_TAXONOMY.filter((mode) => mode.workflow === "shared" && modeMatches(mode)).forEach(appendMode);
  return items;
}

export function ProductsLauncher({ open, onClose }: { open: boolean; onClose: () => void }) {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [activeId, setActiveId] = useState<string | null>(null);
  const [notice, setNotice] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const activeRowRef = useRef<HTMLButtonElement>(null);
  const descriptionId = useId();
  const normalizedQuery = query.trim().toLowerCase();
  const items = useMemo(() => inventory(normalizedQuery), [normalizedQuery]);
  const selectable = items.filter(operable);
  const defaultItem = normalizedQuery && !"antiek home".includes(normalizedQuery)
    ? selectable.find((item) => item.kind === "mode" || (item.kind === "product" && item.matchesProduct))
    : selectable[0];
  const activeItem = selectable.find((item) => item.id === activeId) ?? defaultItem;

  useEffect(() => {
    activeRowRef.current?.scrollIntoView?.({ block: "nearest" });
  }, [activeItem?.id]);

  useEffect(() => {
    if (!open) {
      setQuery("");
      setActiveId(null);
      setNotice("");
      return;
    }
    inputRef.current?.focus();
  }, [open]);

  const canEnterWindow = (requestedId: string, label: string) => {
    const current = useWindows.getState();
    if (!current.windows[requestedId] && current.order.length >= MAX_WINDOWS) {
      setNotice(`Window limit reached. Close a window before opening ${label}.`);
      return false;
    }
    return true;
  };
  const finishWindowEntry = (openedId: string, requestedId: string, label: string) => {
    if (openedId === requestedId) onClose();
    else setNotice(`Window limit reached. Close a window before opening ${label}.`);
  };
  const activate = (item: LauncherItem) => {
    if (!open) return;
    setNotice("");
    switch (item.kind) {
      case "home":
        navigate("/home");
        onClose();
        return;
      case "product": {
        const id = `win:subaction:${item.workflow}`;
        if (!canEnterWindow(id, item.label)) return;
        const openedId = openWindow("subaction", { workflow: item.workflow, __windowId: id }, { id, title: item.label });
        finishWindowEntry(openedId, id, item.label);
        return;
      }
      case "mode":
        if (!item.target) return;
        navigate(item.target);
        onClose();
        return;
      default: {
        const unreachable: never = item;
        return unreachable;
      }
    }
  };
  const openModeInWindow = (mode: ModeEntry) => {
    const kind = windowKindForRoute(mode.route);
    if (!open || !mode.built || !kind || !canEnterWindow(`win:${kind}`, mode.label)) return;
    finishWindowEntry(openWindow(kind), `win:${kind}`, mode.label);
  };
  const onSearchKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.defaultPrevented || event.nativeEvent.isComposing || event.ctrlKey || event.metaKey ||
        event.altKey || event.shiftKey || event.getModifierState("AltGraph")) return;
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      const delta = event.key === "ArrowDown" ? 1 : -1;
      setActiveId((current) => {
        const index = selectable.findIndex((item) => item.id === (current ?? activeItem?.id));
        return selectable[Math.max(0, Math.min(selectable.length - 1, index + delta))]?.id ?? null;
      });
    } else if (event.key === "Enter" && activeItem) {
      event.preventDefault();
      activate(activeItem);
    }
  };
  const firstRunId = items.find((item) => item.kind === "mode" && item.mode.workflow === "shared")?.id;
  return (
    <LemonModal open={open} onClose={onClose} title="More" size="md" footer={
      <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs font-mono text-shadow-1 dark:text-moonlight">
        <span>Arrows choose · Enter opens · Esc closes</span><span>Tab reaches buttons</span>
      </div>
    }>
      <div className="flex flex-col gap-2">
        <p className="text-xs text-shadow-1 dark:text-moonlight">Open a product window or go directly to a surface. Unavailable entries stay visible.</p>
        <input ref={inputRef} type="text" autoFocus aria-label="Filter products and surfaces" aria-describedby={descriptionId}
          value={query} onChange={(event) => { setQuery(event.target.value); setActiveId(null); setNotice(""); }}
          onKeyDown={onSearchKeyDown} placeholder="Filter…"
          className="w-full px-2 py-1.5 text-sm bg-ice-2 dark:bg-charcoal-1 border border-rule dark:border-charcoal-1 rounded-none text-ink dark:text-bright placeholder:text-ink-mute dark:placeholder:text-moonlight" />
        <p id={descriptionId} aria-live="polite" className="sr-only">
          {activeItem ? `Selected: ${activeItem.label}. Enter opens this entry.` : "No matching entry can be opened. Home remains available above the inventory."}
        </p>
        {notice && <p role="status" className="text-xs text-ink dark:text-bright">{notice}</p>}
        <ul aria-label="Products and surfaces" className="overflow-y-auto max-h-[55vh] space-y-0.5">
          {items.map((item) => {
            const active = item.id === activeItem?.id;
            const available = operable(item);
            const mode = item.kind === "mode" ? item.mode : null;
            const unavailableReason = mode && !mode.built ? "not yet" : "open from context";
            return (
              <li key={item.id}>
                {item.id === firstRunId && <h3 className="mt-3 px-2 py-1 font-mono text-xs uppercase tracking-wider text-shadow-1 dark:text-moonlight">Run & settings</h3>}
                <div className="flex items-center gap-1">
                  <button ref={active ? activeRowRef : undefined} type="button" disabled={!available}
                    data-testid={item.kind === "home" ? "launcher-home" : undefined}
                    data-product-window={item.kind === "product" ? item.workflow : undefined}
                    data-mode-id={mode?.id} data-launcher-active={active ? "true" : undefined} aria-current={active ? "true" : undefined}
                    aria-label={item.kind === "product" ? `Open ${item.label} workflow in a window` : undefined}
                    title={item.kind === "product" ? WORKFLOWS[item.workflow].tagline : mode?.blurb}
                    onFocus={() => setActiveId(item.id)} onClick={() => activate(item)}
                    className={"min-w-0 flex-1 text-left px-2 py-1.5 rounded-none border-l-2 flex items-center gap-2 " +
                      (item.kind === "product" ? "min-h-[58px] mt-2 font-mono text-xs uppercase tracking-wider " : "min-h-[50px] text-sm ") +
                      (active ? "border-sun bg-sun/10 dark:bg-sun/5 " : "border-transparent ") +
                      (available ? "text-ink dark:text-bright hover:bg-sun/20 dark:hover:bg-sun/10" : "text-ink-mute dark:text-moonlight opacity-70")}>
                    <span className={item.kind === "mode" && mode?.workflow !== "shared" ? "flex-1 min-w-0 pl-3" : "flex-1 min-w-0"}>{item.label}</span>
                    {item.kind === "product" && <span aria-hidden="true">⊞</span>}
                    {!available && <LemonTag colour="muted" className="shrink-0 text-xxs">{unavailableReason}</LemonTag>}
                  </button>
                  {mode?.built && windowKindForRoute(mode.route) && (
                    <button type="button" data-mode-window={mode.id} onClick={() => openModeInWindow(mode)}
                      title={`Open ${mode.label} in a floating window`} aria-label={`Open ${mode.label} in a window`}
                      className="shrink-0 px-1.5 py-1 rounded-none text-xs text-shadow-1 dark:text-moonlight hover:bg-sun/20 dark:hover:bg-sun/10">⊞</button>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
        {items.length === 1 && <p className="text-sm text-shadow-1 dark:text-moonlight">No surfaces match “{query}”.</p>}
      </div>
    </LemonModal>
  );
}
export default ProductsLauncher;
