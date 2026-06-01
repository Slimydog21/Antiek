/**
 * Hotkey binding vocabulary — SPR-08 (command-scheme rebuild).
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
 *   2. The PRODUCT binding table — every product/sub-action hotkey this
 *      sprint gives a UNIFORM, single ⌘+key combo (one modifier, one
 *      keypress — NO vim chords), each carrying the `ProductActivateDetail`
 *      it fires so a click and a hotkey emit the IDENTICAL activation event
 *      (the click≡hotkey contract SPR-06's penguin depends on).
 *
 *   3. Key NORMALISATION + DISPLAY helpers shared by every consumer, so a
 *      combo written as `"Mod+E"` displays as `⌘E` everywhere and a custom
 *      binding the user types is canonicalised the same way.
 *
 *   4. CONFLICT detection against the built-ins and against other custom
 *      bindings, plus the list of browser/OS-reserved combos we refuse to
 *      bind (intellectual-honesty rule: never claim a key works that the
 *      browser eats), plus the SAFE_ASSIGNABLE policy (the bindable
 *      mod+<key> space + its derivation).
 *
 * ─────────────────────────────────────────────────────────────────────
 * WHY ⌘+key, NOT vim chords (fairness to the scheme we replaced)
 * ─────────────────────────────────────────────────────────────────────
 * The pre-SPR-08 scheme used vim-style g-chords (`g i` → my-research,
 * `g w` → wrestle, …). That had a real rationale: a leader key NAMESPACES
 * the keyboard so a 26-letter alphabet doesn't have to fit into 26 single
 * combos, and `g` (go) reads as a verb. We credit that.
 *
 * But for THIS single operator it is the wrong trade. A chord is a
 * two-keypress *sequence* gated on an 800 ms timing window — the operator
 * must (a) memorise the sequence and (b) hit the second key in time, or it
 * silently does nothing. There is no muscle-memory carry-over from any
 * other app (Linear/Notion/macOS all use single ⌘+key), the timing window
 * is a hidden failure mode, and the namespacing the leader bought is moot
 * at this scale (we have ~10 destinations, not hundreds). One modifier +
 * one keypress is learnable in one press, never times out, and matches the
 * rest of the desktop. So SPR-08 rips the chord machinery out entirely and
 * gives every product/sub-action/destination ONE ⌘+key.
 *
 * Why a separate file from `shortcuts.ts`: `shortcuts.ts` is the imperative
 * keydown handler mounted once at AppShell. Pulling the *data* (the tables)
 * and the *pure helpers* (normalise / format / conflict) out here keeps the
 * handler small, lets the React surfaces import the tables without importing
 * the listener, and makes the conflict logic unit-testable without a DOM.
 */

// ─────────────────────────────────────────────────────────────────────
// Shared activation contract (the thing the penguin / SPR-06 consumes)
// ─────────────────────────────────────────────────────────────────────

/**
 * The single event a product activation fires — whether the operator
 * CLICKED the product or pressed its HOTKEY. The penguin listens for this
 * one event and reacts identically to both. The invariant the whole sprint
 * defends: *there is exactly one activation path per product, and both
 * input methods go through it.*
 */
export const PRODUCT_ACTIVATE_EVENT = "antiek:product:activate" as const;

/** How the activation was triggered. A listener may choreograph differently
 *  (e.g. a bigger flourish for a hotkey), but the EVENT is the same. */
export type ActivationSource = "click" | "hotkey";

/**
 * Payload of {@link PRODUCT_ACTIVATE_EVENT}. Carried on a `CustomEvent`'s
 * `detail`. `productId` identifies *what* was activated:
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
 *  handler both call this — the single emit point for the parity contract. */
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
 * After SPR-08 every BUILT-IN / PRODUCT / SUB-ACTION / CUSTOM binding is a
 * COMBO: `"+"`-joined modifiers + a single key, e.g. `"mod+k"`, `"mod+e"`,
 * `"mod+shift+p"`. (`"?"` — the HUD toggle — is the one lone-key built-in,
 * intentionally so: it is the universal "help" key and carries no modifier.)
 *
 * The chord (space-separated *sequence*) shape is GONE from every binding
 * table; `normalizeBinding` still tolerates a stray space-form so a corrupt
 * persisted custom blob round-trips deterministically rather than throwing,
 * but `isChord` is used by the assign affordance to REJECT it on capture.
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
  // lone key / (tolerated) legacy chord: collapse internal whitespace.
  return trimmed.split(/\s+/).filter(Boolean).join(" ");
}

/**
 * Is this spec a CHORD (a space-separated key sequence) rather than a single
 * combo or lone key?
 *
 * Post-SPR-08 NO binding table row is a chord — this returns false for every
 * `fixedBindings()` row. It survives only so the assign affordance can REJECT
 * a chord the user might still type and so a corrupt legacy blob is detected.
 */
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
  ";": ";",
  ".": ".",
  ",": ",",
  "'": "'",
};

function navigatorIsMac(): boolean {
  if (typeof navigator === "undefined") return true; // SSR/test default: mac glyphs
  return /mac|iphone|ipad|ipod/i.test(navigator.platform || navigator.userAgent);
}

/** Human-display form for chips + the HUD, e.g. "mod+e" → "⌘E",
 *  "mod+shift+p" → "⌘⇧P". Reduced-motion has no effect here (text only). */
export function formatBinding(spec: BindingSpec): string {
  const n = normalizeBinding(spec);
  if (isChord(n)) {
    // Defensive: a legacy/corrupt chord still renders legibly rather than
    // throwing. No live binding produces this branch post-SPR-08.
    return n
      .split(" ")
      .map((k) => glyphForToken(k))
      .join(" then ");
  }
  // combo / lone key
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

/** ARIA-spoken form for `aria-keyshortcuts` / labels, e.g. "Meta+E" or
 *  "Meta+Shift+P". We avoid glyphs here so a screen reader announces words. */
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
 *
 * Every row here is a COMBO or the lone "?" — there is NO chord. `?` is the
 * one deliberate lone key (the universal help key; it carries no modifier so
 * it works on every layout without a chord).
 */
export const BUILTIN_BINDINGS: readonly BindingRow[] = [
  { id: "palette", spec: "mod+k", label: "Command palette", group: "Global", kind: "builtin" },
  { id: "palette-alt", spec: "mod+shift+p", label: "Command palette (alt)", group: "Global", kind: "builtin" },
  { id: "projecttree", spec: "mod+b", label: "Toggle project tree", group: "Panels", kind: "builtin" },
  { id: "aisidecar", spec: "mod+/", label: "Toggle AI sidecar", group: "Panels", kind: "builtin" },
  { id: "cycle-prev", spec: "mod+[", label: "Focus previous panel", group: "Panels", kind: "builtin" },
  { id: "cycle-next", spec: "mod+]", label: "Focus next panel", group: "Panels", kind: "builtin" },
  { id: "close-float", spec: "mod+w", label: "Close focused floating panel (only when one is focused — otherwise the browser closes the tab)", group: "Panels", kind: "builtin" },
  { id: "help", spec: "?", label: "Show keyboard shortcuts", group: "Global", kind: "builtin" },
];

// ─────────────────────────────────────────────────────────────────────
// Product + sub-action binding table — UNIFORM ⌘+key (NO chords)
// ─────────────────────────────────────────────────────────────────────

/**
 * Every product/destination gets ONE ⌘+key combo. One modifier, one
 * keypress, no sequence, no timing window. The letters are chosen from
 * {@link SAFE_ASSIGNABLE} (so the browser/OS does not eat them — see
 * RESERVED_COMBOS for the derivation) and are mnemonic where a free letter
 * allows it; honesty note where the obvious mnemonic was reserved:
 *
 *   - ⌘E → Read   ("rEad"; ⌘R is the browser reload — reserved).
 *   - ⌘J → Research (the research workstation / "/"; ⌘R reserved, so a free
 *           safe letter. J is the home destination too — Research IS the
 *           default landing surface at "/", so ⌘J doubles as "go home".)
 *   - ⌘Y → Write  ("⌘W closes the tab — reserved"; Y is a free safe letter).
 *   - ⌘U → Speak  ("⌘S is Save — reserved"; U is a free safe letter, and
 *           "Utter/spoken" is a loose mnemonic. The honest read: S/P/K are
 *           all reserved or built-in, so Speak takes a free safe letter.)
 *   - ⌘O → Home   (the unified branded home at /home — the igloo door — a
 *           DISTINCT destination from Research at "/", not a duplicate alias.
 *           ⌘H is macOS "Hide app" — reserved (see RESERVED_COMBOS); O is a
 *           free safe letter.)
 *   - ⌘I → More   (the launcher overflow / "Index of all products". The
 *           obvious mnemonic ⌘M was REJECTED: on macOS ⌘M is the window-server
 *           "minimize window" accelerator and ⌘H is "hide app" — both are now
 *           in RESERVED_COMBOS (same class as ⌘Q quit), so the safe range
 *           excludes them by derivation, not by a prose footnote. I is the
 *           remaining free safe letter and reads as "Index". More OPENS the
 *           ProductsLauncher; it does not navigate, so this row carries NO
 *           route (click + hotkey both open the launcher and emit activate
 *           with productId "more").
 *
 * Each PRODUCT row that navigates carries its route + the activation detail;
 * the hotkey handler navigates AND fires `emitProductActivate`, so click ===
 * hotkey. The routeless More row only emits activate (no navigation), which
 * the More button's handler turns into "open the launcher".
 */
export const PRODUCT_BINDINGS: readonly BindingRow[] = [
  { id: "prod-research", spec: "mod+j", label: "Research", group: "Products", kind: "product", productId: "research", route: "/" },
  { id: "prod-read", spec: "mod+e", label: "Read", group: "Products", kind: "product", productId: "read", route: "/library" },
  { id: "prod-write", spec: "mod+y", label: "Write", group: "Products", kind: "product", productId: "write", route: "/write" },
  { id: "prod-speak", spec: "mod+u", label: "Speak", group: "Products", kind: "product", productId: "speak", route: "/speak" },
  { id: "prod-home", spec: "mod+o", label: "Home", group: "Products", kind: "product", productId: "home", route: "/home" },
  { id: "prod-more", spec: "mod+i", label: "More (all products)", group: "Products", kind: "product", productId: "more" },
];

/** A couple of representative sub-actions, wired the same way, to prove the
 *  sub-action path also lives in the uniform ⌘+key world. (On-bar/launcher
 *  placement of these chips is SPR-07.) */
export const SUBACTION_BINDINGS: readonly BindingRow[] = [
  // "/" is the Research home — its landing surface IS where you start a
  // research (StartResearch serves it). Labelled for what the press does
  // (go to the Research home) rather than implying it resets a live session.
  // ⌘G ("Go") is the Find-Next browser combo but Chrome lets the page
  // intercept it; it is not in the hard-reserved set.
  { id: "sub-research-new", spec: "mod+g", label: "Research · go to the Research home", group: "Sub-actions", kind: "subaction", productId: "research", actionId: "new", route: "/" },
  // ⌘; (semicolon) — a free safe punctuation key, library is a Read sub-action.
  { id: "sub-read-library", spec: "mod+;", label: "Read · open the library", group: "Sub-actions", kind: "subaction", productId: "read", actionId: "library", route: "/library" },
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

/**
 * The map SPR-07 consumes: every product + sub-action as a `{ spec, label,
 * ariaLabel, productId, actionId, route }` entry, keyed by a stable id, so
 * the NavRail (and the launcher) can drop a `<KeyChip binding={spec} …/>`
 * next to each door WITHOUT importing the raw tables or knowing the combo
 * letters. Built-ins are excluded (they have no on-bar door). The shape is
 * intentionally flat + serialisable.
 */
export interface ChipBinding {
  /** Stable id (the BindingRow id). */
  id: string;
  /** Canonical ⌘+key spec, e.g. "mod+e". Feed straight to <KeyChip binding=…>. */
  spec: BindingSpec;
  /** Operator-readable label, e.g. "Read". */
  label: string;
  /** Pre-computed ARIA form (e.g. "Meta+E") for aria-keyshortcuts. */
  ariaLabel: string;
  /** Which product the chip belongs to. */
  productId: string;
  /** Sub-action id, when this is a sub-action chip. */
  actionId?: string;
  /** Route the press navigates to (undefined for routeless More). */
  route?: string;
}

/**
 * Returns the full product + sub-action chip map for SPR-07 to place on the
 * NavRail. One entry per product/sub-action; every `spec` is a single ⌘+key
 * combo (never a chord). SPR-07 iterates this and renders a `<KeyChip>` per
 * entry next to the matching door — the EXPOSE half of the SPR-07↔SPR-08
 * dependency.
 */
export function chipBindings(): ChipBinding[] {
  return [...PRODUCT_BINDINGS, ...SUBACTION_BINDINGS].map((b) => ({
    id: b.id,
    spec: b.spec,
    label: b.label,
    ariaLabel: ariaBinding(b.spec),
    productId: b.productId!,
    actionId: b.actionId,
    route: b.route,
  }));
}

// ─────────────────────────────────────────────────────────────────────
// Browser / OS reserved combos — never bind these (honesty rule)
// ─────────────────────────────────────────────────────────────────────

/**
 * Combos the browser/OS intercepts BEFORE our keydown handler can
 * `preventDefault` them (or that are too destructive/confusing to shadow).
 * We REFUSE to assign these as custom bindings and surface the reason, AND
 * we never put one in a built-in/product table. Each carries its derivation
 * (defensibility #5: a reader can check WHY each is off-limits).
 *
 * The hard truth about Chrome on macOS: a handful of ⌘+key combos are wired
 * into the browser/OS chrome and a web page CANNOT cancel them (⌘N/⌘T new
 * window/tab, ⌘W close tab, ⌘Q quit, plus the window-server accelerators
 * ⌘H hide-app and ⌘M minimize-window — whether Chrome even forwards a
 * cancelable keydown to the page for those is platform/config-dependent, so
 * we treat them as off-limits rather than gamble on the operator's setup).
 * Others (⌘S/⌘P/⌘F/⌘L/⌘R/⌘D) the page *can* technically cancel, but shadowing
 * them is a footgun — the operator's muscle memory expects Save/Print/Find/
 * address-bar/Reload/Bookmark, and a mis-fire there is jarring or data-losing.
 * We treat all three classes as reserved. Note we don't reserve `mod+w` away
 * from the built-in table
 * silently: `shortcuts.ts` intentionally only claims ⌘W when a floating
 * panel is focused, and the built-in row's label says so.
 */
export const RESERVED_COMBOS: ReadonlyArray<{ spec: BindingSpec; reason: string }> = [
  // ── Uncancellable browser/OS combos (the page literally cannot preventDefault) ──
  { spec: "mod+n", reason: "Browser: opens a new window (uncancellable)." },
  { spec: "mod+t", reason: "Browser: opens a new tab (uncancellable)." },
  { spec: "mod+w", reason: "Browser: closes the tab (we only borrow it for a focused floating panel)." },
  { spec: "mod+q", reason: "OS: quits the application (uncancellable)." },
  { spec: "mod+shift+w", reason: "Browser: closes the window." },
  { spec: "mod+shift+n", reason: "Browser: opens an incognito/private window." },
  { spec: "mod+shift+t", reason: "Browser: reopens the last closed tab." },
  // ── macOS window-server / app accelerators (same class as ⌘Q: the OS owns
  //    them; whether Chrome forwards a cancelable keydown to the page is
  //    platform/config-dependent, so we never bind them) ──
  { spec: "mod+h", reason: "macOS: hides the application (window-server accelerator)." },
  { spec: "mod+m", reason: "macOS: minimizes the window (window-server accelerator)." },
  // ── Cancellable but jarring/destructive to shadow (muscle-memory footguns) ──
  { spec: "mod+r", reason: "Browser: reloads the page." },
  { spec: "mod+l", reason: "Browser: focuses the address bar." },
  { spec: "mod+s", reason: "Browser: Save page — shadowing it risks losing the operator's expected Save." },
  { spec: "mod+p", reason: "Browser: Print." },
  { spec: "mod+f", reason: "Browser: in-page Find." },
  { spec: "mod+d", reason: "Browser: bookmark this page." },
  { spec: "mod+z", reason: "Editing: Undo — shadowing it loses an undo the operator expects." },
  { spec: "mod+a", reason: "Editing: Select all." },
  { spec: "mod+c", reason: "Editing: Copy." },
  { spec: "mod+v", reason: "Editing: Paste." },
  { spec: "mod+x", reason: "Editing: Cut." },
  // ── ⌘+digit switches tabs in Chrome (1–8 jump to tab N, 9 jumps to last) ──
  { spec: "mod+1", reason: "Browser: jumps to tab 1." },
  { spec: "mod+2", reason: "Browser: jumps to tab 2." },
  { spec: "mod+3", reason: "Browser: jumps to tab 3." },
  { spec: "mod+4", reason: "Browser: jumps to tab 4." },
  { spec: "mod+5", reason: "Browser: jumps to tab 5." },
  { spec: "mod+6", reason: "Browser: jumps to tab 6." },
  { spec: "mod+7", reason: "Browser: jumps to tab 7." },
  { spec: "mod+8", reason: "Browser: jumps to tab 8." },
  { spec: "mod+9", reason: "Browser: jumps to the last tab." },
  { spec: "mod+0", reason: "Browser: resets the page zoom." },
];

/**
 * The set of single keys that, combined with `mod` alone, are off-limits —
 * derived from {@link RESERVED_COMBOS}'s plain `mod+<key>` entries. Used by
 * {@link SAFE_ASSIGNABLE} to compute the bindable letters. (Combos with an
 * extra shift modifier, e.g. `mod+shift+w`, are reserved as full specs but
 * don't remove the single-mod letter from the safe range.)
 */
const RESERVED_MOD_KEYS: ReadonlySet<string> = new Set(
  RESERVED_COMBOS.map((r) => normalizeBinding(r.spec))
    .filter((s) => /^mod\+[^+]+$/.test(s))
    .map((s) => s.slice("mod+".length)),
);

/**
 * SAFE_ASSIGNABLE — the policy that names which `mod+<key>` combos a custom
 * binding may use, carrying its derivation (defensibility #5).
 *
 * THE RANGE. A safe assignable binding is `⌘ + <single key>` where:
 *   - exactly one modifier is present (`mod`, i.e. Cmd/Ctrl), OR a
 *     `mod+shift+<key>` extension — both are "one modifier-cluster + one
 *     keypress", never a sequence;
 *   - the key is a single character (`a`–`z`, or punctuation the layout
 *     yields directly: `;` `,` `.` `'` `/` `[` `]`);
 *   - the resulting combo is NOT in {@link RESERVED_COMBOS} and is NOT
 *     already owned by a built-in/product/sub-action ({@link detectConflict}
 *     enforces the "already owned" half live).
 *
 * THE POLICY. We deliberately:
 *   (1) require a modifier — a BARE single key is rejected (it would hijack
 *       that key app-wide whenever a non-text control is focused; the global
 *       handler's text-editing guard only spares input/textarea/select/
 *       contenteditable, not a focused button/link). See
 *       {@link requiresModifierReason}.
 *   (2) forbid a chord — a custom binding is ONE combo, never a `g x`
 *       sequence; the assign affordance rejects a captured chord ({@link isChord}).
 *   (3) exclude every reserved combo, so we never claim a key the browser
 *       eats (intellectual honesty).
 */
export const SAFE_ASSIGNABLE = {
  /** The required modifier for a product/built-in/custom combo. */
  modifier: "mod" as const,
  /** Punctuation keys the safe range permits in addition to a–z. */
  punctuation: [";", ",", ".", "'", "/", "[", "]"] as const,
  /**
   * The bindable single LETTERS for a plain `mod+<letter>` custom binding:
   * a–z minus the reserved letters (browser/OS owns those). Computed, not
   * hand-listed, so it can never drift from RESERVED_COMBOS.
   */
  letters: "abcdefghijklmnopqrstuvwxyz"
    .split("")
    .filter((c) => !RESERVED_MOD_KEYS.has(c)),
  /**
   * Is `spec` within the safe-assignable shape (single modifier-cluster +
   * one key, key not a bare lone key, not a chord)? This checks SHAPE only;
   * {@link detectConflict} checks ownership + reserved-ness. Both must pass
   * for an assign to succeed.
   */
  isWithinRange(spec: BindingSpec): boolean {
    const n = normalizeBinding(spec);
    if (n.includes(" ")) return false; // a chord is never in range
    if (!n.includes("+")) return false; // a bare lone key is never in range
    const parts = n.split("+");
    const key = parts[parts.length - 1];
    const mods = parts.slice(0, -1);
    if (mods.length === 0) return false;
    // Only mod / shift modifiers are part of the scheme (no alt-namespace,
    // no ctrl-on-mac); the keystone is `mod`. A lone-key + only-shift is not
    // safe (shift+letter is just a capital), so require `mod` to be present.
    if (!mods.every((m) => m === "mod" || m === "shift")) return false;
    if (!mods.includes("mod")) return false;
    return key.length >= 1;
  },
} as const;

/** Is the given (normalised) spec a reserved browser/OS combo? */
export function reservedReason(spec: BindingSpec): string | null {
  const n = normalizeBinding(spec);
  const hit = RESERVED_COMBOS.find((r) => normalizeBinding(r.spec) === n);
  return hit ? hit.reason : null;
}

/**
 * A CUSTOM binding must carry a modifier and must NOT be a chord.
 *
 * A bare single printable key (e.g. "j") is a footgun: the global keydown
 * handler's text-editing guard only suppresses input/textarea/select/
 * contenteditable, NOT a focused button/link/[role=button]/[tabindex]. So a
 * bare letter would hijack that key app-wide whenever any non-text control is
 * focused. A chord re-introduces the very sequence-timing machinery SPR-08
 * ripped out. Requiring a single `mod+<key>` (optionally + shift) shrinks the
 * blast radius to combos the browser hands us cleanly. Returns a reason string
 * when the spec is a bare single key OR a chord, else null.
 */
export function requiresModifierReason(spec: BindingSpec): string | null {
  const n = normalizeBinding(spec);
  if (n.length === 0) return null;
  if (isChord(n)) {
    return "Key sequences (press one key, then another) aren't supported — use a single ⌘ combo, for example ⌘J.";
  }
  if (n.includes("+")) return null; // a combo carries a modifier
  return "A single key on its own would clash with the app's own keys. Add a modifier (⌘, ⌥, or ⇧) — for example ⌘J.";
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
