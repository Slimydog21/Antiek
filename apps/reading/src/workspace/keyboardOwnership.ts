/** Read-only diagnostics for the declared window/document keyboard population.
 * Element handlers, editor plugins and native browser keys are outside this model. */
export interface KeyboardRegistration {
  id: string;
  scope: "global-prefix" | "global-direct" | "overlay" | "observer";
  eligible: (event: KeyboardEvent) => boolean;
  capture?: boolean;
}

export interface OwnerTrace {
  sequence: number;
  key: string;
  code: string;
  context: string;
  trusted: boolean;
  eligible: string[];
  observers: string[];
  delivered: string[];
  actions: { row: string; action: string; handled: boolean }[];
}

const diagnostics = import.meta.env.DEV;
const registrations = new Map<number, KeyboardRegistration>();
const traces: OwnerTrace[] = [];
const eventTraces = new WeakMap<KeyboardEvent, OwnerTrace>();
let serial = 0;
let sequence = 0;

function observe(event: KeyboardEvent): void {
  const matching = [...registrations].filter(([, r]) => r.eligible(event));
  // Capture consumes an armed prefix before any bubble-phase owner can run.
  const prefix = matching.filter(([, r]) => r.scope === "global-prefix");
  const owners = prefix.length ? prefix : matching.filter(([, r]) => r.scope !== "observer");
  const target = event.target instanceof Element ? event.target : document.activeElement;
  const modal = target?.closest('[aria-modal="true"]');
  const context = modal ? `modal:${modal.getAttribute("aria-label") ?? modal.textContent?.slice(0, 60)}`
    : target?.matches('input,textarea,select,[contenteditable="true"]') ? "text" : "default";
  const trace: OwnerTrace = {
    sequence: ++sequence, key: matching.length ? event.key : "[unowned]", code: matching.length ? event.code : "", context, trusted: event.isTrusted,
    eligible: owners.map(([instance, r]) => `${r.id}#${instance}`),
    observers: matching.filter(([, r]) => r.scope === "observer").map(([, r]) => r.id),
    delivered: [], actions: [],
  };
  eventTraces.set(event, trace);
  traces.push(trace);
  if (traces.length > 512) traces.shift();
}

/** The only native global registration seam. Scoped callbacks receive only
 * declared eligible events. Prefix bookkeeping also observes scope exits so
 * an armed prefix can disarm without claiming a key from the new focus. */
export function registerKeyboardOwner(
  target: Window | Document,
  declaration: KeyboardRegistration,
  handler: (event: KeyboardEvent) => void,
): () => void {
  if (diagnostics && !registrations.size) window.addEventListener("keydown", observe, true);
  const instance = ++serial;
  registrations.set(instance, declaration);
  const listener = (event: KeyboardEvent) => {
    const eligible = declaration.eligible(event);
    if (eligible) eventTraces.get(event)?.delivered.push(`${declaration.id}#${instance}`);
    if (eligible || declaration.scope === "global-prefix") handler(event);
  };
  target.addEventListener("keydown", listener as EventListener, declaration.capture);
  return () => {
    target.removeEventListener("keydown", listener as EventListener, declaration.capture);
    registrations.delete(instance);
    if (diagnostics && !registrations.size) window.removeEventListener("keydown", observe, true);
  };
}

export function traceKeyboardAction(event: KeyboardEvent, row: string, action: string, handled: boolean): void {
  eventTraces.get(event)?.actions.push({ row, action, handled });
}

/** Copies only. Tests cannot register an owner or replace a handler through this API. */
export function readKeyboardOwnership() {
  return {
    registrations: [...registrations].map(([instance, r]) => ({ instance, id: r.id, scope: r.scope })),
    traces: traces.map((t) => ({ ...t, eligible: [...t.eligible], observers: [...t.observers],
      delivered: [...t.delivered], actions: t.actions.map((a) => ({ ...a })) })),
  };
}
