/**
 * projects.ts — the project registry wire module (THREAD-CONTRACT §1.5, lane B).
 *
 * A project is a `write_folders` row, owner-scoped on the server; another
 * owner's project answers 404 exactly like a missing one. A `reading`
 * project is a standalone book with `primary_document_id`, promoted in
 * place to `project` (never back). Members are soft, typed edges.
 *
 * The vocabularies here are the rev-7 sets; contract rev 9 extends them
 * (per-product projects) without changing these shapes.
 */
import { API_BASE, ApiError, apiFetch } from "../api";

/**
 * Whether the "create a project from a seed" contract is live (FFX-KPA SPR-03
 * M6). False until SPR-B's ffx-nav-backend-intake publishes the project-seed
 * response and the project-creation decision; until then the zen home skips
 * POST /projects and the investigation id doubles as the project id.
 * TODO(ffx-nav-backend-intake): flip when the intake contract lands.
 */
export const PROJECT_SEED_CONTRACT_LIVE = false;

export type ProjectKind = "project" | "reading";
export type MemberKind = "node" | "investigation" | "document" | "deliverable";

export interface Project {
  project_id: string;
  title: string;
  kind: ProjectKind;
  order: number;
  pinned: boolean;
  archived_at: string | null;
  primary_document_id: string | null;
  created_at: string;
  updated_at: string | null;
  member_count: number;
}

export interface ProjectMember {
  member_kind: MemberKind;
  member_id: string;
  added_at: string;
}

export interface ProjectDetail extends Project {
  members: ProjectMember[];
}

export interface CreateProjectBody {
  title: string;
  kind?: ProjectKind;
  primary_document_id?: string;
}

/** Only the fields sent change. `kind` accepts only the reading → project promotion. */
export interface PatchProjectBody {
  title?: string;
  order?: number;
  pinned?: boolean;
  archived?: boolean;
  kind?: "project";
}

const isObject = (v: unknown): v is Record<string, unknown> =>
  typeof v === "object" && v !== null && !Array.isArray(v);

function isProject(v: unknown): v is Project {
  return (
    isObject(v) &&
    typeof v.project_id === "string" &&
    typeof v.title === "string" &&
    (v.kind === "project" || v.kind === "reading") &&
    typeof v.order === "number" &&
    typeof v.pinned === "boolean" &&
    (v.archived_at === null || typeof v.archived_at === "string") &&
    (v.primary_document_id === null || typeof v.primary_document_id === "string") &&
    typeof v.created_at === "string" &&
    (v.updated_at === null || typeof v.updated_at === "string") &&
    typeof v.member_count === "number"
  );
}

function parseProject(raw: unknown): Project {
  if (!isProject(raw)) throw new ApiError("projects: malformed project", 0, JSON.stringify(raw));
  return raw;
}

async function send(what: string, url: string, init?: RequestInit): Promise<unknown> {
  const resp = await apiFetch(url, init);
  if (!resp.ok) throw new ApiError(`${what} failed: HTTP ${resp.status}`, resp.status, await resp.text());
  return resp.json();
}

const json = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

const projectUrl = (projectId: string, suffix = "") =>
  `${API_BASE}/projects/${encodeURIComponent(projectId)}${suffix}`;

export async function listProjects(opts: { includeArchived?: boolean } = {}): Promise<Project[]> {
  const raw = await send(
    "GET /projects",
    `${API_BASE}/projects${opts.includeArchived ? "?include_archived=true" : ""}`,
  );
  if (!isObject(raw) || !Array.isArray(raw.projects)) {
    throw new ApiError("projects: malformed list", 0, JSON.stringify(raw));
  }
  return raw.projects.map(parseProject);
}

export async function createProject(body: CreateProjectBody): Promise<Project> {
  return parseProject(await send("POST /projects", `${API_BASE}/projects`, json("POST", body)));
}

export async function getProject(projectId: string): Promise<ProjectDetail> {
  const raw = await send("GET /projects/{id}", projectUrl(projectId));
  const project = parseProject(raw);
  const members = (raw as { members?: unknown }).members;
  if (!Array.isArray(members) || !members.every((m) => isObject(m) && typeof m.member_id === "string")) {
    throw new ApiError("projects: malformed members", 0, JSON.stringify(raw));
  }
  return { ...project, members: members as ProjectMember[] };
}

export async function patchProject(projectId: string, body: PatchProjectBody): Promise<Project> {
  return parseProject(await send("PATCH /projects/{id}", projectUrl(projectId), json("PATCH", body)));
}

export async function addProjectMember(
  projectId: string,
  member: { member_kind: MemberKind; member_id: string },
): Promise<"added" | "already_member"> {
  const raw = await send("POST /projects/{id}/members", projectUrl(projectId, "/members"), json("POST", member));
  if (!isObject(raw) || (raw.status !== "added" && raw.status !== "already_member")) {
    throw new ApiError("projects: malformed member answer", 0, JSON.stringify(raw));
  }
  return raw.status;
}

export async function removeProjectMember(projectId: string, memberId: string): Promise<"removed" | "not_member"> {
  const raw = await send(
    "DELETE /projects/{id}/members/{member}",
    projectUrl(projectId, `/members/${encodeURIComponent(memberId)}`),
    { method: "DELETE" },
  );
  if (!isObject(raw) || (raw.status !== "removed" && raw.status !== "not_member")) {
    throw new ApiError("projects: malformed member answer", 0, JSON.stringify(raw));
  }
  return raw.status;
}
