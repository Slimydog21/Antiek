/**
 * Breadcrumbs — the crumb row in the product's words (FFX SPR-01 M5, the
 * breadcrumb half of A-18).
 *
 * The auth crawl read raw slugs and record ids in the crumbs: "home",
 * "my-research", "write › <deliverable id>". Each crumb now resolves through
 * the same taxonomy lookup as the tab title (lib/RouteTitle.tsx, M4), so a
 * page's crumb and its title cannot disagree, and a record id is shown as
 * its entity noun ("a piece", "a notebook", "a research") — never the id.
 * When a mode knows the record's real title it can say so later through a
 * crumb override; until then the noun is honest and the id is not shown.
 *
 * WIRING: the crumb row is rendered by components/navigation/Topbar.tsx,
 * which is lane A's file this week. Adopting this module there is one line:
 *   const crumbs = defaultBreadcrumbsFor(pathname);
 * becomes
 *   const crumbs = breadcrumbsFor(pathname);   // import { breadcrumbsFor } from "./Breadcrumbs";
 * (the `Crumb` shape is the same), or the whole <nav> block can be replaced
 * with <Breadcrumbs pathname={pathname} />.
 */
import { Link } from "react-router-dom";

import { familyNameFor, matchRouteExactly } from "../../lib/RouteTitle";

export type Crumb = { label: string; to?: string };

/** A record id's own prefix names what it is. Checked first. */
const ID_PREFIX_NOUN: ReadonlyArray<readonly [RegExp, string]> = [
  [/^dlv-/i, "a piece"],
  [/^nb-/i, "a notebook"],
  [/^inv-/i, "a research"],
  [/^doc-/i, "a document"],
  [/^syn-/i, "an outcome"],
];

/** The route parameter an id fills names what it is. */
const PARAM_NOUN: Readonly<Record<string, string>> = {
  documentId: "a document",
  notebookId: "a notebook",
  investigationId: "a research",
  deliverableId: "a piece",
  synthesisId: "an outcome",
  sessionId: "a research",
  projectId: "a remembrance",
  token: "an invitation",
  ruleId: "a rule",
  assetId: "a meta-doc",
  interviewId: "an interview",
  kind: "a record",
  id: "a record",
};

/** For ids under routes the taxonomy does not pattern (e.g. /write/:id),
 *  the parent segment names what the id is. */
const PARENT_NOUN: Readonly<Record<string, string>> = {
  write: "a piece",
  create: "a piece",
  "deep-research": "a research",
  inv: "a research",
  replay: "a research",
  wrestle: "a document",
  read: "a document",
  notebook: "a notebook",
  outcomes: "an outcome",
  backtest: "an outcome",
  speak: "a remembrance",
  "skill-rules": "a rule",
  "meta-reading": "a meta-doc",
};

/** Path words that have no route of their own and read badly sentence-cased. */
const WORD_LABEL: Readonly<Record<string, string>> = {
  inv: "Research",
  "cross-graph": "Cross-graph",
};

function isIdLike(segment: string): boolean {
  return ID_PREFIX_NOUN.some(([re]) => re.test(segment)) || /\d/.test(segment);
}

function nounForId(segment: string, paramName: string | null, parent: string | null): string {
  for (const [re, noun] of ID_PREFIX_NOUN) if (re.test(segment)) return noun;
  if (paramName && PARAM_NOUN[paramName]) return PARAM_NOUN[paramName];
  if (parent && PARENT_NOUN[parent]) return PARENT_NOUN[parent];
  return "an item";
}

function sentenceCase(segment: string): string {
  const word = segment.replace(/^_+/, "").replace(/-/g, " ");
  return word ? word[0].toUpperCase() + word.slice(1) : segment;
}

/** The param a pattern route assigns to its LAST segment, if any. */
function lastParamName(route: string): string | null {
  const last = route.split("/").filter(Boolean).pop() ?? "";
  return last.startsWith(":") ? last.slice(1) : null;
}

function safeDecode(segment: string): string {
  try {
    return decodeURIComponent(segment);
  } catch {
    return segment;
  }
}

/** One crumb. `linked` is false where App.tsx has no page to open. */
function crumbFor(acc: string, segment: string, parent: string | null): { label: string; linked: boolean } {
  const hit = matchRouteExactly(acc);
  if (hit?.via === "exact") return { label: hit.name, linked: true };
  if (hit?.via === "pattern") {
    const param = lastParamName(hit.route);
    if (!param) return { label: hit.name, linked: true };
    if (isIdLike(segment)) return { label: nounForId(segment, param, parent), linked: true };
    // A word sitting in a parameter slot ("/speak/invite", "/notebook/auto")
    // is a path word, not a record; linking it would open "record invite".
    return { label: WORD_LABEL[segment] ?? sentenceCase(safeDecode(segment)), linked: false };
  }
  const family = familyNameFor(acc);
  if (family) return { label: family, linked: false };
  if (isIdLike(segment)) return { label: nounForId(segment, null, parent), linked: true };
  return { label: WORD_LABEL[segment] ?? sentenceCase(safeDecode(segment)), linked: true };
}

/** Crumbs for a pathname: one per path segment; each routed one links to its path. */
export function breadcrumbsFor(pathname: string): Crumb[] {
  const path = (pathname || "/").split(/[?#]/)[0];
  const segments = path.split("/").filter(Boolean);
  if (segments.length === 0) return [{ label: "Research" }];
  let acc = "";
  return segments.map((segment, i) => {
    acc += "/" + segment;
    const { label, linked } = crumbFor(acc, segment, i > 0 ? segments[i - 1] : null);
    return linked ? { label, to: acc } : { label };
  });
}

/** The crumb row, markup-compatible with Topbar's current <nav>. */
export function Breadcrumbs({ pathname }: { pathname: string }) {
  const crumbs = breadcrumbsFor(pathname);
  return (
    <nav aria-label="Breadcrumb" className="flex-1 min-w-0">
      <ol className="flex items-center gap-1.5 text-xs font-mono text-ink-soft dark:text-moonlight overflow-x-auto whitespace-nowrap">
        {crumbs.map((c, i) => (
          <li key={i} className="flex items-center gap-1.5">
            {i > 0 && (
              <span aria-hidden="true" className="text-ink-mute dark:text-moonlight/60">
                ›
              </span>
            )}
            {c.to && i < crumbs.length - 1 ? (
              <Link to={c.to} className="text-ink dark:text-bright hover:underline">
                {c.label}
              </Link>
            ) : (
              <span className="text-ink dark:text-bright font-semibold">{c.label}</span>
            )}
          </li>
        ))}
      </ol>
    </nav>
  );
}

export default Breadcrumbs;
