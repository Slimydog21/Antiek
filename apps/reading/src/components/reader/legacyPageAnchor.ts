import type { HtmlProjectionAnchorMapping } from "../../api/htmlProjections";

export type LegacyPageAnchorResult =
  | { kind: "resolved"; anchorId: string }
  | { kind: "not-found" }
  | { kind: "ambiguous"; anchorIds: readonly string[] }
  | { kind: "invalid-anchor" }
  | { kind: "invalid" };

const CANONICAL_ANCHOR_ID = /^antiek-anchor-[0-9a-f]{64}$/;

/** Resolve a compatibility-only PDF page to one canonical projection anchor. */
export function resolveLegacyPageAnchor(
  mappings: readonly HtmlProjectionAnchorMapping[],
  page: number,
): LegacyPageAnchorResult {
  if (!Number.isSafeInteger(page) || page <= 0) return { kind: "invalid" };

  const anchorIds = mappings
    .filter(
      (mapping) =>
        mapping.state === "resolved" &&
        mapping.source_locator.kind === "pdf_page_bbox" &&
        mapping.source_locator.page === page,
    )
    .map((mapping) => mapping.html_anchor_id);

  if (anchorIds.length === 0) return { kind: "not-found" };
  if (anchorIds.length > 1) return { kind: "ambiguous", anchorIds };
  if (!CANONICAL_ANCHOR_ID.test(anchorIds[0])) return { kind: "invalid-anchor" };
  return { kind: "resolved", anchorId: anchorIds[0] };
}

/** Accept only the substrate's `Page N` locator, optionally followed by a path. */
export function parseLegacyPageLocator(locator: string | null | undefined): number | null {
  if (!locator) return null;
  const match = /^Page ([1-9]\d*)(?: · .+)?$/.exec(locator);
  if (!match) return null;
  const page = Number(match[1]);
  return Number.isSafeInteger(page) ? page : null;
}
