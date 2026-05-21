// SPR-06 / M3 — Tags client (localStorage-backed for this sprint).
//
// Sister module to folders.ts. Tags are flat (no nesting, no
// hierarchy). The DDL lives in
// services/library/migrations/0001_folders_tags.sql; until a
// services/library/migrations runner + a FastAPI handler land, this
// module persists tags + document↔tag edges in localStorage.
//
// Tag naming convention: lowercased + trimmed on insert. Two tags
// with the same lowercased name collapse onto the same tag_id —
// "ML" and "ml" are the same tag. This matters for the multi-select
// "Add to tag" affordance: typing "ML" then "Machine Learning" then
// "ml" must not produce three rows.

const TAGS_KEY = "antiek.library.tags.v1";
const DOC_TAGS_KEY = "antiek.library.documentTags.v1";

export interface Tag {
  tag_id: string;
  owner_user_id: string;
  name: string;
  created_at: string;
}

export interface DocumentTagEdge {
  document_id: string;
  tag_id: string;
  added_at: string;
}

function readTags(): Tag[] {
  if (typeof window === "undefined" || !window.localStorage) return [];
  const raw = window.localStorage.getItem(TAGS_KEY);
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw) as unknown;
    return Array.isArray(parsed) ? (parsed as Tag[]) : [];
  } catch {
    return [];
  }
}

function writeTags(tags: Tag[]): void {
  if (typeof window === "undefined" || !window.localStorage) return;
  window.localStorage.setItem(TAGS_KEY, JSON.stringify(tags));
}

function readEdges(): DocumentTagEdge[] {
  if (typeof window === "undefined" || !window.localStorage) return [];
  const raw = window.localStorage.getItem(DOC_TAGS_KEY);
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw) as unknown;
    return Array.isArray(parsed) ? (parsed as DocumentTagEdge[]) : [];
  } catch {
    return [];
  }
}

function writeEdges(edges: DocumentTagEdge[]): void {
  if (typeof window === "undefined" || !window.localStorage) return;
  window.localStorage.setItem(DOC_TAGS_KEY, JSON.stringify(edges));
}

function newTagId(): string {
  const hex = Math.floor(Math.random() * 0xffffffffffff)
    .toString(16)
    .padStart(12, "0");
  return `tag-${hex}`;
}

/** Normalise a user-typed tag name. Lowercased + trimmed; empty
 * strings reject in the caller. */
function normaliseTagName(raw: string): string {
  return raw.trim().toLowerCase();
}

/** List all tags for the current user. */
export async function listTags(): Promise<Tag[]> {
  const tags = readTags().slice();
  tags.sort((a, b) => a.name.localeCompare(b.name));
  return tags;
}

/** Create a tag if it doesn't exist, return it; otherwise return the
 * existing tag with the same normalised name. Idempotent by name. */
export async function getOrCreateTag(name: string): Promise<Tag> {
  const norm = normaliseTagName(name);
  if (!norm) {
    throw new Error("tag name cannot be empty");
  }
  const existing = readTags();
  const match = existing.find((t) => t.name === norm);
  if (match) return match;
  const tag: Tag = {
    tag_id: newTagId(),
    owner_user_id: "__operator__",
    name: norm,
    created_at: new Date().toISOString(),
  };
  existing.push(tag);
  writeTags(existing);
  return tag;
}

/** Delete a tag. Also removes its document edges. */
export async function deleteTag(tag_id: string): Promise<void> {
  const remaining = readTags().filter((t) => t.tag_id !== tag_id);
  writeTags(remaining);
  const remainingEdges = readEdges().filter((e) => e.tag_id !== tag_id);
  writeEdges(remainingEdges);
}

/** Attach a tag to a document. Idempotent. */
export async function addTagToDocument(
  document_id: string,
  tag_id: string,
): Promise<void> {
  const edges = readEdges();
  if (edges.some((e) => e.document_id === document_id && e.tag_id === tag_id)) {
    return;
  }
  edges.push({
    document_id,
    tag_id,
    added_at: new Date().toISOString(),
  });
  writeEdges(edges);
}

/** Detach a tag from a document. */
export async function removeTagFromDocument(
  document_id: string,
  tag_id: string,
): Promise<void> {
  const remaining = readEdges().filter(
    (e) => !(e.document_id === document_id && e.tag_id === tag_id),
  );
  writeEdges(remaining);
}

/** List tag ids for one document. */
export async function listTagsForDocument(
  document_id: string,
): Promise<string[]> {
  return readEdges()
    .filter((e) => e.document_id === document_id)
    .map((e) => e.tag_id);
}

/** List document ids carrying a given tag. */
export async function listDocumentsWithTag(
  tag_id: string,
): Promise<string[]> {
  return readEdges()
    .filter((e) => e.tag_id === tag_id)
    .map((e) => e.document_id);
}

/** TEST/DEV ONLY — wipe all tags state. */
export function _resetTagsForTests(): void {
  writeTags([]);
  writeEdges([]);
}
