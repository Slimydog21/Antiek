import {
  dispatchBrainstormQuestionSelection,
} from "../../BrainstormStation/WatchForLaterPanel";
import type { ParkedQuestionEntry } from "../../../lib/api";

export function openNotebookQuestionInBrainstorm({
  parkedQuestionId,
  text,
}: {
  parkedQuestionId: string;
  text: string;
}) {
  const question: ParkedQuestionEntry = {
    question_id: parkedQuestionId,
    question_text: text,
    source_investigation_id: "notebook",
    source_document_id: null,
    anchor_region_id: null,
    parked_at: new Date().toISOString(),
    parent_event_id: null,
  };
  dispatchBrainstormQuestionSelection(question);
  window.history.pushState({}, "", "/brainstorm");
  window.dispatchEvent(
    typeof PopStateEvent === "undefined"
      ? new Event("popstate")
      : new PopStateEvent("popstate", { state: {} }),
  );
}

export async function openNotebookQuestionInChase(text: string) {
  const { useWorkspace } = await import("../../../workspace/WorkspaceStore");
  useWorkspace.getState().open(
    "Chase",
    {
      spawnContext: text,
      parentInvestigationId: "notebook",
    },
    {
      mode: "floating",
      title: "Chase",
      id: `chase:${text.slice(0, 32)}`,
    },
  );
}
