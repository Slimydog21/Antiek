import type { useTabTrees } from "./tabTreeStore";

/**
 * The tab-tree store, once its module has loaded. The store and the model
 * ship with the lazy document strip, not the entry chunk; the keyboard
 * dispatcher (entry chunk) reaches them through this handle, which
 * tabTreeStore fills when it evaluates. Before then no tree can be loaded,
 * so a tab key finding the handle empty is the same honest no-op as a key
 * finding the tree not yet loaded, and it stays synchronous.
 */
export const tabTreeHandle: { store: typeof useTabTrees | null } = { store: null };
