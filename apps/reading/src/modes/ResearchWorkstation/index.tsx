import { useRef, useState } from "react";
import { useParams } from "react-router-dom";

import { useInvestigation } from "../../hooks/useInvestigation";
import type { InvestigationState } from "../../hooks/useInvestigation";
import { parseSynthesis } from "../../lib/synthesisParser";
import HeaderBar from "../shared/HeaderBar";
import ChaseSlideOver from "./ChaseSlideOver";
import ChatInputArea from "./ChatInputArea";
import HighlightToolbar from "./HighlightToolbar";
import InvestigationSidebar from "./InvestigationSidebar";
import MasterMdViewer from "./MasterMdViewer";
import TrajectoryView from "./TrajectoryView";

/**
 * Mode A — Research Workstation.
 *
 * Layout:
 *   Left  — InvestigationSidebar (past investigations tree)
 *   Center — TrajectoryView (live) → MasterMdViewer (post-completion)
 *   Bottom of center — ChatInputArea
 *   Floating — HighlightToolbar (anchored to selection)
 *   Slide-over — ChaseSlideOver (chase-this child investigation flow)
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
        <aside className="border-r border-stone-200 bg-stone-50 overflow-y-auto">
          <InvestigationSidebar />
        </aside>
        <main className="flex flex-col min-h-0 bg-white">
          {investigationId ? (
            <InvestigationCenter investigationId={investigationId} />
          ) : (
            <>
              <div className="flex-1 overflow-y-auto">
                <EmptyState />
              </div>
              <ChatInputArea autoFocus />
            </>
          )}
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
  const centerRef = useRef<HTMLDivElement>(null);
  const [chase, setChase] = useState<{ open: boolean; text: string }>({
    open: false,
    text: "",
  });

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

  // Render trajectory or synthesis viewer; either way, ChatInputArea
  // is pinned at the bottom (lets operator ask a follow-up question
  // without leaving the current investigation's context).
  return (
    <>
      <div ref={centerRef} className="flex-1 overflow-y-auto relative">
        <CenterContent investigation={investigation} />
        <HighlightToolbar
          scopeRef={centerRef}
          onChaseThis={(text) => setChase({ open: true, text })}
        />
      </div>
      <ChatInputArea />
      <ChaseSlideOver
        open={chase.open}
        spawnContext={chase.text}
        parentInvestigationId={investigationId}
        onClose={() => setChase((c) => ({ ...c, open: false }))}
      />
    </>
  );
}

function CenterContent({ investigation }: { investigation: InvestigationState }) {
  if (
    investigation.status === "completed" ||
    investigation.status === "failed"
  ) {
    const synth = parseSynthesis(investigation.events);
    if (synth) return <MasterMdViewer synthesis={synth} />;
  }
  return <TrajectoryView investigation={investigation} />;
}
