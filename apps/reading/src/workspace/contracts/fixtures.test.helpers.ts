/**
 * fixtures.test.helpers.ts — shared fixtures for the contracts tests. Not a
 * test file (vitest collects `*.test.ts`, not `*.test.helpers.ts`), and
 * excluded from the census scans by its `.test.` infix. It builds RAW wire
 * rows only (projects, investigation summaries, companion tabs); contract
 * nodes come from the adapter under test, never from a hand-written
 * `source.kind` literal here.
 */
import type { InvestigationSummary } from "../../lib/api";
import type { Project, ProjectMember } from "../../lib/api/projects";
import type { AgentTabDescriptor } from "../companionStore";
import type { PreBackendInputs } from "./adapters/preBackend";

export function project(id: string, title: string, over: Partial<Project> = {}): Project {
  return {
    project_id: id,
    title,
    kind: "project",
    order: 1,
    pinned: false,
    archived_at: null,
    primary_document_id: null,
    created_at: "2026-09-01T00:00:00Z",
    updated_at: null,
    member_count: 0,
    ...over,
  };
}

export function summary(id: string, over: Partial<InvestigationSummary> = {}): InvestigationSummary {
  return {
    investigation_id: id,
    question: `Question ${id}`,
    status: "completed",
    started_at: "2026-09-10T10:00:00Z",
    completed_at: "2026-09-10T11:00:00Z",
    cost_usd_total: 0.1,
    parent_investigation_id: null,
    ...over,
  };
}

let seq = 0;
export function tab(kind: AgentTabDescriptor["kind"], over: Partial<AgentTabDescriptor> = {}): AgentTabDescriptor {
  seq += 1;
  const id = kind === "research-thread" ? `agent:thread:${over.investigationId ?? ""}` : "agent:dialogue";
  return { id, kind, title: over.title ?? kind, seq, ...over };
}

/** A cycle-free forest: root → child; an orphan whose parent is outside the
 *  list; a registry-member root. Newest-first order under default is
 *  inv-child? no: inv-child is nested. Roots by started_at desc:
 *  inv-root (09-20), inv-orphan (09-19), inv-member (09-18). */
export const SUMMARIES_ACYCLIC: InvestigationSummary[] = [
  summary("inv-member", { started_at: "2026-09-18T10:00:00Z", completed_at: null, status: "in_progress", question: "Member question" }),
  summary("inv-root", { started_at: "2026-09-20T10:00:00Z", completed_at: "2026-09-20T12:00:00Z" }),
  summary("inv-child", { parent_investigation_id: "inv-root", started_at: "2026-09-21T10:00:00Z", completed_at: null, status: "in_progress" }),
  summary("inv-child-2", { parent_investigation_id: "inv-root", started_at: "2026-09-22T10:00:00Z", status: "failed", completed_at: "2026-09-22T10:30:00Z" }),
  summary("inv-orphan", { parent_investigation_id: "inv-gone", started_at: "2026-09-19T10:00:00Z" }),
];

/** The acyclic forest plus a 2-cycle and a self-parent. */
export const SUMMARIES: InvestigationSummary[] = [
  ...SUMMARIES_ACYCLIC,
  summary("inv-cycle-a", { parent_investigation_id: "inv-cycle-b", started_at: "2026-09-15T10:00:00Z" }),
  summary("inv-cycle-b", { parent_investigation_id: "inv-cycle-a", started_at: "2026-09-14T10:00:00Z" }),
  summary("inv-self", { parent_investigation_id: "inv-self", started_at: "2026-09-13T10:00:00Z" }),
];

export const PROJECTS: Project[] = [
  project("p1", "Varda diligence", { member_count: 3 }),
  project("p2", "Second project", { member_count: 0, order: 2 }),
];

export function tabs(): AgentTabDescriptor[] {
  return [
    tab("research-thread", { investigationId: "inv-child", documentId: "doc-1", title: "child thread" }),
    tab("dialogue"),
    tab("research-thread", { investigationId: "inv-unknown", title: "unknown thread" }),
    tab("research-thread", { investigationId: "inv-member", title: "member thread" }),
  ];
}

export const MEMBERS_P1: ProjectMember[] = [
  { member_kind: "investigation", member_id: "inv-member", added_at: "2026-09-18T10:00:00Z" },
  { member_kind: "document", member_id: "doc-x", added_at: "2026-09-18T10:00:00Z" },
];

export function fixtureInputs(over: Partial<PreBackendInputs> = {}): PreBackendInputs {
  return {
    projects: PROJECTS,
    investigations: SUMMARIES,
    localParents: {},
    companionTabs: tabs(),
    ...over,
  };
}

export function fixtureInputsWithMembers(over: Partial<PreBackendInputs> = {}): PreBackendInputs {
  return fixtureInputs({ membersByProject: new Map([["p1", MEMBERS_P1]]), ...over });
}
