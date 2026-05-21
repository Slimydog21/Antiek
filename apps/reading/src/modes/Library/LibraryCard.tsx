// SPR-06 / M2 — Library card.
//
// One imported document per card. Shows: cover (favicon for HTML, "PDF"
// glyph for PDFs — the SPR-03 backend doesn't expose PDF page-1
// thumbnails as URLs yet, so we surface a deliberate placeholder
// rather than a fake one), title, source URL, last-read timestamp,
// read-progress bar.
//
// Paywall honesty (per rigor #1, intellectual honesty): documents
// whose metadata carries `paywalled: true` get a visible "partial"
// tag. The card must NOT look identical to a fully-ingested article.

import { Link } from "react-router-dom";

import { LemonTag } from "../../components/lemon";

export interface LibraryDocument {
  document_id: string;
  title: string | null;
  source_uri: string | null;
  document_type: string | null;
  source_tier: number;
  /** Free-form metadata pulled from the backend's `documents.metadata`
   * blob. Known keys this UI looks at: `paywalled`, `imported_at`,
   * `content_type`. */
  metadata?: Record<string, unknown> | null;
  /** Optional last-read timestamp pulled from local reading state.
   * Independent of the substrate; populated on `document_opened`
   * emit in this UI. */
  last_read_at?: string | null;
  /** Optional 0..1 reading progress. Same caveat as last_read_at. */
  read_progress?: number | null;
}

export interface LibraryCardProps {
  doc: LibraryDocument;
  /** Tags assigned to this doc (hover-revealed). */
  tagNames?: string[];
  /** Click handler — parent uses it to emit document_opened before
   * the route changes. */
  onOpen?: (doc: LibraryDocument) => void;
}

function favicon(sourceUri: string | null): string | null {
  if (!sourceUri) return null;
  try {
    const u = new URL(sourceUri);
    // Google's favicon endpoint is a stable, no-API-key endpoint for
    // a per-domain icon. If we wanted to host it ourselves we'd cache
    // these — out of scope this sprint.
    return `https://www.google.com/s2/favicons?domain=${encodeURIComponent(u.host)}&sz=64`;
  } catch {
    return null;
  }
}

function isPaywalled(doc: LibraryDocument): boolean {
  if (!doc.metadata) return false;
  return doc.metadata["paywalled"] === true;
}

function contentTypeLabel(doc: LibraryDocument): string {
  const ct = (doc.metadata?.["content_type"] as string | undefined) ?? doc.document_type ?? null;
  if (!ct) return "doc";
  if (ct === "html_article" || ct === "web_article") return "article";
  if (ct === "pdf") return "PDF";
  if (ct === "epub" || ct === "ebook") return "EPUB";
  if (ct === "arxiv" || ct === "academic_paper") return "arXiv";
  return ct;
}

function formatLastRead(iso: string | null | undefined): string {
  if (!iso) return "Never opened";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "Never opened";
  const now = Date.now();
  const diffSec = Math.max(0, (now - date.getTime()) / 1000);
  if (diffSec < 60) return "Just now";
  if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`;
  if (diffSec < 86_400) return `${Math.floor(diffSec / 3600)}h ago`;
  if (diffSec < 86_400 * 7) return `${Math.floor(diffSec / 86_400)}d ago`;
  return date.toLocaleDateString();
}

export function LibraryCard({ doc, tagNames, onOpen }: LibraryCardProps) {
  const paywalled = isPaywalled(doc);
  const ctLabel = contentTypeLabel(doc);
  const iconUrl = favicon(doc.source_uri);
  const isPdf = ctLabel === "PDF";
  const progress = doc.read_progress ?? 0;

  return (
    <Link
      to={`/wrestle/${encodeURIComponent(doc.document_id)}`}
      onClick={() => onOpen?.(doc)}
      data-testid="library-card"
      data-document-id={doc.document_id}
      className={
        "group block border-edge border-sun rounded-hog " +
        "bg-ice-0 dark:bg-charcoal-2 shadow-z1 dark:shadow-z1-night " +
        "hover:shadow-z3 dark:hover:shadow-z3-night " +
        "hover:-translate-x-[2px] hover:-translate-y-[2px] " +
        "transition-transform overflow-hidden"
      }
    >
      <div className="aspect-[16/10] bg-ice-3 dark:bg-charcoal-1 flex items-center justify-center relative">
        {isPdf ? (
          <div className="flex flex-col items-center gap-1 text-ink dark:text-bright">
            <span className="font-mono text-[24px] font-semibold tracking-wider">PDF</span>
            <span className="font-mono text-[10px] uppercase tracking-wider text-shadow-1 dark:text-moonlight">
              page-1 thumbnail deferred
            </span>
          </div>
        ) : iconUrl ? (
          <img
            src={iconUrl}
            alt=""
            width={48}
            height={48}
            className="opacity-80"
            loading="lazy"
          />
        ) : (
          <span className="font-mono text-[10px] uppercase tracking-wider text-shadow-1 dark:text-moonlight">
            no cover
          </span>
        )}

        {paywalled && (
          <div className="absolute top-2 right-2" data-testid="library-card-paywall-tag">
            <LemonTag colour="muted">partial · paywall</LemonTag>
          </div>
        )}
      </div>

      <div className="px-3 py-2.5 space-y-1.5">
        <div className="flex items-baseline justify-between gap-2">
          <p className="font-serif text-[14px] text-ink dark:text-bright truncate">
            {doc.title || doc.document_id}
          </p>
          <span className="font-mono text-[10px] uppercase tracking-wider text-shadow-1 dark:text-moonlight shrink-0">
            {ctLabel}
          </span>
        </div>

        {doc.source_uri && (
          <p className="font-mono text-[10px] text-shadow-1 dark:text-moonlight truncate">
            {prettySource(doc.source_uri)}
          </p>
        )}

        <div className="flex items-center justify-between gap-2 pt-1">
          <span className="font-mono text-[10px] text-shadow-2 dark:text-starlight">
            {formatLastRead(doc.last_read_at)}
          </span>
          <div className="flex-1 h-1 bg-ice-3 dark:bg-charcoal-1 rounded-full overflow-hidden ml-2 max-w-[80px]">
            <div
              className="h-full bg-sun"
              style={{ width: `${Math.min(100, Math.max(0, progress * 100))}%` }}
              data-testid="library-card-progress"
            />
          </div>
        </div>

        {tagNames && tagNames.length > 0 && (
          <div
            className="flex flex-wrap gap-1 pt-1 opacity-0 group-hover:opacity-100 transition-opacity"
            data-testid="library-card-tags"
          >
            {tagNames.slice(0, 4).map((t) => (
              <span
                key={t}
                className="font-mono text-[9px] uppercase tracking-wider px-1.5 py-0.5 rounded-full bg-ice-3 dark:bg-charcoal-1 text-shadow-1 dark:text-moonlight"
              >
                {t}
              </span>
            ))}
          </div>
        )}
      </div>
    </Link>
  );
}

function prettySource(uri: string): string {
  try {
    const u = new URL(uri);
    return `${u.host}${u.pathname === "/" ? "" : u.pathname}`;
  } catch {
    return uri;
  }
}

export default LibraryCard;
