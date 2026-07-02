import type { FolderSummary, RepositoryHit } from "./writeApi";

export type RepositoryBlockKind = "insight" | "open_question" | "claim";

const NODE_BLOCK_KINDS = new Set(["insight", "open_question", "claim"]);

export function repositoryBlockKind(nodeType: string): RepositoryBlockKind {
  const kind = nodeType.trim();
  return (NODE_BLOCK_KINDS.has(kind) ? kind : "claim") as RepositoryBlockKind;
}

function nonEmptyString(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

function finiteNonNegativeNumber(value: unknown): number | null {
  const parsed =
    typeof value === "number"
      ? value
      : typeof value === "string" && value.trim() !== ""
        ? Number(value)
        : Number.NaN;
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : null;
}

export function safeFolders(folders: FolderSummary[]): FolderSummary[] {
  return folders.flatMap((folder) => {
    const folderId = nonEmptyString(folder.folder_id);
    const name = nonEmptyString(folder.name);
    if (!folderId || !name) return [];
    return [
      {
        ...folder,
        folder_id: folderId,
        name,
        member_count: finiteNonNegativeNumber(folder.member_count) ?? 0,
      },
    ];
  });
}

export function safeRepositoryHits(hits: RepositoryHit[]): RepositoryHit[] {
  return hits.flatMap((hit) => {
    const nodeId = nonEmptyString(hit.node_id);
    const label = nonEmptyString(hit.label);
    if (!nodeId || !label) return [];
    return [
      {
        ...hit,
        node_id: nodeId,
        label,
        document_title: nonEmptyString(hit.document_title),
        source_tier: finiteNonNegativeNumber(hit.source_tier),
      },
    ];
  });
}
