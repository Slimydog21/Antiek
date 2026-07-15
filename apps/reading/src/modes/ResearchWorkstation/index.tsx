import { useCallback, useRef } from "react";
import { useParams } from "react-router-dom";

import { useInvestigation } from "../../hooks/useInvestigation";
import type { InvestigationState } from "../../hooks/useInvestigation";
import { parseSynthesis } from "../../lib/synthesisParser";
import GlassSurface from "../../shell/GlassSurface";
import { PanelHost } from "../../workspace/PanelHost";
import { useWorkspace } from "../../workspace/WorkspaceStore";
import type { StarterPanel } from "../../workspace/PanelHost";
import CollectiveLineage from "./CollectiveLineage";
import DistillView from "./DistillView";
import HighlightToolbar from "./HighlightToolbar";
import MasterMdViewer from "./MasterMdViewer";
import NotesPanel from "./NotesPanel";
import PasteIngest from "./PasteIngest";
import StartResearch from "./StartResearch";
import SuggestedResearch from "./SuggestedResearch";
import ThinkingStream from "./ThinkingStream";

/**
 * Mode A — Research Workstation (S5 redesign → Living-Roadmap SPR-05 M3).
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
 * ── ROUTING / CONSOLIDATION MODEL (SPR-05 M3 — defensibility, rigor #5) ──
 * The Research surface has exactly ONE home and ONE per-project view, and
 * they are not competing tabs:
 *
 *   /            → THIS component, IDLE branch → <StartResearch embedded />.
 *                  The IDLE home is the composer (start a research) ABOVE the
 *                  MyResearch LOG (past + running projects). This is the
 *                  operator's "the research home IS the research log" decision:
 *                  "My Research" is folded INTO the workstation home, not a
 *                  separate tab.
 *   /inv/:id     → THIS component, with an id → <InvestigationCenter> (the
 *                  SPR-03 canvas / DistillView). UNCHANGED — clicking a
 *                  project row in the log navigates here.
 *   /my-research → <MyResearch> standalone (App.tsx). KEPT non-breaking as the
 *                  full-page log + launch bar; `/investigations` already
 *                  redirects to it (App.tsx). The chord G+I + any deep link
 *                  still resolve. The legacy InvestigationsIndex form is NOT
 *                  routed (App.tsx retired it pre-SPR-05); the one start entry
 *                  is the composer here.
 *
 * What was REJECTED: keeping "My Research" as its own primary tab beside the
 * workstation (the two-tab model the operator's "two project tabs in research"
 * complaint flagged). What would REVERSE this: the operator wanting a
 * persistent cross-project home tab distinct from any single project — then
 * promote /my-research back into the nav and make `/` the bare composer.
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
        // SPR-05 M3: the idle home is the consolidated composer + research log.
        <StartResearch embedded />
      )}
    </PanelHost>
  );
}

function InvestigationCenter({ investigationId }: { investigationId: string }) {
  const investigation = useInvestigation(investigationId);
  const centerRef = useRef<HTMLDivElement>(null);
  const openPanel = useWorkspace((s) => s.open);

  // SPR-04 M2: highlight → follow this. A raw highlight has no reserved
  // escalation id, so we omit it and the substrate mints a fresh child.
  const onChaseThis = useCallback(
    (text: string) => {
      openPanel(
        "ChaseThread",
        { spawnContext: text, parentInvestigationId: investigationId },
        { mode: "floating", title: "Follow this" },
      );
    },
    [openPanel, investigationId],
  );

  // SPR-04 M2: chasing an OPEN QUESTION carries SPR-03's reserved
  // escalation id when the question escalated — launch INTO it (no
  // orphan), else mint fresh. One launch path either way.
  const onChaseQuestion = useCallback(
    (q: { text: string; reserved_child_investigation_id?: string | null }) => {
      openPanel(
        "ChaseThread",
        {
          spawnContext: q.text,
          parentInvestigationId: investigationId,
          reservedChildId: q.reserved_child_investigation_id ?? null,
        },
        { mode: "floating", title: "Follow this" },
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
        No investigation with id{" "}
        <code className="font-mono">{investigationId}</code>.
      </div>
    );
  }

  // AMS2-SPR-03 (M3): the ACTIVE /inv/:id view is the DENSE research IDE —
  // a long-session reading/working surface (live thinking stream, scored
  // notes, distilled insights, cited prose). The occlusion audit
  // (docs/ams-v2/spr-03-occlusion-audit.md §3) classifies it
  // dense-legible-keep-opaque: this surface stays OPAQUE-IN-WINDOW so dense
  // body text never rides over the moving scene (rigor #1 — a glass surface
  // that fails AA is worse than an opaque one that reads; M3 forbids making
  // the IDE transparent).
  //
  // Audit ground-truth correction: only the HEADER strips inside this view
  // carried an opaque bg (ThinkingStream.tsx:239 bg-ice-1, the Notes header
  // index.tsx:225, MasterMdViewer.tsx:272). The dense BODY areas
  // (ThinkingStream body, DistillView, NotesPanel rows) are background-free,
  // so without an opaque container they would render over the translucent
  // SceneChrome glass band (SceneChrome.tsx:267) → over the scene. We back the
  // whole dense centre in GlassSurface variant="solid" (bg-glass-solid, same
  // hue, alpha 1, NO backdrop-filter, NO scrim) — the opaque-in-window
  // fallback. The scene shows through the LANDING surfaces and the shell
  // margins, NOT this dense IDE. This is the counterpart to the idle `/` home
  // (StartResearch), which IS glassed — idle = landing-glass, active = dense-
  // opaque, resolving the M3 tension.
  return (
    <GlassSurface
      as="div"
      variant="solid"
      ref={centerRef}
      className="h-full overflow-y-auto relative"
    >
      <CollectiveLineage
        events={investigation.events}
        investigationId={investigation.id}
      />
      <CenterContent
        investigation={investigation}
        onChaseQuestion={onChaseQuestion}
      />
      <HighlightToolbar
        scopeRef={centerRef}
        onChaseThis={onChaseThis}
        investigationId={investigationId}
      />
    </GlassSurface>
  );
}

function CenterContent({
  investigation,
  onChaseQuestion,
}: {
  investigation: InvestigationState;
  onChaseQuestion: (q: {
    text: string;
    reserved_child_investigation_id?: string | null;
  }) => void;
}) {
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
            onChase={onChaseQuestion}
          />
        </div>
        {/* SPR-09: the §7 daemon's scored open questions, surfaced beside the
            answer as threads worth chasing. Read-only to render; chasing one
            reuses SPR-04's chase gesture (onChaseQuestion → the one
            ChaseThread panel), so it launches through the same capped path —
            no second launch mechanism, no auto-spawn. */}
        <div className="border-t border-rule dark:border-charcoal-1">
          <SuggestedResearch
            variant="beside"
            onChase={(c) => onChaseQuestion({ text: c.text })}
          />
        </div>
        {/* SPR-04 M3: paste/drop a file into THIS research → max-context
            pack. Absorbed content is citable on the next run / chase. */}
        <div className="border-t border-rule px-4 py-4 dark:border-charcoal-1">
          <PasteIngest investigationId={investigation.id} />
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
