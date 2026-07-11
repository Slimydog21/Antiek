/**
 * HTML asset view session compose (pure).
 *
 * Operator vision: every information asset (books, research output, papers)
 * is viewed as HTML — not PDF. Open a view session with twin bind readiness
 * and hard PDF denial.
 *
 * pdf_view_authorized always false.
 * store_mutated always false.
 */

export interface HtmlAssetViewSessionInput {
  session_id: string;
  asset_id: string;
  /** Ready HTML projection sha for this asset (caller-supplied). */
  html_projection_sha: string | null;
  /** Operator requested view. */
  view_requested: boolean;
  /** Twin bind proposed or bound for this asset. */
  twin_bound: boolean;
  /** Twin has ≥1 insight/question recorded (caller-supplied). */
  twin_substrate_ready?: boolean;
  /** Optional mime/format claim — if "pdf" hard-deny. */
  claimed_format?: string | null;
}

export interface HtmlAssetViewSessionCompose {
  session_id: string;
  asset_id: string;
  html_projection_sha: string | null;
  /** True when view_requested and ready HTML sha present. */
  html_view_ready: boolean;
  twin_ready: boolean;
  /**
   * True when HTML view ready (and twin optional).
   * Session can open as HTML-native reader surface.
   */
  session_ready: boolean;
  /** Always false — PDF never primary view authority. */
  pdf_view_authorized: false;
  /** Always false — pure layer never mutates asset store. */
  store_mutated: false;
  notes: string[];
  authority: "html_asset_view_session_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Compose HTML-native view session for any information asset.
 * Never authorizes PDF; never mutates store.
 */
export function composeHtmlAssetViewSession(
  input: HtmlAssetViewSessionInput,
): HtmlAssetViewSessionCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.view_requested !== "boolean") {
    throw new Error("view_requested must be an explicit boolean");
  }
  if (typeof input.twin_bound !== "boolean") {
    throw new Error("twin_bound must be an explicit boolean");
  }
  const session_id = requireNonEmpty(input.session_id, "session_id");
  const asset_id = requireNonEmpty(input.asset_id, "asset_id");

  const notes: string[] = [
    "pdf_view_authorized=false — HTML-native doctrine for all assets",
    "store_mutated=false — view session is advisory readiness only",
  ];

  if (input.claimed_format != null && input.claimed_format !== undefined) {
    const fmt = requireNonEmpty(input.claimed_format, "claimed_format").toLowerCase();
    if (fmt === "pdf" || fmt === "application/pdf") {
      notes.push(
        "claimed_format=pdf — hard deny PDF view; require HTML projection first",
      );
    } else {
      notes.push(`claimed_format=${fmt}`);
    }
  }

  let html_projection_sha: string | null = null;
  if (
    input.html_projection_sha != null &&
    input.html_projection_sha !== undefined
  ) {
    html_projection_sha = requireNonEmpty(
      input.html_projection_sha,
      "html_projection_sha",
    );
  }

  const isPdfClaim =
    typeof input.claimed_format === "string" &&
    ["pdf", "application/pdf"].includes(
      input.claimed_format.trim().toLowerCase(),
    );

  const html_view_ready =
    input.view_requested &&
    html_projection_sha !== null &&
    !isPdfClaim;

  if (!input.view_requested) {
    notes.push("html_view_ready=false — view_requested=false");
  } else if (isPdfClaim) {
    notes.push("html_view_ready=false — PDF claim blocked until HTML projection");
  } else if (html_projection_sha === null) {
    notes.push(
      "html_view_ready=false — html_projection_sha absent (no invent projection)",
    );
  } else {
    notes.push("html_view_ready=true — ready HTML projection present");
  }

  const twin_substrate =
    input.twin_substrate_ready === undefined
      ? false
      : input.twin_substrate_ready;
  if (typeof twin_substrate !== "boolean") {
    throw new Error("twin_substrate_ready must be boolean when set");
  }

  const twin_ready = input.twin_bound || twin_substrate;
  notes.push(
    twin_ready
      ? `twin_ready=true · bound=${input.twin_bound} · substrate=${twin_substrate}`
      : "twin_ready=false — twin not bound and no substrate signal",
  );

  // Session ready for HTML view; twin is optional enhancement.
  const session_ready = html_view_ready;
  notes.push(
    session_ready
      ? "session_ready=true — open as HTML-native view"
      : "session_ready=false — need ready HTML projection + view_requested",
  );

  notes.push("pdf_view_authorized=false");
  notes.push("store_mutated=false");

  return {
    session_id,
    asset_id,
    html_projection_sha,
    html_view_ready,
    twin_ready,
    session_ready,
    pdf_view_authorized: false,
    store_mutated: false,
    notes,
    authority: "html_asset_view_session_compose_advisory",
  };
}

export function formatHtmlAssetViewSessionSummary(
  c: HtmlAssetViewSessionCompose,
): string {
  return (
    `session_ready=${c.session_ready} · html_view_ready=${c.html_view_ready} · ` +
    `twin_ready=${c.twin_ready} · pdf_view_authorized=false`
  );
}
