import { useContext } from "react";

import { AuthCtx } from "../lib/auth";

/**
 * SceneStatusBadge — the OPERATOR-ONLY fallback voice for the living scene
 * (antiek-living-caliber SPR-04, milestone 5).
 *
 * WHY THIS EXISTS. The Krea proxy collapses every failure into a typed 503 +
 * a deterministic procedural placeholder, so the background degrades
 * SEAMLESSLY — which is exactly why the product could serve fallback art
 * forever with ZERO signal. This badge gives that degradation a quiet voice
 * for the OPERATOR (and only the operator): when art is falling back, it
 * names the reason (e.g. "scene: procedural · no_api_balance") so the
 * operator notices "the live art is off" without staring at logs.
 *
 * THE RULE (diligence #7 — auth IS the operator signal; single-operator
 * product, no dedicated operator hook):
 *   operator + fallback     ⇒ render the badge with the reason text
 *   operator + live         ⇒ render NOTHING (no badge when art is live)
 *   NON-operator + fallback ⇒ render NOTHING — ABSENT FROM THE DOM, not
 *                             CSS-hidden (a logged-out reader must never see
 *                             internal degradation reasons)
 *
 * "Operator" = an AUTHENTICATED auth state. We read auth via the OPTIONAL
 * context (`useContext(AuthCtx)`) rather than the throwing `useAuth`, so this
 * presentational component renders safely even when mounted with NO
 * <AuthProvider> above it (the scene layers are rendered standalone in
 * tests). No provider / loading / unauthenticated all ⇒ non-operator ⇒ the
 * badge is absent.
 *
 * NO NEW NETWORK. The badge consumes ONLY the existing scene-hook state
 * (isFallback + reason threaded from useSceneArt → KreaArtLayer). It never
 * calls /krea/status or any endpoint — that operator surface is a separate,
 * pull-when-you-want diagnostic; this badge is the always-on glance.
 *
 * QUIET + STATIC + TOKEN-STYLED. It reuses design tokens (glass surface,
 * ink text, mono type, the standard radius) so it reads as native chrome,
 * sits bottom-LEFT (Werner lives on the rail; the shell controls are
 * top/right) so it never overlaps them, and has no animation. It is
 * pointer-events:none — purely informational, consistent with the scene
 * being non-interactive.
 */

export interface SceneStatusBadgeProps {
  /** True ⇒ the scene is on the procedural fallback (no live Krea art). */
  isFallback: boolean;
  /** The honest fallback reason from the hook (e.g. "no_key",
   *  "over_daily_budget"); null when live or unknown. */
  reason: string | null;
}

export function SceneStatusBadge({ isFallback, reason }: SceneStatusBadgeProps) {
  // Optional auth read — null context (no provider) is treated as
  // non-operator. NEVER throws (unlike useAuth).
  const auth = useContext(AuthCtx);
  const isOperator = auth?.state.status === "authenticated";

  // Non-operator OR live art ⇒ the badge is ABSENT from the DOM (returning
  // null renders nothing — not a hidden node). This is the whole privacy
  // contract: a reader never sees internal reasons.
  if (!isOperator || !isFallback) return null;

  const label = reason
    ? `scene: procedural · ${reason}`
    : "scene: procedural";

  return (
    <div
      data-testid="scene-status-badge"
      data-reason={reason ?? ""}
      aria-hidden="true"
      style={{
        position: "absolute",
        left: "12px",
        bottom: "12px",
        // Token-styled glass chip — native chrome, not a loud overlay.
        // Token-ONLY: tokens.css is imported app-wide so these vars are always
        // defined; the prior literal var() fallbacks were dead code and tripped
        // token-lint. Dropped for token discipline (ALC SPR-05).
        padding: "2px 8px",
        borderRadius: "var(--radius-sm)",
        background: "var(--glass-bg)",
        border: "1px solid var(--glass-border)",
        color: "var(--text-muted)",
        font: "11px/1.4 var(--mono, ui-monospace, monospace)",
        letterSpacing: "0.01em",
        // Purely informational — never captures pointer events (the scene is
        // pointer-events:none; the badge stays consistent).
        pointerEvents: "none",
        // Quiet + static: no animation, no transition.
        userSelect: "none",
        whiteSpace: "nowrap",
        backdropFilter: "blur(var(--glass-blur, 12px))",
      }}
    >
      {label}
    </div>
  );
}

export default SceneStatusBadge;
