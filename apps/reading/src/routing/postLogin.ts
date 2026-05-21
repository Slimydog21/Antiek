// SPR-06 / M4 — Post-login destination resolver.
//
// =============================================================
// IMPORTANT — Dual-market positioning rationale (per rigor #5,
// defensibility):
// =============================================================
//
// Antiek's master spec (locked 2026-05-21) treats the cozy reader
// as a real audience alongside the operator. The cozy reader's pain
// is "I save PDFs and links to random folders with no good viewing
// experience." The fix is the universal library + URL paste: paste
// a URL → it joins your library → you read it in Wrestle.
//
// For this fix to be the WEDGE rather than a feature, the library
// must be the LANDING surface for new users. If a new sign-up lands
// at the last-opened-document (their NONE) and gets a blank Wrestle
// page, the wedge does not exist for them — they bounce.
//
// An existing engineer reading this code might expect "post-login →
// last document" because that's the operator-product mental model.
// That expectation is wrong for the dual-market positioning. New
// users → /library is intentional; existing users keep their
// last-opened-document landing so we don't strip flow from people
// who already use the substrate. The "Always start at library"
// settings toggle lets either cohort opt in or out.
//
// This is the routing decision the master spec calls out; the
// setting toggle is for individual user override.
// =============================================================

import {
  effectiveAlwaysStartAtLibrary,
  readLastOpenedDocument,
} from "../settings/userSettings";

export interface PostLoginDestinationInput {
  /** Caller-provided `?next=` URL from the magic-link callback (e.g.
   * a deep link the user originally tried to hit). When present this
   * always wins — the routing decision below applies only when the
   * user landed at the bare `/` post-login. */
  nextParam?: string | null;
}

export interface PostLoginDestination {
  /** Path to navigate to (e.g. `/library`, `/wrestle/doc-abc`). */
  path: string;
  /** Why we picked this path. Useful for tests, dev console, and
   * the rationale comment trail. */
  reason:
    | "next_param_honored"
    | "library_default_for_new_user"
    | "library_setting_opted_in"
    | "last_opened_document"
    | "library_fallback_no_last_doc";
}

/** Resolve where a freshly-logged-in user should land.
 *
 * Order of precedence:
 *   1. `?next=` param from the magic-link callback (deep link).
 *   2. User has opted into "Always start at library" → `/library`.
 *   3. New user (no last-opened doc on this device) → `/library`
 *      (the dual-market wedge landing, per the rationale block at
 *      the top of this file).
 *   4. Existing user with a recorded last doc → `/wrestle/<id>`.
 *   5. Otherwise (no signal) → `/library` (safe default).
 */
export function resolvePostLoginDestination(
  input: PostLoginDestinationInput = {},
): PostLoginDestination {
  // 1. Honor deep link.
  if (input.nextParam && input.nextParam !== "/" && input.nextParam !== "") {
    return {
      path: input.nextParam,
      reason: "next_param_honored",
    };
  }

  // 2. Explicit user preference wins over inference.
  if (effectiveAlwaysStartAtLibrary()) {
    const lastDoc = readLastOpenedDocument();
    if (lastDoc === null) {
      // Brand-new device → wedge landing.
      return {
        path: "/library",
        reason: "library_default_for_new_user",
      };
    }
    // User opted in despite having history.
    return {
      path: "/library",
      reason: "library_setting_opted_in",
    };
  }

  // 3 + 4. Returning user falls back to last document.
  const lastDoc = readLastOpenedDocument();
  if (lastDoc) {
    return {
      path: `/wrestle/${encodeURIComponent(lastDoc)}`,
      reason: "last_opened_document",
    };
  }

  // 5. No signal — library is the safe default.
  return {
    path: "/library",
    reason: "library_fallback_no_last_doc",
  };
}
