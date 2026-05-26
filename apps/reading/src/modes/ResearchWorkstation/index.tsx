import { useCallback, useRef } from "react";
import { useParams } from "react-router-dom";

import { useInvestigation } from "../../hooks/useInvestigation";
import type { InvestigationState } from "../../hooks/useInvestigation";
import { parseSynthesis } from "../../lib/synthesisParser";
import { PanelHost } from "../../workspace/PanelHost";
import { useWorkspace } from "../../workspace/WorkspaceStore";
import type { StarterPanel } from "../../workspace/PanelHost";
import DistillView from "./DistillView";
import HighlightToolbar from "./HighlightToolbar";
import MasterMdViewer from "./MasterMdViewer";
import NotesPanel from "./NotesPanel";
import StartResearch from "./StartResearch";
import ThinkingStream from "./ThinkingStream";

/**
 * Mode A — Research Workstation (S5 redesign).
 *
 * Layout shift from the legacy version:
 *   - InvestigationSidebar → docked-left panel (via PanelHost starter)
 *   - ChatInputArea       → docked-bottom panel (when an investigation
 *                            is loaded; the empty state renders the
 *                            StartResearch composer because there's no
 *                            investigation context for the docked Chat
 *                            panel yet — and a fresh `/` MUST be able to
 *                            actually start a research)
 *   - ChaseSlideOver      → floating panel opened via workspace action
 *   - Trajectory / MasterMdViewer → main slot (unchanged surface)
 *
 * The PanelHost wraps a starter list; AppShell (S4) provides the
 * surrounding NavRail + Topbar + dock zones. HighlightToolbar still
 * lives as a selection-anchored DOM overlay because it's positioned
 * against text, not workspace coordinates.
 */
export default function ResearchWorkstation() {
  const params = useParams<{ investigationId?: string }>();
  const investigationId = params.investigationId ?? null;

  const starters: StarterPanel[] = [
    {
      kind: "InvestigationSidebar",
      mode: "docked-left",
      title: "Investigations",
      id: "rw:investigation-sidebar",
    },
    ...(investigationId
      ? ([
          {
            kind: "Chat",
            mode: "docked-bottom",
            props: { parentInvestigationId: investigationId },
            title: "Chat · this investigation",
            id: `rw:chat:${investigationId}`,
          },
        ] as StarterPanel[])
      : []),
  ];

  return (
    <PanelHost starters={starters}>
      {investigationId ? (
        <InvestigationCenter investigationId={investigationId} />
      ) : (
        <StartResearch />
      )}
    </PanelHost>
  );
}

function InvestigationCenter({ investigationId }: { investigationId: string }) {
  const investigation = useInvestigation(investigationId);
  const centerRef = useRef<HTMLDivElement>(null);
  const openPanel = useWorkspace((s) => s.open);

  const onChaseThis = useCallback(
    (text: string) => {
      openPanel(
        "Chase",
        { spawnContext: text, parentInvestigationId: investigationId },
        { mode: "floating", title: "Chase" },
      );
    },
    [openPanel, investigationId],
  );

  if (investigation.status === "loading") {
    return (
      <div className="h-full flex items-center justify-center text-sm text-ink-mute dark:text-moonlight font-serif italic">
        Loading investigation…
      </div>
    );
  }
  if (investigation.status === "not_found") {
    return (
      <div className="h-full flex items-center justify-center text-sm text-shadow-1 dark:text-moonlight font-serif">
        No investigation with id <code className="font-mono">{investigationId}</code>.
      </div>
    );
  }

  return (
    <div ref={centerRef} className="h-full overflow-y-auto relative">
      <CenterContent investigation={investigation} />
      <HighlightToolbar scopeRef={centerRef} onChaseThis={onChaseThis} />
    </div>
  );
}

function CenterContent({ investigation }: { investigation: InvestigationState }) {
  if (
    investigation.status === "completed" ||
    investigation.status === "failed"
  ) {
    const synth = parseSynthesis(investigation.events);
    // SPR-03: a completed research's durable product is its insights + open
    // questions (DistillView, M2), shown alongside the answer prose
    // (MasterMdViewer, SPR-04's narrative is separate). When there's no
    // synthesis (the no-key / nothing-distilled case) DistillView carries the
    // honest no-result state on its own.
    return (
      <div className="flex h-full min-h-0 flex-col overflow-y-auto">
        {synth ? <MasterMdViewer synthesis={synth} /> : null}
        <div className="border-t border-rule dark:border-charcoal-1">
          <DistillView
            investigationId={investigation.id}
            running={false}
          />
        </div>
      </div>
    );
  }
  // SPR-02 live view + SPR-03 auto-notes: the plain-language thinking stream on
  // the left, the notes the async note-taker is taking on the right (M1) — the
  // user watches notes being taken, not just activity narrated. The raw log
  // lives one toggle away inside ThinkingStream. No steer controls on this
  // one-shot `/inv/:id` path — the Loop-1 orchestrator has no steerable runner;
  // the cascade monitor (DeepResearchWorkspace) is where Stop/redirect/deepen
  // are wired through a session.
  return (
    <div className="flex h-full min-h-0">
      <div className="min-w-0 flex-1">
        <ThinkingStream investigation={investigation} />
      </div>
      <aside className="hidden w-[320px] shrink-0 flex-col overflow-y-auto border-l border-rule dark:border-charcoal-1 lg:flex">
        <div className="border-b border-rule bg-ice-1 px-4 py-2 font-mono text-xs uppercase tracking-wider text-shadow-1 dark:border-charcoal-1 dark:bg-charcoal-2 dark:text-moonlight">
          Notes
        </div>
        <NotesPanel investigation={investigation} />
      </aside>
    </div>
  );
}
