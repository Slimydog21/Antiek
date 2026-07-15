import ChaseThread from "../ResearchWorkstation/ChaseThread";
import { useWindows } from "../../workspace/windowsStore";

export type ReadingChaseWindowProps = {
  spawnContext: string;
  parentInvestigationId: string;
  documentTitle: string;
  pageNumber: number;
  reservedChildId?: string | null;
  workspaceWindowId: string;
};

/** A purpose-built glass-native host: source context plus the existing chase. */
export default function ReadingChaseWindow({
  spawnContext,
  parentInvestigationId,
  documentTitle,
  pageNumber,
  reservedChildId,
  workspaceWindowId,
}: ReadingChaseWindowProps) {
  const close = useWindows((state) => state.close);
  return (
    <section data-reading-chase-window className="flex h-full min-h-0 flex-col text-ink dark:text-bright">
      <header className="border-b border-rule bg-ice-1/80 px-4 py-3 dark:border-charcoal-1 dark:bg-charcoal-2/80">
        <p className="m-0 font-mono text-[10px] uppercase tracking-wider text-shadow-1 dark:text-moonlight">
          From {documentTitle} · page {pageNumber}
        </p>
        <p className="mt-1 line-clamp-2 border-l-2 border-sun pl-3 font-serif text-sm italic text-ink-soft dark:text-starlight">
          “{spawnContext}”
        </p>
      </header>
      <div className="min-h-0 flex-1 overflow-y-auto">
        <ChaseThread
          spawnContext={spawnContext}
          parentInvestigationId={parentInvestigationId}
          reservedChildId={reservedChildId}
          onOpenInMain={() => close(workspaceWindowId)}
        />
      </div>
    </section>
  );
}
