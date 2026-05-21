// SPR-06 / M3 — Folders client (localStorage-backed for this sprint).
//
// The canonical schema for folders + document_folders lives in
// services/library/migrations/0001_folders_tags.sql. There is no
// FastAPI handler that surfaces those tables today — the spec wired
// the file path but the SPR-03 substrate didn't ship a folders
// endpoint, and the SPR-06 surface needs SOMETHING the user can
// click without us building a backend route the spec didn't ask for.
//
// Strategy: persist folders + document↔folder edges in
// localStorage under stable namespaced keys. The exported API mirrors
// what a future REST endpoint would expose (list / create / delete /
// addDocument / removeDocument / listForDocument), so flipping the
// implementation from localStorage to fetch() is a one-file change.
//
// Honesty note (per rigor #1, intellectual honesty): this is
// single-device storage. A user logged in on two browsers will see
// two different folder sets. The handoff packet calls this out so
// the next sprint doesn't surprise itself.
//
// All functions are sync today (localStorage is sync) but typed as
// Promise-returning so the future REST swap is a no-op at call
// sites.

const FOLDERS_KEY = "antiek.library.folders.v1";
const DOC_FOLDERS_KEY = "antiek.library.documentFolders.v1";

/** One folder row. Mirrors the columns of `folders` in the migration. */
export interface Folder {
  folder_id: string;
  owner_user_id: string;
  name: string;
  sort_order: number;
  created_at: string;  // ISO 8601
}

/** One document↔folder edge. Mirrors `document_folders`. */
export interface DocumentFolderEdge {
  document_id: string;
  folder_id: string;
  added_at: string;
}

function readFolders(): Folder[] {
  if (typeof window === "undefined" || !window.localStorage) return [];
  const raw = window.localStorage.getItem(FOLDERS_KEY);
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw) as unknown;
    return Array.isArray(parsed) ? (parsed as Folder[]) : [];
  } catch {
    return [];
  }
}

function writeFolders(folders: Folder[]): void {
  if (typeof window === "undefined" || !window.localStorage) return;
  window.localStorage.setItem(FOLDERS_KEY, JSON.stringify(folders));
}

function readEdges(): DocumentFolderEdge[] {
  if (typeof window === "undefined" || !window.localStorage) return [];
  const raw = window.localStorage.getItem(DOC_FOLDERS_KEY);
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw) as unknown;
    return Array.isArray(parsed) ? (parsed as DocumentFolderEdge[]) : [];
  } catch {
    return [];
  }
}

function writeEdges(edges: DocumentFolderEdge[]): void {
  if (typeof window === "undefined" || !window.localStorage) return;
  window.localStorage.setItem(DOC_FOLDERS_KEY, JSON.stringify(edges));
}

function newFolderId(): string {
  const hex = Math.floor(Math.random() * 0xffffffffffff)
    .toString(16)
    .padStart(12, "0");
  return `fld-${hex}`;
}

/** List all folders for the current user, sorted by sort_order then name. */
export async function listFolders(): Promise<Folder[]> {
  const folders = readFolders().slice();
  folders.sort((a, b) => {
    if (a.sort_order !== b.sort_order) return a.sort_order - b.sort_order;
    return a.name.localeCompare(b.name);
  });
  return folders;
}

/** Create a new folder. Names are NOT auto-deduplicated — the user
 * may legitimately want two folders called "Inbox" if they later
 * realise they meant different things. */
export async function createFolder(name: string): Promise<Folder> {
  const trimmed = name.trim();
  if (!trimmed) {
    throw new Error("folder name cannot be empty");
  }
  const existing = readFolders();
  const folder: Folder = {
    folder_id: newFolderId(),
    owner_user_id: "__operator__",
    name: trimmed,
    sort_order: existing.length,
    created_at: new Date().toISOString(),
  };
  existing.push(folder);
  writeFolders(existing);
  return folder;
}

/** Delete a folder. Also removes any document↔folder edges that
 * referenced it (cascade-on-delete is the user's expected mental
 * model). */
export async function deleteFolder(folder_id: string): Promise<void> {
  const remaining = readFolders().filter((f) => f.folder_id !== folder_id);
  writeFolders(remaining);
  const remainingEdges = readEdges().filter((e) => e.folder_id !== folder_id);
  writeEdges(remainingEdges);
}

/** Add a document to a folder. Idempotent — re-adding is a no-op. */
export async function addDocumentToFolder(
  document_id: string,
  folder_id: string,
): Promise<void> {
  const edges = readEdges();
  if (edges.some((e) => e.document_id === document_id && e.folder_id === folder_id)) {
    return;
  }
  edges.push({
    document_id,
    folder_id,
    added_at: new Date().toISOString(),
  });
  writeEdges(edges);
}

/** Remove a document from a folder. */
export async function removeDocumentFromFolder(
  document_id: string,
  folder_id: string,
): Promise<void> {
  const remaining = readEdges().filter(
    (e) => !(e.document_id === document_id && e.folder_id === folder_id),
  );
  writeEdges(remaining);
}

/** List folder ids for one document. */
export async function listFoldersForDocument(
  document_id: string,
): Promise<string[]> {
  return readEdges()
    .filter((e) => e.document_id === document_id)
    .map((e) => e.folder_id);
}

/** List document ids for one folder. */
export async function listDocumentsInFolder(
  folder_id: string,
): Promise<string[]> {
  return readEdges()
    .filter((e) => e.folder_id === folder_id)
    .map((e) => e.document_id);
}

/** TEST/DEV ONLY — wipe all folders state. Tests call this between
 * runs; production code should never need it. */
export function _resetFoldersForTests(): void {
  writeFolders([]);
  writeEdges([]);
}
