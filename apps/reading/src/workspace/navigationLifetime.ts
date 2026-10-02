import { UNSAFE_createBrowserHistory } from "react-router-dom";

export type NavigationHistory = ReturnType<typeof UNSAFE_createBrowserHistory>;
type RouterListener = Parameters<NavigationHistory["listen"]>[0];
const registryKey = Symbol.for("antiek.navigationLifetime.v1");
type NavigationLifetime = {
  ownerWindow: Window;
  history: NavigationHistory;
  epoch: number | null;
  subscribers: Set<() => void>;
  routerListeners: Set<RouterListener>;
};
// The live observer belongs to this realm, not a component/module evaluation.
// HMR reuses its history, counter and sole native listener without a gap.
const registry = globalThis as typeof globalThis & {
  [registryKey]?: { lifetime: NavigationLifetime | null; subscribers: Set<() => void> };
};
const shared = registry[registryKey] ??= { lifetime: null, subscribers: new Set<() => void>() };

function publishSubscribers(lifetime: NavigationLifetime): void {
  for (const listener of [...lifetime.subscribers]) {
    if (!lifetime.subscribers.has(listener)) continue;
    try { listener(); } catch { /* An admission observer cannot stop routing. */ }
  }
}

function advance(lifetime: NavigationLifetime): void {
  if (lifetime.epoch !== null) {
    lifetime.epoch = lifetime.epoch < Number.MAX_SAFE_INTEGER
      ? lifetime.epoch + 1 : null;
  }
  publishSubscribers(lifetime);
}

export function initializeNavigationHistory(ownerWindow: Window): NavigationHistory {
  const current = shared.lifetime;
  if (current) {
    if (current.ownerWindow !== ownerWindow) {
      throw new Error("Navigation observation is already bound to another Window.");
    }
    return current.history;
  }
  const inner = UNSAFE_createBrowserHistory({ window: ownerWindow, v5Compat: true });
  const subscribers = shared.subscribers;
  const routerListeners = new Set<RouterListener>();
  const history: NavigationHistory = {
    get action() { return inner.action; },
    get location() { return inner.location; },
    createHref: (to) => inner.createHref(to),
    createURL: (to) => inner.createURL(to),
    encodeLocation: (to) => inner.encodeLocation(to),
    push: (to, state) => inner.push(to, state),
    replace: (to, state) => inner.replace(to, state),
    go: (delta) => inner.go(delta),
    listen(listener) {
      const subscription: RouterListener = (update) => listener(update);
      routerListeners.add(subscription);
      return () => { routerListeners.delete(subscription); };
    },
  };
  const lifetime: NavigationLifetime = {
    ownerWindow, history, epoch: 0, subscribers, routerListeners,
  };
  // Keep the sole inner listener for the root lifetime. Facade subscription
  // cleanup (including StrictMode) never detaches this observer.
  inner.listen((update) => {
    advance(lifetime);
    for (const listener of [...routerListeners]) {
      if (!routerListeners.has(listener)) continue;
      try { listener(update); } catch { /* Other root subscribers still receive it. */ }
    }
  });
  shared.lifetime = lifetime;
  publishSubscribers(lifetime);
  return history;
}

/** Null refuses admission before bootstrap or after permanent exhaustion. */
export function readNavigationEpoch(): number | null {
  return shared.lifetime?.epoch ?? null;
}

export function subscribeNavigationLifetime(listener: () => void): () => void {
  const subscription = () => listener();
  shared.subscribers.add(subscription);
  return () => { shared.subscribers.delete(subscription); };
}

/** Preserve the existing raw replacement: no router state/action publication. */
export function replaceNavigationStateWithoutPublication(state: unknown, url: string): void {
  const lifetime = shared.lifetime;
  if (lifetime && lifetime.ownerWindow !== window) {
    throw new Error("Native replacement belongs to another Window.");
  }
  window.history.replaceState(state, "", url);
  // Legacy persistence callers before bootstrap retain their native behavior;
  // the read getter remains null until a real listener is attached.
  if (lifetime) advance(lifetime);
}
