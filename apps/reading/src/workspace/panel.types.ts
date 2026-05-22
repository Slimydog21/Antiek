/**
 * Workspace panel type system.
 *
 *   PanelKind          — string-tagged union of all renderable panel surfaces.
 *                        Adding a new panel surface means adding one entry here
 *                        plus one entry in PanelRegistry.
 *   PanelMode          — where the panel is drawn (docked-l/r, floating, popout).
 *                        S5 extends this with "docked-bottom" for the Chat surface.
 *   PanelDescriptor    — one open panel's full state.
 *   WorkspaceSnapshot  — the whole shell at one moment in time.
 */

export type PanelMode =
  | "docked-left"
  | "docked-right"
  | "docked-bottom"
  | "floating"
  | "popout";

/**
 * Stable string vocabulary of renderable panel surfaces. The
 * PanelRegistry maps each entry to a React component (or React.lazy).
 *
 * S3 only "Fake*" entries (the demo scene). S5+ adds real surfaces
 * (InvestigationSidebar, Trajectory, Chat, Chase, PdfViewer, Notes,
 * CrossDocs, ClaimInspector, Notebook, AISidecar, CommandPalette, …).
 *
 * Stored on disk eventually (S9 persistence), so renames are
 * load-bearing. Prefer adding new kinds over renaming existing ones.
 */
export type PanelKind =
  | "FakeSidebar"
  | "FakeNotebook"
  | "FakeChat"
  | "InvestigationSidebar"
  | "Trajectory"
  | "MasterMdViewer"
  | "Chat"
  | "Chase"
  | "PdfViewer"
  | "Notes"
  | "CrossDocs"
  | "ClaimInspector"
  | "Notebook"
  | "NotebookEditor"
  | "AISidecar"
  | "CommandPalette"
  | "ProjectTree"
  | "Stats"
  | "DeliverableSidebar"
  | "BlockPalette"
  | "ReplayStepList"
  | "InterviewRecording"
  | "InterviewTranscript"
  | "InterviewNotes"
  | "Lightbox"
  | "BrainstormWatchList"
  | "BrainstormThoughtPartner";

export type PanelDescriptor = {
  /** Stable id. e.g. "InvestigationSidebar:default", "Chat:inv-abc:42". */
  id: string;
  /** What surface to render. Lookups go through `PanelRegistry[kind]`. */
  kind: PanelKind;
  /** Props passed to the renderer. */
  props: Record<string, unknown>;
  /** Where the panel currently lives. */
  mode: PanelMode;
  /**
   * z-index. Only meaningful for `floating` panels. Docked panels keep
   * their order via the `dockLeftIds` / `dockRightIds` arrays.
   */
  zIndex: number;
  /** Floating-only: position + size in the floating layer. */
  rect: { x: number; y: number; width: number; height: number };
  /** Docked-only: width/height hints (operator can resize docks in S3). */
  size: { width: number; height: number };
  /** Pinned panels survive route changes (carried forward in S9). */
  pinned: boolean;
  /** Operator-readable label rendered in the handle. */
  title: string;
};

export type WorkspaceSnapshot = {
  panels: Record<PanelDescriptor["id"], PanelDescriptor>;
  /** Top-to-bottom order inside the left dock. */
  dockLeftIds: string[];
  /** Top-to-bottom order inside the right dock. */
  dockRightIds: string[];
  /** Left-to-right order inside the bottom dock. Used by Chat-style
   *  panels that want to live under the main slot. */
  dockBottomIds: string[];
  /** Bottom-to-top z order in the floating layer (last entry = highest). */
  floatingIds: string[];
  /** The currently-focused panel (for keyboard focus + bring-to-front). */
  focusedPanelId: string | null;
  /** Monotonic counter so newly-focused floats sit above existing ones. */
  zCounter: number;
  /** Operator-resizable bottom-dock height (px). Default 220. */
  dockBottomHeight: number;
  /**
   * Bumped when the persistence schema changes (S9). A mismatched
   * version is ignored at hydration time with a debug log.
   */
  schemaVersion: 1;
};

/** A bare empty snapshot (used as the initial state + by `reset`). */
export const EMPTY_SNAPSHOT: WorkspaceSnapshot = {
  panels: {},
  dockLeftIds: [],
  dockRightIds: [],
  dockBottomIds: [],
  floatingIds: [],
  focusedPanelId: null,
  zCounter: 1,
  dockBottomHeight: 220,
  schemaVersion: 1,
};
