import { useEffect, useState } from "react";

/**
 * useFloatMenuSelection — the shared, host-agnostic selection listener that
 * feeds the {@link FloatMenu}. Generalized DIRECTLY from the shipped
 * `ResearchWorkstation/HighlightToolbar.tsx` (commit pre-SPR-04): it listened
 * to `document`'s `selectionchange` (HighlightToolbar.tsx:38), narrowed to a
 * scope container (`scope.contains(range.commonAncestorContainer)`,
 * HighlightToolbar.tsx:52), read the selection's rect via
 * `range.getBoundingClientRect()` (HighlightToolbar.tsx:56), and dropped
 * sub-3-char / collapsed selections (HighlightToolbar.tsx:46,57). This hook
 * extracts that exact behavior so EVERY surface — Research synthesis, a DRW
 * block detail, later Read/Write/Speak — shares ONE selection path instead of
 * forking the toolbar four times.
 *
 * ════════════════════════════════════════════════════════════════════════
 * ANCHORING — raw selection rect, NOT the reading-physics layout-map (§ why)
 * ════════════════════════════════════════════════════════════════════════
 * A text selection is a TRANSIENT user input — a live caret drag that exists
 * only while the user holds it — NOT a semantic persistent anchor. So the
 * float-menu positions itself from the selection's RAW pixel rect
 * (`Range.getBoundingClientRect()`), the same read HighlightToolbar always
 * used. It deliberately does NOT route through the SPR-02 reading-physics
 * `layout-map` (`reading-physics/layout-map.ts`), which resolves SEMANTIC
 * chunk / claim / passage anchors that survive reflow and re-resolve by quote.
 * Those two are different jobs: the layout-map answers "where does claim c2
 * live, now and after an edit?"; the float-menu answers "where is the caret
 * the user is dragging RIGHT NOW?". Coupling the menu to the layout-map would
 * be wrong — it would try to give a persistent semantic identity to a thing
 * that is gone the instant the user clicks away. This hook therefore imports
 * NOTHING from `reading-physics/`. A maintainer tempted to "anchor it properly
 * via the physics" should read this paragraph first: the rawness is the
 * correct design, not a shortcut.
 *
 * The HOST owns the pixel read (this hook reads the DOM); {@link FloatMenu}
 * itself receives a plain rect prop and never touches the DOM/physics. That
 * keeps the menu testable with a literal rect and reusable on a non-DOM host.
 */

/** A minimal viewport-relative rect — exactly the fields the menu positions
 * from. A `DOMRect` satisfies this; tests pass a literal. */
export interface SelectionRect {
  top: number;
  left: number;
  width: number;
  height: number;
}

/** Provenance the host can attach to a selection so a NOTE chains
 * claim→chunk→document (§9). The host resolves these from whatever maps the
 * selected DOM range back to graph entities; the hook does not invent them.
 * `servable` is the §9.0 flag of the chunk the selection lands in — false ⇒
 * a withheld region, and the host must NOT let the body leave the client in a
 * SEARCH / DEEP-RESEARCH payload (the no-leak guard lives in FloatMenu). */
export interface SelectionProvenance {
  documentId?: string | null;
  chunkId?: string | null;
  /** §9.0 servability of the chunk the selection lands in. `undefined` ⇒ the
   * host could not resolve a chunk (e.g. a free-prose synthesis selection);
   * `true`/`false` ⇒ resolved-and-servable / resolved-and-withheld. */
  servable?: boolean;
  derivedRevisionId?: string | null;
  derivedContentSha256?: string | null;
  derivedGeneration?: number | null;
  derivedCitationId?: string | null;
  derivedChunkOrdinal?: number | null;
  derivedChunkTextSha256?: string | null;
}

/** What the host hands {@link FloatMenu}: the live selection's text + raw rect
 * + (optional) resolved provenance. */
export interface FloatMenuSelection {
  text: string;
  rect: SelectionRect;
  provenance: SelectionProvenance;
}

export interface UseFloatMenuSelectionOptions {
  /** The scope container; only selections entirely inside it open the menu
   * (HighlightToolbar's `scope.contains` narrowing). */
  scopeRef: React.RefObject<HTMLElement | null>;
  /** Host hook to resolve provenance for the current range. Optional — when
   * omitted the selection carries empty provenance (still works; the NOTE
   * simply has no chunk to chain to, recorded honestly as null). The host
   * reads its OWN DOM↔graph map here; the selection hook does not. */
  resolveProvenance?: (range: Range, text: string) => SelectionProvenance;
  /** Minimum selected length to open (HighlightToolbar used 3). */
  minLength?: number;
}

/**
 * Track the live text selection inside `scopeRef`. Returns the current
 * selection (text + raw rect + provenance) or null when there is none / it is
 * too short / it collapsed / it left the scope. The menu opens iff this is
 * non-null — so an empty/collapsed selection dismisses the menu cleanly
 * (rigor #3), with no separate teardown.
 */
export function useFloatMenuSelection({
  scopeRef,
  resolveProvenance,
  minLength = 3,
}: UseFloatMenuSelectionOptions): FloatMenuSelection | null {
  const [selection, setSelection] = useState<FloatMenuSelection | null>(null);

  useEffect(() => {
    function onSelectionChange() {
      const sel = window.getSelection();
      const scope = scopeRef.current;
      // Empty selection / no scope → dismiss (rigor #3: empty selection → no
      // window, no crash). Clear only if currently open to avoid render churn.
      if (!sel || sel.rangeCount === 0 || !scope) {
        setSelection((s) => (s ? null : s));
        return;
      }
      const text = sel.toString().trim();
      if (!text || text.length < minLength) {
        setSelection((s) => (s ? null : s));
        return;
      }
      const range = sel.getRangeAt(0);
      // Scope narrowing — only selections inside the host's scope open the
      // menu (HighlightToolbar.tsx:52). A selection elsewhere on the page is
      // not ours; dismiss.
      if (!scope.contains(range.commonAncestorContainer)) {
        setSelection((s) => (s ? null : s));
        return;
      }
      const r = range.getBoundingClientRect();
      // A collapsed selection has a zero-area rect — treat as dismissed
      // (rigor #3: selection collapses while menu open → dismiss).
      if (r.width === 0 && r.height === 0) {
        setSelection((s) => (s ? null : s));
        return;
      }
      const provenance = resolveProvenance
        ? resolveProvenance(range, text)
        : {};
      setSelection({
        text,
        rect: { top: r.top, left: r.left, width: r.width, height: r.height },
        provenance,
      });
    }
    document.addEventListener("selectionchange", onSelectionChange);
    return () =>
      document.removeEventListener("selectionchange", onSelectionChange);
  }, [scopeRef, resolveProvenance, minLength]);

  return selection;
}
