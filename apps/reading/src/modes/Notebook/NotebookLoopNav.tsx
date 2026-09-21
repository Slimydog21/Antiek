import { Link } from "react-router-dom";

/**
 * Daily-loop nav for AutoNotebook (read → research → notebook → write).
 * Cite: AutoNotebook (SPR-06), DistillView open-auto-notebook, Write ConnectResearch.
 * No new product — only links to already-shipped surfaces.
 */

/** Build `/write?investigation=&title=` handoff (title optional, never invented). */
export function writeHandoffHref(
  investigationId: string,
  title?: string | null,
): string {
  const q = new URLSearchParams();
  q.set("investigation", investigationId);
  const t = (title ?? "").trim();
  if (t) q.set("title", t.slice(0, 200));
  return `/write?${q.toString()}`;
}

export interface NotebookLoopNavProps {
  investigationId: string;
  /** When true, emphasize Write handoff (graph has narratable content). */
  canWrite?: boolean;
  /** Prefills Write title when continuing from auto-notebook (real question/title only). */
  writeTitle?: string | null;
}

export default function NotebookLoopNav({
  investigationId,
  canWrite = false,
  writeTitle = null,
}: NotebookLoopNavProps) {
  const inv = encodeURIComponent(investigationId);
  const writeTo = writeHandoffHref(investigationId, writeTitle);

  return (
    <nav
      aria-label="Daily loop"
      data-testid="notebook-loop-nav"
      className="flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-[11px] text-shadow-1 dark:text-moonlight"
    >
      <Link
        to={`/inv/${inv}`}
        className="underline-offset-2 hover:underline"
        data-testid="auto-notebook-back-to-research"
      >
        ← back to research
      </Link>
      <span aria-hidden="true">·</span>
      <Link
        to={`/inv/${inv}#distill`}
        className="underline-offset-2 hover:underline"
        data-testid="auto-notebook-open-distill"
      >
        distill
      </Link>
      <span aria-hidden="true">·</span>
      <Link
        to={writeTo}
        className={
          canWrite
            ? "text-sun-deep dark:text-sun underline-offset-2 hover:underline"
            : "underline-offset-2 hover:underline"
        }
        data-testid="auto-notebook-continue-write"
      >
        {canWrite ? "continue in Write →" : "open Write"}
      </Link>
      <span aria-hidden="true">·</span>
      <Link
        to="/notebooks"
        className="underline-offset-2 hover:underline"
        data-testid="auto-notebook-notebooks-index"
      >
        all notebooks
      </Link>
    </nav>
  );
}
