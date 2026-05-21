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

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Renderer = ComponentType<any> | LazyExoticComponent<ComponentType<any>>;

export const PanelRegistry: Record<PanelKind, Renderer> = {
  // S3 — demo only
  FakeSidebar,
  FakeNotebook,
  FakeChat,

  // S5 — real research-workstation surfaces
  InvestigationSidebar: lazy(() => import("../modes/ResearchWorkstation/InvestigationSidebar")),
  Trajectory: lazy(() => import("../modes/ResearchWorkstation/TrajectoryView")),
  MasterMdViewer: lazy(() => import("../modes/ResearchWorkstation/MasterMdViewer")),
  Chat: lazy(() => import("../modes/ResearchWorkstation/ChatInputArea")),
  Chase: lazy(() => import("../modes/ResearchWorkstation/ChaseSlideOver")),

  // S6 — wrestling-workstation surfaces
  PdfViewer: lazy(() => import("../components/PdfViewer")),
  Notes: lazy(() => import("../components/NotesPanel")),
  CrossDocs: lazy(() => import("../components/CrossDocSidebar")),
  ClaimInspector: lazy(() => import("../components/ClaimCard")),

  // S7 — notebook surface
  Notebook: lazy(() => import("../modes/Notebook")),
  // S7-full — TipTap notebook editor (local-state autosave; substrate
  // integration arrives once the SPR-08+ merge lands on main)
  NotebookEditor: lazy(() => import("../modes/Notebook/EditorPanel")),

  // S8 — ubiquitous AI + palette
  AISidecar: lazy(() => import("../components/AISidecar")),
  CommandPalette: lazy(() => import("../components/CommandPalette")),

  // S4 — project-tree side rail panel (NavRail is separate, not a panel)
  ProjectTree: lazy(() => import("../components/navigation/ProjectTree")),

  // S10 — example route migrated as a panel
  Stats: lazy(() => import("../modes/Stats")),
};
