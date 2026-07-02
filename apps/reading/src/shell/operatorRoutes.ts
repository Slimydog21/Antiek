import type { Workflow } from "./workflowTaxonomy";

export type OperatorRouteGroup =
  | "Home"
  | "Research"
  | "Read"
  | "Write"
  | "Speak"
  | "Governance"
  | "Audit + analytics"
  | "Pricing + replay";

export interface OperatorRouteEntry {
  id: string;
  group: OperatorRouteGroup;
  path: string;
  title: string;
  description: string;
  paletteSubtitle?: string;
  workflow?: Workflow;
}

export const OPERATOR_ROUTE_GROUP_ORDER: OperatorRouteGroup[] = [
  "Home",
  "Research",
  "Read",
  "Write",
  "Speak",
  "Governance",
  "Audit + analytics",
  "Pricing + replay",
];

export const OPERATOR_ROUTES: OperatorRouteEntry[] = [
  {
    id: "home",
    group: "Home",
    path: "/home",
    title: "Antiek home",
    description: "Front door to the four workflows",
    paletteSubtitle: "Front door to the four workflows (/home)",
    workflow: "shared",
  },
  {
    id: "research",
    group: "Research",
    path: "/",
    title: "Research workstation",
    description: "Mode A — chat-first investigation surface",
    paletteSubtitle: "Mode A — chat-first investigation surface (/)",
  },
  {
    id: "deep-research",
    group: "Research",
    path: "/deep-research",
    title: "Deep Research Workspace",
    description: "Cascade monitor and steerable research sessions",
  },
  {
    id: "brainstorm",
    group: "Research",
    path: "/brainstorm",
    title: "Brainstorm station",
    description: "Mode E — watch-for-later + thought partner",
    paletteSubtitle: "Mode E — watch-for-later + thought-partner (/brainstorm)",
  },
  {
    id: "my-research",
    group: "Research",
    path: "/my-research",
    title: "My research",
    description: "One monitor over running + completed research",
    paletteSubtitle: "One monitor over every running + completed research (/my-research)",
  },
  {
    id: "wrestle",
    group: "Read",
    path: "/wrestle",
    title: "Document wrestler",
    description: "Mode B — PDF reading + region selection",
    paletteSubtitle: "Mode B — PDF reading + region selection (/wrestle)",
  },
  {
    id: "library",
    group: "Read",
    path: "/library",
    title: "Library",
    description: "Read shelf over the servable corpus",
  },
  {
    id: "library-browse",
    group: "Read",
    path: "/library/browse",
    title: "Library browse",
    description: "Paginated catalog over every servable work",
  },
  {
    id: "readings",
    group: "Read",
    path: "/readings",
    title: "Your readings",
    description: "Saved reads and created deliverables",
  },
  {
    id: "meta-readings",
    group: "Read",
    path: "/meta-readings",
    title: "All meta-docs",
    description: "Created deliverables only",
  },
  {
    id: "meta-reading",
    group: "Read",
    path: "/read/meta-reading",
    title: "Meta-reading",
    description: "Proposed — sign-off pending",
    paletteSubtitle: "Proposed — sign-off pending (/read/meta-reading)",
  },
  {
    id: "notebooks",
    group: "Read",
    path: "/notebooks",
    title: "Notebooks",
    description: "Wedge 2 literate-analysis surface",
  },
  {
    id: "write",
    group: "Write",
    path: "/write",
    title: "Write home",
    description: "Blocks → outline → draft → editor loop",
  },
  {
    id: "create",
    group: "Write",
    path: "/create",
    title: "Creation studio",
    description: "Mode C — lego-block writing",
    paletteSubtitle: "Mode C — Lego-block writing (/create)",
  },
  {
    id: "speak",
    group: "Speak",
    path: "/speak",
    title: "Speak",
    description: "One door for interview projects + invited voices",
    paletteSubtitle: "Remember someone — invite their people, gather their voices (/speak)",
  },
  {
    id: "biography",
    group: "Speak",
    path: "/biography",
    title: "Biography",
    description: "Template that composes Research, Write, and Speak",
  },
  {
    id: "skill-rules",
    group: "Governance",
    path: "/skill-rules",
    title: "Skill rules",
    description: "Cross-user discovered rules",
    paletteSubtitle: "Cross-user promoted rules (/skill-rules)",
  },
  {
    id: "privacy",
    group: "Governance",
    path: "/privacy",
    title: "Privacy dashboard",
    description: "Privacy budgets and deletion controls",
  },
  {
    id: "trust",
    group: "Governance",
    path: "/trust",
    title: "Trust Center",
    description: "Published privacy, deletion, and training commitments",
  },
  {
    id: "settings",
    group: "Governance",
    path: "/settings",
    title: "Settings",
    description: "Application settings and control links",
  },
  {
    id: "coordination",
    group: "Governance",
    path: "/coordination",
    title: "Coordination",
    description: "Gate ledger, roadmap, unified cost, escrow, and consent",
  },
  {
    id: "documents",
    group: "Governance",
    path: "/documents",
    title: "Documents",
    description: "Substrate-attached sources by tier (acquisition/governance)",
    paletteSubtitle: "Substrate-attached sources by tier (/documents)",
  },
  {
    id: "sources",
    group: "Governance",
    path: "/sources",
    title: "Sources",
    description: "Bulk source-ingestion adapters (acquisition/governance)",
  },
  {
    id: "cost-consent",
    group: "Governance",
    path: "/coordination/cost-consent",
    title: "Cost & consent",
    description: "Unified spend, escrow, and consent status",
  },
  {
    id: "federation",
    group: "Governance",
    path: "/federation",
    title: "Federation config",
    description: "Cross-substrate citation policy (§13.9 Phase 3)",
    paletteSubtitle: "Cross-substrate policy (/federation)",
  },
  {
    id: "cross-graph-citations",
    group: "Governance",
    path: "/cross-graph/citations",
    title: "Cross-graph citations",
    description: "Record citations and revenue share",
    paletteSubtitle: "Record citations + rev-share (/cross-graph/citations)",
  },
  {
    id: "loop3",
    group: "Governance",
    path: "/loop-3",
    title: "Loop 3 checklist",
    description: "RL unlock criteria + env gate (§14.2)",
  },
  {
    id: "operator",
    group: "Governance",
    path: "/operator",
    title: "Operator dashboard",
    description: "Composite operator-facing snapshot",
  },
  {
    id: "advertiser-console",
    group: "Governance",
    path: "/operator/advertiser-campaigns",
    title: "Advertiser console",
    description: "Operator-managed lead-gen campaigns",
  },
  {
    id: "payout-dashboard",
    group: "Governance",
    path: "/operator/payouts/dashboard",
    title: "Payout dashboard",
    description: "Unified creator + publisher accrual view",
  },
  {
    id: "creator-payouts",
    group: "Governance",
    path: "/me/payouts",
    title: "Creator payouts",
    description: "Your scoped creator payout ledger",
  },
  {
    id: "marketplace",
    group: "Governance",
    path: "/marketplace",
    title: "Marketplace metrics",
    description: "Creator, publisher, and advertiser health snapshot",
  },
  {
    id: "stats",
    group: "Audit + analytics",
    path: "/stats",
    title: "Substrate stats",
    description: "Per-table cardinality dashboard",
  },
  {
    id: "outcomes-index",
    group: "Audit + analytics",
    path: "/outcomes",
    title: "Outcomes audit",
    description: "Cross-investigation grading history",
  },
  {
    id: "payouts",
    group: "Audit + analytics",
    path: "/payouts",
    title: "Payouts audit",
    description: "Stripe Connect transfer log",
  },
  {
    id: "billing",
    group: "Audit + analytics",
    path: "/billing",
    title: "Billing",
    description: "Free-tier usage + margin breakdown",
  },
  {
    id: "pricing",
    group: "Pricing + replay",
    path: "/pricing",
    title: "Pricing",
    description: "OpenRouter-style pay-as-you-go calculator",
    paletteSubtitle: "OpenRouter-style calculator (/pricing)",
  },
  {
    id: "map",
    group: "Pricing + replay",
    path: "/map",
    title: "Application map",
    description: "Index of every operator-facing surface",
  },
];

export function operatorRouteGroups(): { title: OperatorRouteGroup; routes: OperatorRouteEntry[] }[] {
  return OPERATOR_ROUTE_GROUP_ORDER.map((title) => ({
    title,
    routes: OPERATOR_ROUTES.filter((route) => route.group === title),
  }));
}

export function operatorRouteForPath(path: string): OperatorRouteEntry | undefined {
  return OPERATOR_ROUTES.find((route) => route.path === path);
}
