import { LemonTag } from "../../components/lemon";
import type { FullTextResponse } from "../../api/books";

/**
 * Attribution — the reader's rights/provenance chrome (Read SPR-05 M3).
 *
 * Renders on EVERY tier of the reader: it tells the reader where this work
 * came from and under what license. The data is read DIRECTLY off the
 * gate-served full-text response (never a local flag) — `tier` distinguishes
 * an arXiv document (`'T1'|'T2'|'T3'`) from a non-arXiv one (`null`):
 *
 *   • arXiv (canonical_url present) → a "via arXiv" link back to the abstract
 *     page (the authoritative source-of-record) + a tier chip + a license
 *     chip when a license URI is known.
 *   • non-arXiv (tier null, canonical_url null) → nothing extra. There is no
 *     canonical arXiv source-of-record to point at, so the component renders
 *     null and the reader's existing servability badge stays the rights cue.
 *
 * The "via arXiv" link is the attribution arXiv asks for (a link back to the
 * paper) and is honest about provenance regardless of which tier hosts the
 * body. It opens in a new tab and NEVER proxies arXiv bytes through Antiek —
 * it is a plain browser→arXiv navigation.
 */

export interface AttributionProps {
  body: FullTextResponse;
}

/** A short, human label for the arXiv rights tier (the chip text). */
function tierLabel(tier: "T1" | "T2" | "T3"): string {
  switch (tier) {
    case "T1":
      return "Open license";
    case "T2":
      return "Non-commercial";
    case "T3":
      return "Rights reserved";
  }
}

/** A short, human label for a known license URI. Falls back to the raw URI's
 *  last path segment so an unrecognised license still reads as *something*
 *  truthful rather than a fabricated name. */
function licenseLabel(license: string): string {
  const l = license.toLowerCase();
  if (l.includes("publicdomain") || l.includes("/zero/") || l.includes("cc0")) return "CC0";
  if (l.includes("/by-nc-sa")) return "CC BY-NC-SA";
  if (l.includes("/by-nc-nd")) return "CC BY-NC-ND";
  if (l.includes("/by-nc")) return "CC BY-NC";
  if (l.includes("/by-sa")) return "CC BY-SA";
  if (l.includes("/by-nd")) return "CC BY-ND";
  if (l.includes("/by")) return "CC BY";
  // arXiv's own default deposit license. Its URI ends in `.../1.0/`, so the
  // terminal-segment fallback would render a useless "1.0" chip — name it
  // honestly instead. Must come BEFORE the terminal fallback.
  if (l.includes("arxiv.org/licenses/nonexclusive-distrib")) return "arXiv default license";
  // Unknown URI: show its terminal segment, not an invented name.
  const seg = license.replace(/\/+$/, "").split("/").filter(Boolean).pop();
  return seg ? seg.toUpperCase() : "License";
}

export default function Attribution({ body }: AttributionProps) {
  const isArxiv = body.tier !== null && body.canonical_url !== null;

  // Non-arXiv: nothing to attribute beyond the reader's existing servability
  // badge — render nothing rather than empty chrome.
  if (!isArxiv) return null;

  const canonicalUrl = body.canonical_url as string;
  const tier = body.tier as "T1" | "T2" | "T3";

  return (
    <section
      aria-label="Attribution"
      className="flex flex-wrap items-center gap-2 text-[12px] font-mono text-shadow-1 dark:text-moonlight border-t border-rule dark:border-charcoal-1 pt-3"
    >
      <a
        href={canonicalUrl}
        target="_blank"
        rel="noreferrer noopener"
        className="text-ink dark:text-bright hover:text-ink dark:hover:text-bright underline-offset-2 hover:underline"
      >
        via arXiv ↗
      </a>
      <LemonTag colour={tier === "T1" ? "aurora" : "muted"} dot>
        {tierLabel(tier)}
      </LemonTag>
      {body.license && <LemonTag colour="muted">{licenseLabel(body.license)}</LemonTag>}
    </section>
  );
}
