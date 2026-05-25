/**
 * sceneRegistry — the per-workflow scene chrome descriptor.
 *
 * Functional rationale (frontend-design spec, SPR-05): the verbs a scene
 * offers ARE the work that scene does, and the tabs ARE the views one object
 * actually has. A global toolbar would offer verbs unattached to the work in
 * front of you — form fighting function. So the chrome is keyed to the active
 * workflow: `workflowForRoute(pathname)` selects the descriptor; the Topbar
 * renders it. On a shared/operator route there is no descriptor and the Topbar
 * renders bare.
 *
 * Two load-bearing decisions, stated so SPR-07/future product sprints inherit
 * them rather than rediscover them:
 *
 *  1. Tabs are ROUTE-LINKED, not body-swappers. The scene body is rendered by
 *     the router into PanelLayout's `mainSlot`; a tab that "swapped the body"
 *     would fight that architecture (two sources of truth for what the scene
 *     shows). So a tab is a `NavLink` to its sub-view route and the active tab
 *     reflects the current URL. This is the hard-to-vary choice given the
 *     route-rendered body: it keeps the URL the single source of truth and
 *     makes deep-links / back-forward correct for free.
 *
 *  2. A tab whose product surface does not exist yet is HONEST: `builtState:
 *     'soon'`, rendered disabled with a small "soon" badge, never a `NavLink`
 *     to a fake destination. `built` is reserved for tabs whose `to` route is
 *     actually mounted in App.tsx today. The registry test enforces that a
 *     `built` tab always carries a `to`.
 *
 * SPR-07 owns wiring the action `intent`s and tab `to` routes to the real
 * product surfaces as they ship; this file already declares all four
 * workflows' descriptors so the chrome is exercisable now. Each action/tab
 * carries a comment citing the product-spec sprint it realizes.
 */

import type { Workflow } from "./workflowTaxonomy";
import { SHORTCUT_EVENTS } from "../workspace/shortcuts";

/**
 * A scene action = a verb the active workflow runs. The `intent` is functional
 * (no dead handlers): either a route navigation or a window event the shell
 * already listens for (the palette/launcher toggles dispatched in shortcuts.ts
 * + ProductsLauncher.tsx). The Topbar reads `intent.kind` to wire onClick.
 */
export type SceneActionIntent =
  | { kind: "navigate"; to: string }
  | { kind: "event"; event: string };

export interface SceneAction {
  id: string;
  label: string;
  intent: SceneActionIntent;
}

/**
 * A scene tab = one view of the workflow's primary object. `to` is the
 * sub-view route a `built` tab links to; `soon` tabs omit it (no fake
 * destination). `builtState` is the single switch the Topbar + WorkflowStub
 * key off — never a separate hardcoded "these are built" list.
 */
export interface SceneTab {
  id: string;
  label: string;
  to?: string;
  builtState: "built" | "soon";
}

export interface SceneDescriptor {
  actions: SceneAction[];
  tabs: SceneTab[];
}

/**
 * The window event the rail uses to open the products launcher. Mirrored here
 * (not imported) because it is owned by ProductsLauncher.tsx, not the shortcut
 * module; keeping the literal next to the actions that use it makes the
 * coupling visible.
 */
const LAUNCHER_TOGGLE_EVENT = "antiek:launcher:toggle";

/**
 * SCENE_REGISTRY — the four workflows' descriptors.
 *
 * Tabs are marked `built` only where the `to` route is mounted in App.tsx
 * today; everything the product specs describe but hasn't shipped is `soon`.
 * The built-vs-soon split is the honest state of the product surface, not an
 * aspiration.
 */
export const SCENE_REGISTRY: Record<Exclude<Workflow, "shared">, SceneDescriptor> = {
  // ---- Research: the investigation as the primary object ----
  // Verbs + tabs sourced from master-spec §6 (deep-research workspace) and the
  // four-workflow IA: an investigation has a synthesis, a trajectory, its
  // sources, and a literate notebook.
  research: {
    actions: [
      // master-spec §6.1 — start a fresh investigation (the research home).
      { id: "new", label: "New", intent: { kind: "navigate", to: "/" } },
      // master-spec §7.3 — chase an evidentiary gap; the chase tree lives in
      // the investigations index until the in-scene chase surface ships.
      { id: "chase", label: "Chase", intent: { kind: "navigate", to: "/investigations" } },
      // master-spec §8 — author a memo from the synthesis; Write owns the
      // editor, so the verb hands off to the creation studio.
      { id: "draft-memo", label: "Draft memo", intent: { kind: "navigate", to: "/create" } },
    ],
    tabs: [
      // master-spec §6.4 — the synthesis view is the research home today.
      { id: "synthesis", label: "Synthesis", to: "/", builtState: "built" },
      // master-spec §7.5 — trajectory replay exists per-investigation only
      // (/replay/:id); there is no standalone trajectory route yet.
      { id: "trajectory", label: "Trajectory", builtState: "soon" },
      // master-spec §6.2 — the source corpus is the Read DocumentsIndex today.
      { id: "sources", label: "Sources", to: "/documents", builtState: "built" },
      // master-spec §6.6 — the literate notebook index is built.
      { id: "notebook", label: "Notebook", to: "/notebooks", builtState: "built" },
    ],
  },

  // ---- Read: the document as the primary object ----
  // Verbs + tabs sourced from master-spec §6.2 (corpus + literate analysis)
  // and the Wrestle single-document deep-read surface.
  read: {
    actions: [
      // master-spec §6.2 — open / acquire a readable source.
      { id: "open", label: "Open", intent: { kind: "navigate", to: "/documents" } },
      // master-spec §5.6 — capture a voice note while reading; the capture
      // surface isn't built, so the verb opens the command palette where
      // capture will register (no dead handler in the meantime).
      { id: "voice-note", label: "Voice note", intent: { kind: "event", event: SHORTCUT_EVENTS.PALETTE_TOGGLE } },
      // master-spec §7 — spin a reading into a research investigation.
      { id: "spin-research", label: "Spin research", intent: { kind: "navigate", to: "/" } },
    ],
    tabs: [
      // master-spec §6.2 — the Wrestle single-document reader is built.
      { id: "reader", label: "Reader", to: "/wrestle", builtState: "built" },
      // master-spec §6.6 — reading notes land in the notebook surface.
      { id: "notes", label: "Notes", to: "/notebooks", builtState: "built" },
      // master-spec §7.3 — the per-reading rabbit-hole (evidentiary-gap)
      // surface is not built as a route yet.
      { id: "rabbit-hole", label: "Rabbit hole", builtState: "soon" },
      // master-spec §9 — the ad-border (IP-attribution economics) reader
      // surface is not built yet.
      { id: "ad-border", label: "Ad border", builtState: "soon" },
    ],
  },

  // ---- Write: the deliverable as the primary object ----
  // Verbs + tabs sourced from master-spec §8 (compose deliverables from
  // insight blocks) + §5 (voice/style discipline).
  write: {
    actions: [
      // master-spec §8.1 — add a section to the deliverable (the create home).
      { id: "new-section", label: "New section", intent: { kind: "navigate", to: "/create" } },
      // master-spec §8.2 — expand an outline node into prose; same studio.
      { id: "expand-outline", label: "Expand outline", intent: { kind: "navigate", to: "/create" } },
      // master-spec §6 + §3 — trace a written claim back to its source chunk;
      // the source corpus is the trace target today.
      { id: "trace-to-source", label: "Trace to source", intent: { kind: "navigate", to: "/documents" } },
    ],
    tabs: [
      // master-spec §8.2 — the outline view of a deliverable is not a separate
      // route yet (the studio is one route today).
      { id: "outline", label: "Outline", builtState: "soon" },
      // master-spec §8.1 — the editor IS the creation studio home.
      { id: "editor", label: "Editor", to: "/create", builtState: "built" },
      // master-spec §3 — the deliverable's cited sources map to the corpus.
      { id: "sources", label: "Sources", to: "/documents", builtState: "built" },
      // master-spec §5 — the voice/style panel is not a route yet.
      { id: "style", label: "Style", builtState: "soon" },
    ],
  },

  // ---- Speak: the interview-as-acquisition as the primary object ----
  // Verbs + tabs sourced from master-spec §10 (interview-as-acquisition) +
  // §9 (IP-attribution → contributors + payouts).
  speak: {
    actions: [
      // master-spec §10.1 — invite a contributor to an interview.
      { id: "invite", label: "Invite", intent: { kind: "navigate", to: "/interviews" } },
      // master-spec §10.2 — start / record an interview; the per-interview
      // record surface lives under /interview/:id, reached from the index.
      { id: "record", label: "Record", intent: { kind: "navigate", to: "/interviews" } },
      // master-spec §10.4 — verify a contribution; not a route yet, so the
      // verb opens the palette (where verify will register) rather than a fake
      // destination.
      { id: "verify", label: "Verify", intent: { kind: "event", event: SHORTCUT_EVENTS.PALETTE_TOGGLE } },
      // master-spec §8 — author a biography from the interview; Write owns the
      // editor.
      { id: "author", label: "Author", intent: { kind: "navigate", to: "/create" } },
      // master-spec §9.0 — publish gates on the legal/opt-in path; the publish
      // surface is not built, so the verb opens the launcher where publishing
      // infra is reachable.
      { id: "publish", label: "Publish", intent: { kind: "event", event: LAUNCHER_TOGGLE_EVENT } },
    ],
    tabs: [
      // master-spec §10.2 — the interviews index is built.
      { id: "interviews", label: "Interviews", to: "/interviews", builtState: "built" },
      // master-spec §10.4 — the corroboration view is not a route yet.
      { id: "corroboration", label: "Corroboration", builtState: "soon" },
      // master-spec §9.2 — the contributors / IP-holder view is not a route
      // yet (payouts infra lives under shared, not the Speak scene).
      { id: "contributors", label: "Contributors", builtState: "soon" },
      // master-spec §10.5 — the assembled biography view is not a route yet.
      { id: "biography", label: "Biography", builtState: "soon" },
    ],
  },
};

/** The descriptor for a workflow, or `null` for shared/operator routes. */
export function sceneForWorkflow(
  w: Exclude<Workflow, "shared"> | null,
): SceneDescriptor | null {
  return w ? SCENE_REGISTRY[w] : null;
}
