import { isDocumentAnchor, type DocumentAnchor } from "../contracts/anchor";

/** Model reply fields stay in wire form; these actions require user confirmation. */
export type PaneReplyAction =
  | { kind: "open_document"; anchor: DocumentAnchor }
  | { kind: "open_writer"; deliverable_id: string; block_id?: string }
  | { kind: "project_seed"; title: string; prompt: string; sources?: string[] };

/** Null admits the pane action; unrelated legacy kinds remain executor-validated. */
export function paneActionProblem(item: Record<string, unknown>): string | null {
  switch (item.kind) {
    case "open_document":
      return isDocumentAnchor(item.anchor) ? null : "open_document: anchor is not a DocumentAnchor";
    case "open_writer":
      if (typeof item.deliverable_id !== "string" || !item.deliverable_id) return "open_writer: deliverable_id required";
      if (item.block_id !== undefined && typeof item.block_id !== "string") return "open_writer: section must be text";
      return null;
    case "project_seed":
      if (typeof item.title !== "string" || !item.title) return "project_seed: title required";
      if (typeof item.prompt !== "string" || !item.prompt) return "project_seed: prompt required";
      if (item.sources !== undefined && !(Array.isArray(item.sources) && item.sources.every((x) => typeof x === "string"))) {
        return "project_seed: sources must be an array of strings";
      }
      return null;
    default:
      return null;
  }
}
