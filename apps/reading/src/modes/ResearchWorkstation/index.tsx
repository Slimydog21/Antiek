import { useCallback, useRef } from "react";
import { useParams } from "react-router-dom";

import { useInvestigation } from "../../hooks/useInvestigation";
import type { InvestigationState } from "../../hooks/useInvestigation";
import { parseSynthesis } from "../../lib/synthesisParser";
import { PanelHost } from "../../workspace/PanelHost";
import { useWorkspace } from "../../workspace/WorkspaceStore";
import type { StarterPanel } from "../../workspace/PanelHost";
import HighlightToolbar from "./HighlightToolbar";
import MasterMdViewer from "./MasterMdViewer";
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
    if (synth) return <MasterMdViewer synthesis={synth} />;
  }
  // SPR-02: the default live view is the plain-language thinking stream, not
  // the raw event log. The raw log lives one toggle away inside ThinkingStream
  // (the "show raw activity" escape hatch reuses TrajectoryView). No steer
  // controls on this one-shot `/inv/:id` path — the Loop-1 orchestrator has no
  // steerable runner; the cascade monitor (DeepResearchWorkspace) is where
  // Stop/redirect/deepen are wired through a session.
  return <ThinkingStream investigation={investigation} />;
}
