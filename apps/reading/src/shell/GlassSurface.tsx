import {
  forwardRef,
  type ElementType,
  type HTMLAttributes,
  type ReactNode,
} from "react";

import { usePrefersReducedMotion } from "../workspace/usePrefersReducedMotion";

/**
 * GlassSurface — the AMS-v2 landing-glass primitive (SPR-03, M2/M3/M4).
 *
 * ONE place that turns a landing surface translucent over the living
 * mountainscape `<Scene/>` (z-0) WITHOUT ever dropping body text below the
 * WCAG-AA 4.5:1 floor. Every landing surface in the occlusion audit
 * (docs/ams-v2/spr-03-occlusion-audit.md §3) is wrapped in this primitive so
 * the scrim math + the reduced-motion / no-scene degradation live in exactly
 * one file, not copy-pasted per route (taste: hard-to-vary).
 *
 * ── TOKENS ARE CONSUMED, NEVER REDEFINED (rigor #4) ──────────────────────────
 * The glass fill / hairline / blur come from SPR-09-owned tokens via their
 * Tailwind classes — `bg-glass` (var(--glass-bg)), `border-glass`
 * (var(--glass-border)), `backdrop-blur-glass` (12px) — and the opaque fallback
 * from `bg-glass-solid` (var(--glass-bg-solid)). This file defines NO colour
 * value; `lint:tokens` is the guard. tokens.css / tokens.ts are read-only here.
 *
 * ── THE SCRIM CONTRACT (M3 — the WCAG-AA guarantee) ──────────────────────────
 * tokens.css (L58-66) + tokens.ts `glass` are explicit: glass ALONE does not
 * guarantee 4.5:1 over a busy scene — a dark/bright frame behind the
 * translucent fill can erode contrast. The CONSUMER must add a scrim. This
 * primitive OWNS that scrim: the glass variant composites an extra
 * solid-fallback layer (`bg-glass-solid`) at SCRIM_MIN_OPACITY BEHIND the
 * content, so the effective text background is
 *
 *     glass-bg(alpha)  over  [ scrim-solid(SCRIM_MIN_OPACITY)  over  scene ]
 *
 * i.e. the worst the scene can do to the text background is bounded. Measured
 * worst case (proven in GlassSurface.test.tsx, the canonical token values):
 *
 *   day   --ink on glass over a BLACK scene        → 10.55:1 (floor 4.5) ✓
 *   night --ink(night)/bright on glass over WHITE  →  5.87:1 (floor 4.5) ✓
 *
 * Bare glass (no scrim) already clears the floor (day 9.1:1, night 4.66:1); the
 * scrim turns the tight night margin (0.16) into a defensible one (>1.3). The
 * solid fallback itself is far above the floor (day 18:1, night 14:1), as the
 * token contract promises — the scrim only recovers what scene-bleed costs.
 *
 * ── DEGRADATION (M4 / RULE 3 — every screen complete with no scene) ──────────
 * The glass variant renders the SOLID fallback (opaque `bg-glass-solid`, NO
 * backdrop-filter, no scrim layer needed) when EITHER:
 *   - the OS asks for `prefers-reduced-motion: reduce` (the scene is frozen /
 *     the motion budget is spent), OR
 *   - `sceneAbsent` is passed true (offline / no Krea key / over-budget — there
 *     is no moving scene behind to show through).
 * The fallback is IDENTICAL to `variant="solid"`, so the AA guarantee is the
 * same (and stronger — the solid hue clears the floor with no scene at all).
 * The primitive reads the media query itself; consumers only pass `sceneAbsent`
 * for the non-motion absence signals.
 */

export type GlassVariant = "glass" | "solid";

/**
 * The opacity of the scrim layer (solid fallback hue) the glass variant
 * composites behind its content. Chosen as the lightest scrim that lifts the
 * worst-case NIGHT contrast (bright text on glass over a white scene) from its
 * bare-glass margin of 4.66:1 to a defensible ≥5.5:1, while keeping the glass
 * visibly translucent (the scene still reads through the combined alpha). The
 * full derivation + worst-case ratios live in GlassSurface.test.tsx. This is
 * the SINGLE knob a maintainer raises if a future busier scene erodes contrast
 * — the audit (§5) points here.
 */
export const SCRIM_MIN_OPACITY = 0.2;

export interface GlassSurfaceProps extends HTMLAttributes<HTMLElement> {
  /**
   * "glass"  — translucent frost over the scene + the AA scrim (degrades to the
   *            solid fallback under reduced-motion / sceneAbsent).
   * "solid"  — the opaque-in-window / dense-content surface: `bg-glass-solid`
   *            (alpha 1, same hue, no colour jump, no backdrop-filter). Use for
   *            dense surfaces the audit classifies dense-legible-keep-opaque.
   * Default "glass".
   */
  variant?: GlassVariant;
  /** The element/component to render as. Default "div". */
  as?: ElementType;
  /**
   * True when there is no moving scene behind this surface (offline / no Krea
   * key / over-budget). Forces the glass variant to the solid fallback so the
   * screen stays complete + legible with nothing behind it. Default false.
   */
  sceneAbsent?: boolean;
  children?: ReactNode;
}

/**
 * Returns true when the glass variant must fall back to the opaque solid:
 * either the OS prefers reduced motion, or no scene is present.
 */
function useSolidFallback(sceneAbsent: boolean): boolean {
  const reduceMotion = usePrefersReducedMotion();
  return reduceMotion || sceneAbsent;
}

export const GlassSurface = forwardRef<HTMLElement, GlassSurfaceProps>(
  function GlassSurface(
    {
      variant = "glass",
      as,
      sceneAbsent = false,
      className = "",
      children,
      ...rest
    },
    ref,
  ) {
    const Component = (as ?? "div") as ElementType;
    const fallback = useSolidFallback(sceneAbsent);
    const renderSolid = variant === "solid" || fallback;

    if (renderSolid) {
      // SOLID — the opaque-in-window / degraded surface. Same hue at alpha 1
      // (`bg-glass-solid` == --glass-bg-solid), the translucent hairline (now
      // rendered over an opaque fill, so no colour jump), and NO backdrop-filter
      // dependency. Identical for variant="solid" and for the glass degradation,
      // so the AA guarantee is one thing.
      return (
        <Component
          ref={ref}
          data-glass-surface="solid"
          data-glass-variant={variant}
          className={["bg-glass-solid border border-glass", className]
            .filter(Boolean)
            .join(" ")}
          {...rest}
        >
          {children}
        </Component>
      );
    }

    // GLASS — translucent frost (`bg-glass` + `backdrop-blur-glass`) + the
    // hairline, PLUS the scrim. The surface owns `isolate` (its own stacking
    // context) and the translucent fill; the scrim + content live in an inner
    // `relative min-h-full` backing div.
    //
    // WHY THE INNER BACKING DIV (SPR-03 sharpen — below-the-fold scrim coverage)
    // -------------------------------------------------------------------------
    // Several landing surfaces put `overflow-y-auto` ON the GlassSurface itself
    // (Home, Speak, Library, Write home). If the scrim were `absolute inset-0`
    // directly on that scroll container, it would size to the CLIENT box, not
    // the scrollHeight — so text below the first viewport height would have only
    // the bare glass fill behind it (no scrim), silently eroding the AA margin
    // the scrim exists to provide (night 5.87:1 → 4.66:1) on exactly the long
    // pages most likely to scroll. The fix: the scrim is `absolute inset-0`
    // inside an inner `relative min-h-full` flow div. As a normal flow child of
    // the scroll container, that div's height tracks the full scroll CONTENT (and
    // `min-h-full` keeps it ≥ the client box when content is short), so the
    // scrim now covers every line, above and below the fold. `min-h-full` is a
    // no-op when the surface has indefinite height (non-scroll consumers like the
    // `/` column), so it never stretches a fixed-height layout. The fill on the
    // surface already covered the full content; this brings the scrim to parity.
    return (
      <Component
        ref={ref}
        data-glass-surface="glass"
        data-glass-variant="glass"
        className={[
          "relative isolate bg-glass backdrop-blur-glass border border-glass",
          className,
        ]
          .filter(Boolean)
          .join(" ")}
        {...rest}
      >
        <div
          data-glass-backing=""
          className="relative min-h-full rounded-[inherit]"
        >
          {/* The scrim layer — solid-fallback hue at SCRIM_MIN_OPACITY, behind
              the content. This is the WCAG-AA guarantee (see file header): it
              bounds how dark/bright the scene can make the text background. It is
              aria-hidden + pointer-events-none so it is purely presentational.
              `inset-0` here covers the backing div, which spans the full scroll
              content (see the WHY above), not just the visible client box. */}
          {/* `-z-10` is a LOCAL stack INSIDE this glass surface's own stacking
              context (`isolate` on the Component above) — it only puts the scrim
              BEHIND this surface's own content. It is NOT a shell-family z and is
              deliberately outside the zScale band system (which orders whole
              surfaces, not a surface's internal layers). */}
          <span
            aria-hidden="true"
            data-glass-scrim=""
            className="bg-glass-solid pointer-events-none absolute inset-0 -z-10 rounded-[inherit]"
            style={{ opacity: SCRIM_MIN_OPACITY }}
          />
          {children}
        </div>
      </Component>
    );
  },
);

export default GlassSurface;
