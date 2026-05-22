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
import { fetchIsReturning } from "../../api/users/me";

export interface PostLoginDestinationInput {
  /** Caller-provided `?next=` URL from the magic-link callback (e.g.
   * a deep link the user originally tried to hit). When present this
   * always wins — the routing decision below applies only when the
   * user landed at the bare `/` post-login. */
  nextParam?: string | null;
  /** The current authenticated user's id. Threaded through to the
   *  substrate's is-returning lookup. Defaults to the single-operator
   *  constant if absent. */
  userId?: string;
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
    | "library_fallback_no_last_doc"
    | "substrate_returning_user"
    | "substrate_new_user";
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


/** Async variant of ``resolvePostLoginDestination`` that consults the
 *  substrate's authoritative ``is_returning_user`` view before falling
 *  back to the localStorage proxy.
 *
 *  When the substrate is reachable + the user is "returning" (has at
 *  least one behavior event older than the threshold), routing to
 *  ``/wrestle/<last>`` is correct even on a fresh device — solves the
 *  cross-device-treated-as-new bug the SPR-06 handoff flagged.
 *
 *  When the substrate is unreachable, fetchIsReturning resolves to
 *  null and we delegate to the sync resolver above (localStorage
 *  proxy + per-device heuristic). The TS layer keeps working
 *  regardless of backend availability — same posture as the SPR-03
 *  ingest client.
 */
export async function resolvePostLoginDestinationAsync(
  input: PostLoginDestinationInput = {},
): Promise<PostLoginDestination> {
  // The deep-link + library-setting paths don't need the substrate;
  // resolve them synchronously first. Only the new-vs-returning
  // distinction benefits from the substrate call.
  if (input.nextParam && input.nextParam !== "/" && input.nextParam !== "") {
    return { path: input.nextParam, reason: "next_param_honored" };
  }
  if (effectiveAlwaysStartAtLibrary()) {
    const lastDoc = readLastOpenedDocument();
    return lastDoc === null
      ? { path: "/library", reason: "library_default_for_new_user" }
      : { path: "/library", reason: "library_setting_opted_in" };
  }

  const substrate = await fetchIsReturning({ userId: input.userId });
  if (substrate !== null) {
    if (substrate.is_returning) {
      const lastDoc = readLastOpenedDocument();
      if (lastDoc) {
        return {
          path: `/wrestle/${encodeURIComponent(lastDoc)}`,
          reason: "substrate_returning_user",
        };
      }
      // Substrate says returning but we have no per-device last-doc;
      // safest is the library so we don't dead-end them.
      return {
        path: "/library",
        reason: "library_fallback_no_last_doc",
      };
    }
    // Substrate authoritatively says new — wedge landing.
    return {
      path: "/library",
      reason: "substrate_new_user",
    };
  }

  // Substrate unreachable — delegate to the sync resolver (localStorage
  // proxy + heuristic).
  return resolvePostLoginDestination(input);
}
