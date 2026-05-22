import { lazy } from "react";
import type { ComponentType, LazyExoticComponent } from "react";

import type { PanelKind } from "./panel.types";

/**
 * Map from `PanelKind` to the React component that renders it.
 *
 * Adding a new panel surface = one entry here + one entry in PanelKind.
 * No orchestrator changes; PanelLayoutPanel does the dispatch.
 *
 * Renderers are `React.lazy` so the bundle is code-split per panel:
 * the main chunk doesn't pay for `Notebook` until a Notebook panel
 * actually mounts.
 *
 * S3 only registers the three Fake* demo renderers used by the
 * Workspace/Demo Storybook story. S5+ adds real surfaces:
 *   - S5: InvestigationSidebar, Trajectory, MasterMdViewer, Chat, Chase
 *   - S6: PdfViewer, Notes, CrossDocs, ClaimInspector
 *   - S7: Notebook
 *   - S8: AISidecar, CommandPalette
 *   - S4: ProjectTree
 */

// S3 demo renderers (eagerly imported because they are small fake panels)
import { FakeChat } from "./__fakes__/FakeChat";
import { FakeNotebook } from "./__fakes__/FakeNotebook";
import { FakeSidebar } from "./__fakes__/FakeSidebar";

// Eager imports for renderers that ALSO appear as direct main-slot
// children of routes (RW imports MasterMdViewer + TrajectoryView,
// WrestleApp imports PdfViewer, App.tsx imports Notebook + Stats).
// Marking these as `lazy()` here while they're statically imported
// elsewhere defeats the code-split — vite warns "dynamic import will
// not move module into another chunk." Make the registry match
// reality: these renderers ship in the main bundle either way.
import PdfViewer from "../components/PdfViewer";
import NotebookPage from "../modes/Notebook";
import MasterMdViewer from "../modes/ResearchWorkstation/MasterMdViewer";
import TrajectoryView from "../modes/ResearchWorkstation/TrajectoryView";
import Stats from "../modes/Stats";

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Renderer = ComponentType<any> | LazyExoticComponent<ComponentType<any>>;

export const PanelRegistry: Record<PanelKind, Renderer> = {
  // S3 — demo only
  FakeSidebar,
  FakeNotebook,
  FakeChat,

  // S5 — real research-workstation surfaces. InvestigationSidebar +
  // Chat + Chase are only referenced via the registry, so they stay
  // lazy + ship in their own chunks. MasterMdViewer + Trajectory are
  // direct main-slot children in RW/index.tsx — eager.
  InvestigationSidebar: lazy(() => import("../modes/ResearchWorkstation/InvestigationSidebar")),
  Trajectory: TrajectoryView,
  MasterMdViewer,
  Chat: lazy(() => import("../modes/ResearchWorkstation/ChatInputArea")),
  Chase: lazy(() => import("../modes/ResearchWorkstation/ChaseSlideOver")),

  // S6 — wrestling-workstation surfaces. PdfViewer is a direct child
  // of WrestleApp's main slot → eager. Notes / CrossDocs /
  // ClaimInspector are panel-only → lazy.
  PdfViewer,
  Notes: lazy(() => import("../components/NotesPanel")),
  CrossDocs: lazy(() => import("../components/CrossDocSidebar")),
  ClaimInspector: lazy(() => import("../components/ClaimCard")),

  // S7 — Notebook is also rendered at /notebook/:id (static App.tsx
  // import), so eager. NotebookEditor is panel-only → lazy (the TipTap
  // chunk is the biggest in the app — preserving the split matters).
  Notebook: NotebookPage,
  NotebookEditor: lazy(() => import("../modes/Notebook/EditorPanel")),

  // S8 — ubiquitous AI + palette. Both are mounted as top-level
  // components in AppShell so they're effectively eager already; we
  // keep them as panel kinds so the workspace can route ⌘/ + ⌘K
  // through workspace.open/close.
  AISidecar: lazy(() => import("../components/AISidecar")),
  CommandPalette: lazy(() => import("../components/CommandPalette")),

  // S4 — project-tree side rail panel (NavRail is separate, not a panel)
  ProjectTree: lazy(() => import("../components/navigation/ProjectTree")),

  // S10 — Stats is also rendered as a route → eager.
  Stats,

  // S10 row 10.7 — CreationStudio side panels
  DeliverableSidebar: lazy(() => import("../modes/CreationStudio/DeliverableSidebar")),
  BlockPalette: lazy(() => import("../modes/CreationStudio/BlockPalette")),

  // S10 row 10.14 — Replay step timeline panel
  ReplayStepList: lazy(() => import("../modes/Replay/ReplayStepList")),

  // S10 row 10.10 — Interview tri-pane panels
  InterviewRecording: lazy(() => import("../modes/Interview/InterviewRecording")),
  InterviewTranscript: lazy(() => import("../modes/Interview/InterviewTranscript")),
  InterviewNotes: lazy(() => import("../modes/Interview/InterviewNotes")),

  // S7 WP-7.3 — ImageBlock "open as panel" target
  Lightbox: lazy(() => import("../components/Lightbox")),

  // S10 row 10.8 — BrainstormStation panels
  BrainstormWatchList: lazy(() => import("../modes/BrainstormStation/WatchForLaterPanel")),
  BrainstormThoughtPartner: lazy(() => import("../modes/BrainstormStation/ThoughtPartnerPanel")),
};
