import { beforeEach, describe, expect, it, vi } from "vitest";

const bridgeMocks = vi.hoisted(() => ({
  dispatchBrainstormQuestionSelection: vi.fn(),
}));

vi.mock("../../BrainstormStation/WatchForLaterPanel", () => ({
  dispatchBrainstormQuestionSelection:
    bridgeMocks.dispatchBrainstormQuestionSelection,
}));

import { useWorkspace } from "../../../workspace/WorkspaceStore";
import {
  openNotebookQuestionInBrainstorm,
  openNotebookQuestionInChase,
} from "./QuestionCardBlock";

describe("QuestionCardBlock Brainstorm handoff", () => {
  beforeEach(() => {
    bridgeMocks.dispatchBrainstormQuestionSelection.mockReset();
    useWorkspace.getState().reset();
    window.history.pushState({}, "", "/notebook/notebook-1");
  });

  it("seeds Brainstorm with the parked question and navigates to the Brainstorm route", () => {
    const popstate = vi.fn();
    window.addEventListener("popstate", popstate);

    openNotebookQuestionInBrainstorm({
      parkedQuestionId: "q-notebook-1",
      text: "What should this source make me research next?",
    });

    expect(bridgeMocks.dispatchBrainstormQuestionSelection).toHaveBeenCalledWith({
      question_id: "q-notebook-1",
      question_text: "What should this source make me research next?",
      source_investigation_id: "notebook",
      source_document_id: null,
      anchor_region_id: null,
      parked_at: expect.any(String),
      parent_event_id: null,
    });
    expect(window.location.pathname).toBe("/brainstorm");
    expect(popstate).toHaveBeenCalledTimes(1);

    window.removeEventListener("popstate", popstate);
  });

  it("opens the free-text fallback Chase panel with the Chase prop contract", async () => {
    await openNotebookQuestionInChase("What hidden assumption should I test?");

    const panel = Object.values(useWorkspace.getState().panels)[0];
    expect(panel).toMatchObject({
      kind: "Chase",
      mode: "floating",
      title: "Chase",
      props: {
        spawnContext: "What hidden assumption should I test?",
        parentInvestigationId: "notebook",
      },
    });
  });
});
