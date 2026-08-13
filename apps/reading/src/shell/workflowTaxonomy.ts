/**
 * workflowTaxonomy.ts — the single source of truth that maps EVERY
 * frontend mode to one of the four product workflows (Research / Read /
 * Write / Speak) or to an explicit `shared` operator/governance bucket.
 *
 * SPR-04 (antiek-unified Wave 2). The product is unified behind four
 * workflows; the ~37 self-registering modes under `src/modes/` carry no
 * Research/Read/Write/Speak framing of their own. This file IS the
 * framing. Nothing is allowed to be orphaned: a build-time completeness
 * check (`taxonomy.test.ts`) enumerates the mode directories and FAILS
 * if any registered mode is absent here.
 *
 * Why a hand-authored map and not auto-derivation: the grouping is a
 * product decision (which workflow story does this surface tell?), not
 * a mechanical fact. The mechanical fact — "does this mode exist in the
 * build?" — is what the test enforces. So: the *coverage* is mechanical
 * (every mode dir must appear), the *classification* is editorial.
 *
 * The `built` flag is NOT a free-floating comment that rots. It is
 * cross-checked against the actual route table + panel registry by
 * `taxonomy.test.ts`: a mode marked `built: true` here must be reachable
 * (routed in App.tsx or registered as a panel), and vice versa. That is
 * what makes the honest-stub system (WorkflowStub.tsx) data-driven:
 * "is Read's Library built?" is answered by code, not by a maintainer's
 * memory.
 *
 * Cross-references:
 *   - mode set:        src/modes/*  (each dir with an index.tsx, plus
 *                      Write/Editor + Write/Repository which are the
 *                      Write workflow's component modes without an
 *                      index.tsx of their own)
 *   - route table:     src/App.tsx  (canonical "what is mounted")
 *   - panel registry:  src/workspace/PanelRegistry.tsx
 */

export type Workflow = "research" | "read" | "write" | "speak" | "shared";

/** Stable id of a mode. For dir-modes this is the directory name; for the
 *  two Write component modes it is the dotted path "Write/Editor" etc. */
export type ModeId = string;

export interface ModeEntry {
  /** Mode id — matches the directory under src/modes/ (or Write/<X>). */
  id: ModeId;
  /** The workflow this mode belongs to (or `shared` for operator/governance). */
  workflow: Workflow;
  /** One-line operator-readable label (shown in the launcher + ⌘K). */
  label: string;
  /** One-line description of what the mode does. */
  blurb: string;
  /**
   * Whether this mode is reachable in the current build. Cross-checked
   * against App.tsx routes + PanelRegistry by taxonomy.test.ts so it
   * cannot silently rot. Drives the honest-stub logic.
   */
  built: boolean;
  /**
   * Primary route, when the mode is routed. Absent for modes that are
   * panel-only or built-but-not-yet-wired.
   */
  route?: string;
  /**
   * If `shared`, a one-line reason it is cross-cutting rather than
   * force-fit into a workflow. Required for shared entries (enforced by
   * the test) so the bucket can't be abused to hide an orphan.
   */
  sharedReason?: string;
}

/**
 * The four product workflows + the shared bucket, with their content-tree
 * nouns and the default scene route. Drives NavRail (zone 1), ProjectTree
 * (zone 2), and SceneChrome (zone 3).
 */
export interface WorkflowMeta {
  id: Workflow;
  label: string;
  /** One-line statement of the workflow's job (shown in stubs + launcher). */
  tagline: string;
  /**
   * The NOUNS this workflow's content tree shows (zone 2) — the objects
   * the operator works ON, not the tools. Content-first IA.
   */
  nouns: string[];
  /**
   * Route the rail navigates to when the workflow is selected.
   *
   * U-04 DOOR CONTRACT — a workflow's `defaultRoute` opens to an ACTION,
   * not an explanation. The landing must let the user do the workflow's
   * core thing immediately (Research → start a research; Read → open/add a
   * book; Write → start composing; Speak → start a remembrance), never a
   * prose dead-end ("Select or create … to begin") or a bare uploader.
   * Research's StartResearch (PR #10) is the reference. Each product's
   * door-fix sprint owns making its own landing satisfy this; the U-04
   * audit (handoff) records which doors meet it and which are still filed.
   */
  defaultRoute: string;
  /**
   * If the workflow's primary surface isn't built yet, the sprint it
   * ships in — surfaced honestly by WorkflowStub rather than faked.
   */
  shippingSprint?: string;
}

export const WORKFLOWS: Record<Exclude<Workflow, "shared">, WorkflowMeta> = {
  research: {
    id: "research",
    label: "Research",
    tagline: "Investigate a question end-to-end and grade the answer.",
    nouns: ["Investigations", "Chase trees", "Outcomes"],
    defaultRoute: "/",
  },
  read: {
    id: "read",
    label: "Read",
    // Read SPR-06 door re-home: the Read door opens on the Library shelf —
    // "Spotify for books", the home of Read — not the PDF wrestler. The
    // tagline + nouns lead with the shelf you read from, not the uploader
    // you bring sources into (which is now a demoted power affordance,
    // reachable from the Library, not the door).
    tagline: "Open a book and read it with the AI alongside.",
    // SPR-13 M4: "Meta-docs" sits AFTER "Library" — the reader's CREATED
    // deliverables (a Read noun beside the raw library of source books), the
    // meta-docs tab the personal space filters to.
    nouns: ["Library", "Meta-docs", "Notebooks"],
    defaultRoute: "/library",
  },
  write: {
    id: "write",
    label: "Write",
    // Write SPR-07 door re-home: the Write door opens on the real lego-block
    // loop (WriteHome at /write) — pull research notes into an outline,
    // generate a draft from them, edit in the real editor — not the legacy
    // CreationStudio "select or create a deliverable" dead-end (now a demoted
    // power surface at /create, off the door). The tagline + nouns lead with
    // the loop, not the studio.
    tagline: "Pull your notes into an outline, draft from them, then edit.",
    nouns: ["Pieces", "Block repository"],
    defaultRoute: "/write",
  },
  speak: {
    id: "speak",
    label: "Speak",
    // Speak SPR-08: a warm, human tagline + nouns — DeepBlu biography-as-a-
    // service, not "interview-as-acquisition". Someone you want to remember;
    // the people who knew them; the voices they leave.
    tagline: "Remember someone — invite their people and gather their voices.",
    nouns: ["People to remember", "Their people", "Voices"],
    defaultRoute: "/speak",
  },
};

/**
 * THE TAXONOMY. Every mode under src/modes/ (and the two Write component
 * modes) appears exactly once. The completeness test fails if a mode dir
 * exists with no entry here, or an entry references a mode that no longer
 * exists.
 */
export const MODE_TAXONOMY: readonly ModeEntry[] = [
  // ── RESEARCH ──────────────────────────────────────────────────────
  // Wrestle + Brainstorm were rail surfaces in the 5-surface prototype;
  // they fold into Research (the investigation is the unit of work, and
  // brainstorming/parking questions feed it) — except document-wrestling,
  // which is reading and folds into Read (see below).
  {
    id: "ResearchWorkstation",
    workflow: "research",
    label: "Research workstation",
    blurb: "Chat-first investigation surface — the Research home (Mode A).",
    built: true,
    route: "/",
  },
  {
    id: "InvestigationsIndex",
    workflow: "research",
    label: "My research",
    // SPR-05 fold: the old flat /investigations list is folded into the one
    // multi-research monitor (MyResearch, a ResearchWorkstation surface). Its
    // capabilities — list, status, cost, replay — are preserved there. The
    // /investigations path redirects to /my-research, so the canonical route
    // for this surface is now /my-research (the component file is retired from
    // routing, kept on disk so this completeness entry stays honest).
    blurb: "One calm monitor over every running + completed research (SPR-05).",
    built: true,
    route: "/my-research",
  },
  {
    id: "BrainstormStation",
    workflow: "research",
    label: "Brainstorm station",
    blurb: "Watch-for-later + thought-partner; parks questions that feed investigations.",
    built: true,
    route: "/brainstorm",
  },
  {
    id: "Outcomes",
    workflow: "research",
    label: "Outcome",
    blurb: "One investigation's graded outcome (Phase 8 input).",
    built: true,
    route: "/outcomes/:synthesisId",
  },
  {
    id: "OutcomesIndex",
    workflow: "research",
    label: "Outcomes audit",
    blurb: "Cross-investigation grading history.",
    built: true,
    route: "/outcomes",
  },
  {
    id: "Replay",
    workflow: "research",
    label: "Trajectory replay",
    blurb: "Step-by-step replay of an investigation's agent trajectory.",
    built: true,
    route: "/replay/:investigationId",
  },
  {
    id: "Backtest",
    workflow: "research",
    label: "Backtest report",
    blurb: "Backtest a synthesis against held-out outcomes.",
    built: true,
    route: "/backtest/:synthesisId",
  },

  // ── READ ──────────────────────────────────────────────────────────
  // Document-wrestling, the library/document index, sources, and the
  // notebook surface are all "bring sources into the substrate and think
  // about them" — the Read workflow.
  {
    id: "WrestleApp",
    workflow: "read",
    // Read SPR-06: demoted from "the Read home" to a bring-your-own-PDF
    // power surface. It STAYS in the Read workflow (it is reading), but it
    // is no longer the door — the Library is (see read.defaultRoute). It is
    // reachable from the Library's "bring your own PDF" affordance + ⌘K.
    label: "Document wrestler",
    blurb: "Bring your own PDF — read it, select regions, extract claims (power surface; not the Read door).",
    built: true,
    route: "/wrestle",
  },
  // Read SPR-06 operator-surface eviction (mirrors Wave E U-03 "operator
  // behind More"): the tier-filtered Documents index and the bulk-ingest
  // Sources surface are acquisition/governance tools, not the reading door.
  // They move OUT of the Read workflow into the shared/More bucket — the
  // code + routes are untouched (capability preserved), only the
  // classification changes, so they no longer bleed onto the Read door and
  // no longer set the Read rail active. Reachable via More + ⌘K.
  {
    id: "DocumentsIndex",
    workflow: "shared",
    label: "Documents",
    blurb: "Substrate-attached sources by tier (acquisition/governance).",
    built: true,
    route: "/documents",
    sharedReason:
      "Tier-filtered source-management surface (raw ids, ingestion); operator/acquisition tooling, not the reading door (Read SPR-06 eviction).",
  },
  {
    id: "Sources",
    workflow: "shared",
    label: "Sources",
    blurb: "Bulk-add URLs into the substrate graph (acquisition adapters).",
    built: true,
    route: "/sources",
    sharedReason:
      "Bulk source-ingestion (acquisition adapters); operator tooling that spans acquisition, not a reading surface (Read SPR-06 eviction).",
  },
  {
    id: "Notebook",
    workflow: "read",
    label: "Notebook",
    blurb: "Literate-analysis surface — one notebook (Wedge 2 linchpin, Mode F).",
    built: true,
    route: "/notebook/:notebookId",
  },
  {
    id: "NotebooksIndex",
    workflow: "read",
    label: "Notebooks",
    blurb: "Notebooks listing.",
    built: true,
    route: "/notebooks",
  },
  // Read's Spotify-for-books surfaces (merged from read/spotify-for-books at
  // the product consolidation — mapped here so the completeness check passes).
  {
    id: "Library",
    workflow: "read",
    label: "Library",
    blurb: "Servable book/document library — the Spotify-for-books shelf.",
    built: true,
    route: "/library",
  },
  {
    id: "Reading",
    workflow: "read",
    label: "Reader",
    blurb: "Full-text book reader (deny-by-default servability gate).",
    built: true,
    route: "/read/:documentId",
  },
  // DRW glass-box monitor (research workflow; merged with the DRW product).
  {
    id: "DeepResearchWorkspace",
    workflow: "research",
    label: "Deep Research Workspace",
    blurb: "Glass-box monitor for cascaded parallel researches (DRW SPR-09).",
    built: true,
    route: "/deep-research",
  },

  // ── WRITE ─────────────────────────────────────────────────────────
  // Write SPR-07: the door is the real lego-block loop — WriteHome at /write
  // composes the block repository (tap-to-add picker) + the legible outline +
  // the real editor + the brainstorm on-ramp. The Write SPR-03/04 component
  // modes (Repository, Editor) are now MOUNTED inside that surface, so they
  // are reachable (built=true, route=/write — the door they live on). The
  // legacy CreationStudio is demoted to a power surface at /create (still
  // Write — it IS writing — but off the door; capability untouched).
  {
    id: "CreationStudio",
    workflow: "write",
    // Write SPR-07: demoted from "the Write home" to a power surface. It stays
    // in Write, reachable at /create + ⌘K, but it is no longer the door — the
    // real loop (WriteHome) is. (The "attach by id" dead-end the experience-
    // spec flagged is bypassed by the door re-home, not the studio's own code.)
    label: "Creation studio",
    blurb: "Section-based writing surface (power surface; not the Write door).",
    built: true,
    route: "/create",
  },
  {
    id: "Write/Repository",
    workflow: "write",
    label: "Block repository",
    blurb: "Tap-to-add block picker the Write loop composes from (Write SPR-03; routed SPR-07).",
    // Mounted inside WriteHome — reachable on the Write door (/write).
    built: true,
    route: "/write",
  },
  {
    id: "Write/Editor",
    workflow: "write",
    label: "Write editor",
    blurb: "Real structured block editor where the generated draft lands (Write SPR-04; mounted SPR-07).",
    // Mounted inside WriteHome — reachable on the Write door (/write).
    built: true,
    route: "/write",
  },

  // ── SPEAK ─────────────────────────────────────────────────────────
  // Interview (the 5-surface prototype's Interview surface) + the Speak
  // biography console + invites all fold into Speak.
  {
    id: "SpeakIndex",
    workflow: "speak",
    label: "Speak",
    blurb: "Biography-project surface — the Speak home.",
    built: true,
    route: "/speak",
  },
  {
    id: "Speak",
    workflow: "speak",
    label: "Speak project console",
    blurb: "One biography project: invite, capture, corroborate, draft.",
    built: true,
    route: "/speak/:projectId",
  },
  {
    id: "SpeakInvite",
    workflow: "speak",
    label: "Speak invite (landing)",
    blurb: "Friends-and-family invitee landing — unauthenticated, token-credentialed.",
    built: true,
    route: "/speak/invite/:token",
  },
  // SPR-11 — the Biography TEMPLATE. NOT a fifth workflow: a biography
  // composes Research + Write + Speak over the ONE graph, so it is classified
  // under Speak (the talk/voices surface it leads into), reachable from the
  // home's "Start a biography" card — never a fifth rail door (that would
  // imply a fifth product/graph, which the template-not-silo decision rejects;
  // see docs/decisions/spr-11-biography-template-not-graph.md).
  {
    id: "Biography",
    workflow: "speak",
    label: "Biography",
    blurb: "Start a biography — composes research, writing, and gathered voices over the one workspace (SPR-11).",
    built: true,
    route: "/biography",
  },
  // Speak SPR-08 ONE DOOR: the Interview surface folds into Speak (mirrors the
  // SPR-05 InvestigationsIndex fold). The capture/transcript/corroboration
  // capability is preserved inside the Speak console; routing is retired to
  // /speak (/interviews and /interview/:id both redirect there — App.tsx
  // InterviewRedirect). InterviewIndex (below) is the one surviving Interview
  // MODE (real modes/InterviewIndex/index.tsx) and carries the taxonomy entry.
  //
  // There is NO separate "Interview" entry: the SPR-08 draft kept one, but the
  // recording-mode index (modes/Interview/index.tsx) was retired in AGH SPR-02
  // M6, and the SPR-04-rigor completeness gate (taxonomy.test.ts) — the current
  // enforced standard — requires every entry to map to a real modes/*/index.tsx.
  // A phantom "Interview" entry pointing at /speak would be exactly the stale
  // entry that gate exists to catch. The InterviewTranscript/InterviewNotes
  // components stay on disk as registered panels; they are not a routed mode.
  {
    id: "InterviewIndex",
    workflow: "speak",
    label: "Interviews",
    blurb: "Projects + invited informants — folded into the Speak home (SPR-08).",
    built: true,
    route: "/speak",
  },

  // ── SHARED / OPERATOR / GOVERNANCE ────────────────────────────────
  // Genuinely cross-cutting surfaces: they don't belong to one workflow.
  // Each carries a one-line reason; the test forbids a shared entry with
  // no reason so the bucket can't be used to hide an orphan.
  {
    id: "Login",
    workflow: "shared",
    label: "Login",
    blurb: "Magic-link login page.",
    built: true,
    route: "/login",
    sharedReason: "Auth gate — precedes any workflow; not part of one.",
  },
  {
    id: "Settings",
    workflow: "shared",
    label: "Settings",
    blurb: "Operator settings.",
    built: true,
    route: "/settings",
    sharedReason: "Cross-cutting operator preferences.",
  },
  {
    id: "OperatorDashboard",
    workflow: "shared",
    label: "Operator dashboard",
    blurb: "Operator control surface (IP escrow, system status).",
    built: true,
    route: "/operator",
    sharedReason: "Operator-only control plane spanning all workflows.",
  },
  {
    id: "TrustCenter",
    workflow: "shared",
    label: "Trust Center",
    blurb: "Public ε budgets · deletion SLA · unlock status.",
    built: true,
    route: "/trust",
    sharedReason: "Public trust/governance surface; not workflow-scoped.",
  },
  // Own Your Mind P0 (docs/own-your-mind/10-p0-implementation-brief.md) —
  // three read-only provenance/governance surfaces. Explain is a param route
  // (a detail surface reached from claims/syntheses/documents, not from the
  // launcher); ObjectiveCard + Signals are bare routes and appear in More.
  {
    id: "Explain",
    workflow: "shared",
    label: "Explain provenance",
    blurb: "Why this claim / what grounded this synthesis / who cites this document (read-only).",
    built: true,
    route: "/explain/:kind/:id",
    sharedReason: "Read-only provenance chain over claims, syntheses, and documents from every workflow.",
  },
  {
    id: "ObjectiveCard",
    workflow: "shared",
    label: "Objective card",
    blurb: "Live dispatch matrix · gap scoring · gates · budgets (read-only).",
    built: true,
    route: "/objective",
    sharedReason: "Operator-owned objective rendering; spans all workflows.",
  },
  {
    id: "Signals",
    workflow: "shared",
    label: "Signal inventory",
    blurb: "Every event ActionType with payload class and emitter (read-only).",
    built: true,
    route: "/signals",
    sharedReason: "Audit/governance inventory over the event schema; not workflow-scoped.",
  },
  {
    id: "PrivacyDashboard",
    workflow: "shared",
    label: "Privacy",
    blurb: "ε exposure + delete-all controls.",
    built: true,
    route: "/privacy",
    sharedReason: "Governance — privacy controls cut across all data.",
  },
  {
    id: "Pricing",
    workflow: "shared",
    label: "Pricing",
    blurb: "OpenRouter-style cost calculator.",
    built: true,
    route: "/pricing",
    sharedReason: "Commercial/marketing surface; not a workflow tool.",
  },
  {
    id: "Billing",
    workflow: "shared",
    label: "Billing",
    blurb: "Free-tier usage + margin breakdown.",
    built: true,
    route: "/billing",
    sharedReason: "Account billing — cross-cutting commercial surface.",
  },
  {
    id: "Stats",
    workflow: "shared",
    label: "Substrate stats",
    blurb: "Per-table cardinality dashboard.",
    built: true,
    route: "/stats",
    sharedReason: "Substrate observability spanning all workflows.",
  },
  {
    id: "Map",
    workflow: "shared",
    label: "Application map",
    blurb: "Index of every operator-facing surface.",
    built: true,
    route: "/map",
    sharedReason: "Meta-navigation over the whole app.",
  },
  {
    id: "Multimedia",
    workflow: "shared",
    label: "Multimedia",
    blurb: "Plan and steer grounded audio/video explainers before paid media generation.",
    built: true,
    route: "/multimedia",
    sharedReason:
      "Generated information media composes Research, Read, Write, and Speak assets; routed as a cross-workflow product surface until the global workflow model is expanded.",
  },
  {
    id: "Loop3",
    workflow: "shared",
    label: "Loop 3 checklist",
    blurb: "RL-unlock criteria + env gate.",
    built: true,
    route: "/loop-3",
    sharedReason: "Operator governance gate (RL unlock); not a workflow.",
  },
  {
    id: "SkillRules",
    workflow: "shared",
    label: "Skill rules",
    blurb: "Cross-user promoted skill rules.",
    built: true,
    route: "/skill-rules",
    sharedReason: "Substrate governance — promoted rules span workflows.",
  },
  {
    id: "SkillRuleDetail",
    workflow: "shared",
    label: "Skill rule detail",
    blurb: "One promoted skill rule's detail.",
    built: true,
    route: "/skill-rules/:ruleId",
    sharedReason: "Detail view of a shared governance object.",
  },
  {
    id: "Federation",
    workflow: "shared",
    label: "Federation config",
    blurb: "Cross-substrate federation policy.",
    built: true,
    route: "/federation",
    sharedReason: "Cross-substrate governance (Phase 3); not workflow-scoped.",
  },
  {
    // antiek-unified SPR-05 (gate ledger + roadmap) + SPR-07 (cost + consent).
    // One coordination surface spanning all four workflows — gate state, the
    // 45-sprint roadmap, unified cost, and per-IP-holder escrow/consent. Read-
    // only governance, so it lives in the shared bucket, not one workflow.
    id: "Coordination",
    workflow: "shared",
    label: "Coordination",
    blurb: "Gate ledger · roadmap · unified cost · escrow/consent (read-only).",
    built: true,
    route: "/coordination",
    sharedReason:
      "Cross-workflow governance (gates, roadmap, cost, escrow/consent); spans all four workflows.",
  },
  {
    id: "CrossGraphCitations",
    workflow: "shared",
    label: "Cross-graph citations",
    blurb: "Record cross-graph citations + rev-share.",
    built: true,
    route: "/cross-graph/citations",
    sharedReason: "Cross-graph IP-attribution mechanism; spans workflows.",
  },
  {
    id: "PayoutsAudit",
    workflow: "shared",
    label: "Payouts audit",
    blurb: "Stripe Connect transfer log.",
    built: true,
    route: "/payouts",
    sharedReason: "IP-economics audit; governance, not a workflow tool.",
  },
  // AGH SPR-03: the four never-routed ad-economics orphan surfaces
  // (AdvertiserConsole, CreatorPayouts, PayoutDashboard, MarketplaceMetrics)
  // were deleted — each fetched a backend route that does not exist and
  // rendered a shape no real route returns. The live §9 economics surfaces
  // are OperatorDashboard (/operator) and PayoutsAudit (/payouts) above.
  // Precise on CreatorPayouts (review note): PayoutsAudit is a COMPANION
  // surface (operator transfer-log audit at /payouts/transfers), NOT a
  // replacement for a creator self-service view — and a real
  // /creator-payouts/{recipient_ref} route DOES exist, just with a
  // different shape (rollover_balance_cents / kyc_state / total_paid_cents)
  // than the orphan rendered. Revival = a self-service view repointed at
  // that real route, not a claim that PayoutsAudit already covers it. The
  // deleted vision + its required backend contract is preserved in the
  // deletion commit body for a future ad-economics sprint to rebuild
  // against a real route.
];

/** All workflow ids, in rail order. */
export const WORKFLOW_ORDER: readonly Exclude<Workflow, "shared">[] = [
  "research",
  "read",
  "write",
  "speak",
];

const BY_ID = new Map<ModeId, ModeEntry>(
  MODE_TAXONOMY.map((m) => [m.id, m]),
);

/** Look up a mode entry by id. */
export function modeById(id: ModeId): ModeEntry | undefined {
  return BY_ID.get(id);
}

/** Every mode that belongs to a workflow (in declaration order). */
export function modesForWorkflow(workflow: Workflow): ModeEntry[] {
  return MODE_TAXONOMY.filter((m) => m.workflow === workflow);
}

/**
 * Build presence for a workflow: is ANY of its modes reachable in the
 * current build? Used by WorkflowStub to decide whether to show a real
 * scene or an honest "not yet" state. Data-driven — reads the `built`
 * flags (which the test pins to the real route/panel registry), never a
 * hardcoded list.
 */
export function workflowHasBuiltMode(workflow: Workflow): boolean {
  return MODE_TAXONOMY.some((m) => m.workflow === workflow && m.built);
}

/**
 * The workflow's landing scene — the mode the door (and ThreadJump) opens.
 *
 * It MUST agree with `WORKFLOWS[workflow].defaultRoute` so a door re-home is
 * honored in exactly one place: when a built mode's route matches the
 * workflow's defaultRoute, that mode is the landing (e.g. Read SPR-06 set
 * read.defaultRoute = /library, so the Library — not the first-declared
 * Read mode, the demoted PDF wrestler — is the landing). Falls back to the
 * first built+routed mode only when no mode owns the default route.
 */
export function landingModeForWorkflow(workflow: Workflow): ModeEntry | undefined {
  if (workflow !== "shared") {
    const wantRoute = WORKFLOWS[workflow].defaultRoute;
    const onDefault = MODE_TAXONOMY.find(
      (m) => m.workflow === workflow && m.built && m.route === wantRoute,
    );
    if (onDefault) return onDefault;
  }
  return MODE_TAXONOMY.find(
    (m) => m.workflow === workflow && m.built && Boolean(m.route),
  );
}

/**
 * Single source of truth for the rail boundary. Returns true exactly when
 * the workflow is one of the four members of WORKFLOW_ORDER. The shared
 * bucket (every operator, admin, settings, governance, trust, billing,
 * privacy and cross-cutting surface) is false and must never be rendered
 * by the NavRail. This predicate is the only definition of "rail
 * destination." The U-01 count guard and the U-03 off-the-rail guard both
 * import and call it so the two tests agree on the boundary and a future
 * reclassification cannot create a gap. Change the rail set in one place
 * only; the guards follow.
 */
export function isWorkflowDestination(
  wf: Workflow,
): wf is Exclude<Workflow, "shared"> {
  return WORKFLOW_ORDER.includes(wf as Exclude<Workflow, "shared">);
}

// SPR-13 M4: the personal-space surfaces (the Read personal bed + the meta-docs
// tab) are sub-surfaces of the Reading mode (no own MODE_TAXONOMY entry, like
// MetaReading), but they ARE Read-workflow destinations — so the active rail
// highlights Read when the operator is on them. Listed here so workflowForPath
// resolves them without a (would-be-stale) taxonomy entry.
const READ_SUBSURFACE_ROUTES: ReadonlyArray<{ workflow: Workflow; prefix: string }> = [
  { workflow: "read", prefix: "/readings" },
  { workflow: "read", prefix: "/meta-readings" },
  { workflow: "read", prefix: "/read/meta-reading" },
];

/** Resolve which workflow a pathname belongs to (for active-rail state). */
export function workflowForPath(pathname: string): Workflow {
  // Longest-prefix match against routed modes. Strip params for matching.
  const candidates = [
    ...MODE_TAXONOMY.filter((m) => m.route).map((m) => ({
      workflow: m.workflow,
      // Convert "/speak/:projectId" → "/speak" prefix.
      prefix: m.route!.replace(/\/:.*/, ""),
    })),
    ...READ_SUBSURFACE_ROUTES,
  ];
  // Sort by prefix length desc so "/speak/invite" beats "/speak".
  candidates.sort((a, b) => b.prefix.length - a.prefix.length);
  for (const c of candidates) {
    if (c.prefix === "/" ) continue; // handle root last
    if (pathname === c.prefix || pathname.startsWith(c.prefix + "/")) {
      return c.workflow;
    }
  }
  if (pathname === "/" || pathname === "") return "research";
  return "research";
}
