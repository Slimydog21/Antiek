/**
 * Hotkey binding vocabulary — SPR-08.
 *
 * This module is the *framework-agnostic* half of the hotkey system: it
 * knows nothing about React or the DOM event listener. It owns:
 *
 *   1. The canonical, human-readable BUILT-IN binding table (the keys
 *      `shortcuts.ts` already implements). This is a DESCRIPTION of the
 *      built-ins, not a second implementation — `shortcuts.ts` stays the
 *      single place that *handles* them. The table exists so the HUD,
 *      the KeyChips, and the conflict detector can all reason about the
 *      same set of keys without re-parsing `shortcuts.ts`.
 *
 *   2. The PRODUCT binding table — the new product/sub-action hotkeys
 *      this sprint adds (G-chords for the four products + Home + More),
 *      each carrying the `ProductActivateDetail` it fires so a click and
 *      a hotkey emit the IDENTICAL activation event (the SPR-10 contract).
 *
 *   3. Key NORMALISATION + DISPLAY helpers shared by every consumer, so a
 *      binding written as `"g i"` displays as `G then I` everywhere and a
 *      custom binding the user types is canonicalised the same way.
 *
 *   4. CONFLICT detection against the built-ins and against other custom
 *      bindings, plus the list of browser/OS-reserved combos we refuse to
 *      bind (intellectual-honesty rule: never claim a key works that the
 *      browser eats).
 *
 * Why a separate file from `shortcuts.ts`: `shortcuts.ts` is the imperative
 * keydown handler mounted once at AppShell. Pulling the *data* (the tables)
 * and the *pure helpers* (normalise / format / conflict) out here keeps the
 * handler small, lets the React surfaces import the tables without importing
 * the listener, and makes the conflict logic unit-testable without a DOM.
 */

// ─────────────────────────────────────────────────────────────────────
// Shared activation contract (the thing SPR-10 consumes)
// ─────────────────────────────────────────────────────────────────────

/**
 * The single event a product activation fires — whether the operator
 * CLICKED the product or pressed its HOTKEY. SPR-10's penguin listens for
 * this one event and reacts identically to both. The invariant the whole
 * sprint defends: *there is exactly one activation path per product, and
 * both input methods go through it.*
 */
export const PRODUCT_ACTIVATE_EVENT = "antiek:product:activate" as const;

/** How the activation was triggered. SPR-10 may choreograph differently
 *  (e.g. a bigger flourish for a hotkey), but the EVENT is the same. */
export type ActivationSource = "click" | "hotkey";

/**
 * Payload of {@link PRODUCT_ACTIVATE_EVENT}. Carried on a `CustomEvent`'s
 * `detail`. `targetId` identifies *what* was activated:
 *   - a product:      productId = "research" | "read" | ... | "home" | "more"
 *   - a sub-action:   productId of the owning product + actionId
 *   - a custom entity binding: productId="custom", route + entityId set
 */
export interface ProductActivateDetail {
  /** Which product (or "home"/"more"/"custom") was activated. */
  productId: string;
  /** Sub-action within the product, when the activation is a sub-action. */
  actionId?: string;
  /** The route this activation navigates to (so a listener can mirror nav). */
  route?: string;
  /** For custom per-entity bindings: the bound entity id. */
  entityId?: string;
  /** How it was triggered — click vs hotkey. */
  source: ActivationSource;
}

/** Construct the activation CustomEvent. The ONE constructor both a click
 *  handler and the hotkey handler call, so the two can never drift. */
export function makeProductActivateEvent(
  detail: ProductActivateDetail,
): CustomEvent<ProductActivateDetail> {
  return new CustomEvent(PRODUCT_ACTIVATE_EVENT, { detail });
}

/** Fire a product activation on `window`. Click handlers and the hotkey
 *  handler both call this — the single emit point for the SPR-10 contract. */
export function emitProductActivate(detail: ProductActivateDetail): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(makeProductActivateEvent(detail));
}

// ─────────────────────────────────────────────────────────────────────
// Key normalisation + display
// ─────────────────────────────────────────────────────────────────────

/**
 * A binding's *spec* — the stable, serialisable string form.
 *
 * Two shapes:
 *   - chord:    "g r"  (space-separated keys, pressed in sequence)
 *   - combo:    "mod+k", "mod+shift+p"  ("+"-joined modifiers + key)
 *
 * `mod` means Cmd-on-macOS / Ctrl-elsewhere (matches `shortcuts.ts`'s
 * `isMod`). We normalise everything to lower-case canonical tokens so
 * `"Mod+K"`, `"mod + k"` and `"MOD+k"` all compare equal.
 */
export type BindingSpec = string;

/** Canonicalise a raw binding spec to its comparison form. */
export function normalizeBinding(raw: BindingSpec): BindingSpec {
  const trimmed = raw.trim().toLowerCase();
  if (trimmed.includes("+")) {
    // combo: sort modifiers into a stable order, key last.
    const parts = trimmed.split("+").map((p) => p.trim()).filter(Boolean);
    const order = ["mod", "ctrl", "alt", "shift", "meta"];
    const mods = parts
      .filter((p) => order.includes(p))
      .sort((a, b) => order.indexOf(a) - order.indexOf(b));
    const keys = parts.filter((p) => !order.includes(p));
    return [...mods, ...keys].join("+");
  }
  // chord: collapse internal whitespace.
  return trimmed.split(/\s+/).filter(Boolean).join(" ");
}

/** Is this spec a chord (sequence) rather than a single combo? */
export function isChord(spec: BindingSpec): boolean {
  const n = normalizeBinding(spec);
  return n.includes(" ") && !n.includes("+");
}

const KEY_GLYPHS: Record<string, string> = {
  mod: navigatorIsMac() ? "⌘" : "Ctrl",
  meta: "⌘",
  ctrl: "Ctrl",
  alt: navigatorIsMac() ? "⌥" : "Alt",
  shift: "⇧",
  "/": "/",
  "[": "[",
  "]": "]",
};

function navigatorIsMac(): boolean {
  if (typeof navigator === "undefined") return true; // SSR/test default: mac glyphs
  return /mac|iphone|ipad|ipod/i.test(navigator.platform || navigator.userAgent);
}

/** Human-display form for chips + the HUD, e.g. "g r" → "G then R",
 *  "mod+shift+p" → "⌘⇧P". Reduced-motion has no effect here (text only). */
export function formatBinding(spec: BindingSpec): string {
  const n = normalizeBinding(spec);
  if (isChord(n)) {
    return n
      .split(" ")
      .map((k) => glyphForToken(k))
      .join(" then ");
  }
  // combo
  return n
    .split("+")
    .map((k) => glyphForToken(k))
    .join("");
}

/** Short display forms for multi-char named keys, so "Enter" renders as
 *  "↵" and "ArrowUp" as "↑" instead of a shouty full-width word in a chip. */
const NAMED_KEY_GLYPHS: Record<string, string> = {
  enter: "↵",
  return: "↵",
  escape: "Esc",
  esc: "Esc",
  tab: "Tab",
  backspace: "⌫",
  delete: "Del",
  space: "Space",
  arrowup: "↑",
  arrowdown: "↓",
  arrowleft: "←",
  arrowright: "→",
};

function glyphForToken(token: string): string {
  if (KEY_GLYPHS[token]) return KEY_GLYPHS[token];
  if (token.length === 1) return token.toUpperCase();
  // Multi-char named key: prefer a short glyph/label over an all-caps word.
  return NAMED_KEY_GLYPHS[token] ?? token.charAt(0).toUpperCase() + token.slice(1);
}

/** ARIA-spoken form for `aria-keyshortcuts` / labels, e.g. "Control+K" or
 *  "G then R". We avoid glyphs here so a screen reader announces words. */
export function ariaBinding(spec: BindingSpec): string {
  const n = normalizeBinding(spec);
  const speak = (t: string) =>
    t === "mod"
      ? navigatorIsMac()
        ? "Meta"
        : "Control"
      : t === "shift"
        ? "Shift"
        : t === "alt"
          ? "Alt"
          : t === "ctrl"
            ? "Control"
            : t === "meta"
              ? "Meta"
              : t.toUpperCase();
  if (isChord(n)) return n.split(" ").map(speak).join(" then ");
  return n.split("+").map(speak).join("+");
}

// ─────────────────────────────────────────────────────────────────────
// Built-in binding table (DESCRIPTION of what shortcuts.ts implements)
// ─────────────────────────────────────────────────────────────────────

export interface BindingRow {
  /** Stable id for the action. */
  id: string;
  /** Canonical binding spec. */
  spec: BindingSpec;
  /** Operator-readable label. */
  label: string;
  /** Group heading in the HUD. */
  group: string;
  /** Built-in vs product vs custom — drives precedence + HUD sectioning. */
  kind: "builtin" | "product" | "subaction" | "custom";
  /** Optional product this row belongs to (for product/subaction rows). */
  productId?: string;
  /** Optional sub-action id. */
  actionId?: string;
  /** Route the binding navigates to, when applicable. */
  route?: string;
}

/**
 * The built-ins, mirroring `shortcuts.ts` exactly. Kept in sync by the
 * `bindings.test.ts` assertions that pin the count + the load-bearing keys.
 * NOTE on ⌘W: `shortcuts.ts` only intercepts ⌘W when a floating panel is
 * focused — otherwise it lets the browser's native "close tab" through.
 * The HUD says so (see label) rather than claiming a clean ⌘W binding.
 */
export const BUILTIN_BINDINGS: readonly BindingRow[] = [
  { id: "palette", spec: "mod+k", label: "Command palette", group: "Global", kind: "builtin" },
  { id: "palette-alt", spec: "mod+shift+p", label: "Command palette (alt)", group: "Global", kind: "builtin" },
  { id: "projecttree", spec: "mod+b", label: "Toggle project tree", group: "Panels", kind: "builtin" },
  { id: "aisidecar", spec: "mod+/", label: "Toggle AI sidecar", group: "Panels", kind: "builtin" },
  { id: "cycle-prev", spec: "mod+[", label: "Focus previous panel", group: "Panels", kind: "builtin" },
  { id: "cycle-next", spec: "mod+]", label: "Focus next panel", group: "Panels", kind: "builtin" },
  { id: "close-float", spec: "mod+w", label: "Close focused floating panel (only when one is focused — otherwise the browser closes the tab)", group: "Panels", kind: "builtin" },
  { id: "go-research", spec: "g i", label: "Go to my research", group: "Go to (chords)", kind: "builtin", route: "/my-research" },
  { id: "go-wrestle", spec: "g w", label: "Go to wrestle", group: "Go to (chords)", kind: "builtin", route: "/wrestle" },
  { id: "go-notebooks", spec: "g n", label: "Go to notebooks", group: "Go to (chords)", kind: "builtin", route: "/notebooks" },
  { id: "go-home", spec: "g r", label: "Go home (research)", group: "Go to (chords)", kind: "builtin", route: "/" },
  { id: "help", spec: "?", label: "Show keyboard shortcuts", group: "Global", kind: "builtin" },
];

// ─────────────────────────────────────────────────────────────────────
// Product + sub-action binding table (NEW this sprint)
// ─────────────────────────────────────────────────────────────────────

/**
 * Product/destination chords. We deliberately use the EXISTING `g`-chord
 * prefix (already wired in `shortcuts.ts`) rather than inventing a new
 * modifier, so the new bindings inherit the chord-window + isTextEditing
 * guard for free and don't collide with browser combos.
 *
 * Mapping rationale (and honesty about overlap):
 *   - `g r` already meant "go home (research)" → it IS the Research product
 *     activation. We REUSE it (one key, one meaning) and additionally have
 *     it fire the product-activate event. No new key, no conflict.
 *   - `g e` → Read   (R is taken by research/home; "rEad" → E)
 *   - `g t` → Write  (W is taken by wrestle; "wriTe" → T)
 *   - `g s` → Speak
 *   - `g h` → Home (the unified branded home at /home — the igloo door —
 *     a DISTINCT destination from Research at "/", not a duplicate alias)
 *   - `g m` → More (the launcher overflow). More OPENS the ProductsLauncher;
 *     it does not navigate, so this row carries NO route (the click + the
 *     hotkey both open the launcher and emit activate with productId "more").
 *
 * Each PRODUCT row that navigates carries its route + the activation detail;
 * the hotkey handler navigates AND fires `emitProductActivate`, so click ===
 * hotkey. The routeless More row only emits activate (no navigation), which
 * the More button's handler turns into "open the launcher".
 */
export const PRODUCT_BINDINGS: readonly BindingRow[] = [
  { id: "prod-research", spec: "g r", label: "Research", group: "Products", kind: "product", productId: "research", route: "/" },
  { id: "prod-read", spec: "g e", label: "Read", group: "Products", kind: "product", productId: "read", route: "/library" },
  { id: "prod-write", spec: "g t", label: "Write", group: "Products", kind: "product", productId: "write", route: "/write" },
  { id: "prod-speak", spec: "g s", label: "Speak", group: "Products", kind: "product", productId: "speak", route: "/speak" },
  { id: "prod-home", spec: "g h", label: "Home", group: "Products", kind: "product", productId: "home", route: "/home" },
  { id: "prod-more", spec: "g m", label: "More (all products)", group: "Products", kind: "product", productId: "more" },
];

/** A couple of representative sub-actions, wired the same way, to prove the
 *  sub-action path. (On-bar/launcher placement of these chips is SPR-11.) */
export const SUBACTION_BINDINGS: readonly BindingRow[] = [
  // "/" is the Research home — its landing surface IS where you start a
  // research (StartResearch serves it). Labelled for what the press does
  // (go to the Research home) rather than implying it resets a live session.
  { id: "sub-research-new", spec: "g c", label: "Research · go to the Research home", group: "Sub-actions", kind: "subaction", productId: "research", actionId: "new", route: "/" },
  { id: "sub-read-library", spec: "g l", label: "Read · open the library", group: "Sub-actions", kind: "subaction", productId: "read", actionId: "library", route: "/library" },
];

/** All non-custom rows, used for conflict checks + the HUD's fixed groups. */
export function fixedBindings(): BindingRow[] {
  return [...BUILTIN_BINDINGS, ...PRODUCT_BINDINGS, ...SUBACTION_BINDINGS];
}

/** Lookup a product/sub-action row by its activation target. */
export function bindingForProduct(
  productId: string,
  actionId?: string,
): BindingRow | undefined {
  const pool = actionId ? SUBACTION_BINDINGS : PRODUCT_BINDINGS;
  return pool.find(
    (b) => b.productId === productId && b.actionId === actionId,
  );
}

// ─────────────────────────────────────────────────────────────────────
// Browser / OS reserved combos — never bind these (honesty rule)
// ─────────────────────────────────────────────────────────────────────

/**
 * Combos the browser/OS intercepts before our handler can preventDefault
 * (or that are too destructive to shadow). We REFUSE to assign these as
 * custom bindings and surface the reason. Note we don't list `mod+w`
 * here even though the browser eats it: `shortcuts.ts` intentionally only
 * claims it when a floating panel is focused — documented, not silent.
 */
export const RESERVED_COMBOS: ReadonlyArray<{ spec: BindingSpec; reason: string }> = [
  { spec: "mod+n", reason: "Browser: opens a new window." },
  { spec: "mod+t", reason: "Browser: opens a new tab." },
  { spec: "mod+w", reason: "Browser: closes the tab (we only borrow it for a focused floating panel)." },
  { spec: "mod+q", reason: "OS: quits the application." },
  { spec: "mod+shift+w", reason: "Browser: closes the window." },
  { spec: "mod+r", reason: "Browser: reloads the page." },
  { spec: "mod+l", reason: "Browser: focuses the address bar." },
  { spec: "mod+shift+n", reason: "Browser: opens an incognito/private window." },
];

/** Is the given (normalised) spec a reserved browser/OS combo? */
export function reservedReason(spec: BindingSpec): string | null {
  const n = normalizeBinding(spec);
  const hit = RESERVED_COMBOS.find((r) => normalizeBinding(r.spec) === n);
  return hit ? hit.reason : null;
}

/**
 * SPR-08 sharpen — a CUSTOM binding must carry a modifier or be a chord.
 *
 * A bare single printable key (e.g. "j") is a footgun: the global keydown
 * handler's text-editing guard only suppresses input/textarea/select/
 * contenteditable, NOT a focused button/link/[role=button]/[tabindex]. So a
 * bare letter would hijack that key app-wide whenever any non-text control is
 * focused. Requiring a modifier (mod/alt/shift+key) or a chord shrinks the
 * blast radius to combos the browser hands us cleanly. Returns a reason string
 * when the spec is a bare single key, else null.
 */
export function requiresModifierReason(spec: BindingSpec): string | null {
  const n = normalizeBinding(spec);
  if (n.includes("+")) return null; // a combo carries a modifier
  if (n.includes(" ")) return null; // a chord (sequence) is fine
  if (n.length === 0) return null;
  return "A single key on its own would clash with the app's own keys. Add a modifier (⌘, ⌥, or ⇧) — for example ⌥J.";
}

// ─────────────────────────────────────────────────────────────────────
// Conflict detection
// ─────────────────────────────────────────────────────────────────────

export type ConflictKind = "builtin" | "product" | "subaction" | "custom" | "reserved";

export interface Conflict {
  kind: ConflictKind;
  /** The id of the colliding binding (or "" for reserved). */
  withId: string;
  /** Human explanation, shown in the assign-affordance warning. */
  message: string;
}

/**
 * Detect whether assigning `spec` for `selfId` collides with anything.
 *
 * Precedence rule (documented + tested):
 *   - A custom binding may NEVER override a built-in or a product/sub-action
 *     binding — those are foundational navigation. Attempting it is a
 *     *blocked* conflict (the assign affordance rejects it).
 *   - A custom binding that collides with ANOTHER custom binding is an
 *     *overridable* conflict: the affordance warns and, if the user
 *     confirms, the new binding wins (last-write-wins) and the old custom
 *     binding is dropped. This keeps the cost of customisation bounded: the
 *     user can always reach a consistent state without a dead key.
 *   - Reserved browser/OS combos are *blocked* (honesty rule).
 *
 * `existingCustom` is the list of already-bound custom specs (id + spec).
 */
export function detectConflict(
  spec: BindingSpec,
  existingCustom: ReadonlyArray<{ id: string; spec: BindingSpec }>,
  selfId?: string,
): Conflict | null {
  const n = normalizeBinding(spec);

  const reserved = reservedReason(n);
  if (reserved) {
    return { kind: "reserved", withId: "", message: reserved };
  }

  for (const b of fixedBindings()) {
    if (normalizeBinding(b.spec) === n) {
      return {
        kind: b.kind === "builtin" ? "builtin" : b.kind === "product" ? "product" : "subaction",
        withId: b.id,
        message: `"${formatBinding(n)}" is reserved for "${b.label}". Built-in and product hotkeys can't be overridden — pick another key.`,
      };
    }
  }

  for (const c of existingCustom) {
    if (c.id === selfId) continue;
    if (normalizeBinding(c.spec) === n) {
      return {
        kind: "custom",
        withId: c.id,
        message: `"${formatBinding(n)}" is already assigned to another item. Re-assigning will move it here.`,
      };
    }
  }

  return null;
}

/** True iff the conflict (if any) blocks assignment outright. A `custom`
 *  conflict is overridable; everything else blocks. */
export function isBlockingConflict(c: Conflict | null): boolean {
  return c != null && c.kind !== "custom";
}
