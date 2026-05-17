import { useParams } from "react-router-dom";

import { useInvestigation } from "../../hooks/useInvestigation";
import HeaderBar from "../shared/HeaderBar";
import ChatInputArea from "./ChatInputArea";
import TrajectoryView from "./TrajectoryView";

/**
 * Mode A — Research Workstation.
 *
 * Two-column layout:
 *   Left  — InvestigationSidebar (past investigations tree)
 *   Center — TrajectoryView (live) → MasterMdViewer (post-completion)
 *
 * Day 3 ships: layout + chat input. Days 4-8 fill in the center +
 * sidebar + chunk modal + highlight-to-chase + tree.
 */
export default function ResearchWorkstation() {
  const params = useParams<{ investigationId?: string }>();
  const investigationId = params.investigationId ?? null;

  return (
    <div className="flex flex-col h-screen">
      <HeaderBar>
        {investigationId && (
          <span className="text-xs font-mono text-stone-500">
            inv: <span className="text-stone-900">{investigationId}</span>
          </span>
        )}
      </HeaderBar>
      <div className="grid grid-cols-[280px_1fr] flex-1 min-h-0">
        {/* Left — sidebar (day 6 fills this in) */}
        <aside className="border-r border-stone-200 bg-stone-50 overflow-y-auto">
          <div className="p-3 text-xs font-mono text-stone-500">
            <div className="text-stone-700 font-semibold mb-2">
              Past investigations
            </div>
            <div className="text-stone-400 italic">
              Sidebar coming Day 6.
            </div>
          </div>
        </aside>

        {/* Center — empty state OR trajectory OR viewer */}
        <main className="flex flex-col min-h-0 bg-white">
          <div className="flex-1 overflow-y-auto">
            {investigationId ? (
              <InvestigationCenter investigationId={investigationId} />
            ) : (
              <EmptyState />
            )}
          </div>
          <ChatInputArea autoFocus={!investigationId} />
        </main>
      </div>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="h-full flex items-center justify-center">
      <div className="max-w-md text-center px-6">
        <h1 className="text-2xl font-serif text-stone-900 mb-3">
          What do you want to research?
        </h1>
        <p className="text-sm text-stone-500 leading-relaxed font-serif">
          Paste a question. The substrate runs a recursive note-taking
          chain across the corpus, distills insights and open questions,
          and renders a cited thesis. Highlight anything in the result
          to chase it further.
        </p>
      </div>
    </div>
  );
}

function InvestigationCenter({ investigationId }: { investigationId: string }) {
  const investigation = useInvestigation(investigationId);

  if (investigation.status === "loading") {
    return (
      <div className="h-full flex items-center justify-center text-sm text-stone-400 font-serif italic">
        Loading investigation…
      </div>
    );
  }
  if (investigation.status === "not_found") {
    return (
      <div className="h-full flex items-center justify-center text-sm text-stone-500 font-serif">
        No investigation with id <code className="font-mono">{investigationId}</code>.
      </div>
    );
  }
  // Days 5+ will transition to MasterMdViewer when status === "completed".
  // For Day 4 we render the trajectory for every non-loading/not-found state.
  return <TrajectoryView investigation={investigation} />;
}
