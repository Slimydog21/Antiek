import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import NotebookCanvas from "./NotebookCanvas";
import type { NotebookResponse } from "./types";

const questionMocks = vi.hoisted(() => ({
  openNotebookQuestionInBrainstorm: vi.fn(),
  openNotebookQuestionInChase: vi.fn(),
}));

vi.mock("./blocks/questionHandoff", () => ({
  openNotebookQuestionInBrainstorm:
    questionMocks.openNotebookQuestionInBrainstorm,
  openNotebookQuestionInChase: questionMocks.openNotebookQuestionInChase,
}));

function notebook(blocks: NotebookResponse["blocks"]): NotebookResponse {
  return {
    notebook_id: "nb-1",
    title: "Research notebook",
    investigation_id: "inv-1",
    document_id: null,
    content_class: "user_owned",
    created_at: "2026-07-01T00:00:00Z",
    updated_at: "2026-07-01T00:00:00Z",
    blocks,
  };
}

describe("NotebookCanvas question-card handoff", () => {
  beforeEach(() => {
    questionMocks.openNotebookQuestionInBrainstorm.mockReset();
    questionMocks.openNotebookQuestionInChase.mockReset();
  });
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("opens a parked question in Brainstorm from the live routed canvas", async () => {
    const data = notebook([
      {
        block_id: "block-q1",
        block_index: 0,
        block_type: "question_card",
        ref_id: "q-live-1",
        content_json: {
          question_text: "What should this source make me research next?",
        },
        created_at: "2026-07-01T00:00:00Z",
      },
    ]);

    render(<NotebookCanvas notebook={data} onAppendBlock={vi.fn()} />);

    await userEvent.click(
      screen.getByRole("button", { name: "brainstorm" }),
    );

    expect(questionMocks.openNotebookQuestionInBrainstorm).toHaveBeenCalledWith({
      parkedQuestionId: "q-live-1",
      text: "What should this source make me research next?",
    });
    expect(screen.queryByText(/^open:/)).toBeNull();
  });

  it("opens a free-text notebook question in Chase when there is no parked id", async () => {
    const data = notebook([
      {
        block_id: "block-q2",
        block_index: 0,
        block_type: "question_card",
        ref_id: null,
        content_json: {
          question_text: "What hidden assumption should I test?",
        },
        created_at: "2026-07-01T00:00:00Z",
      },
    ]);

    render(<NotebookCanvas notebook={data} onAppendBlock={vi.fn()} />);

    await userEvent.click(screen.getByRole("button", { name: "chase" }));

    expect(questionMocks.openNotebookQuestionInChase).toHaveBeenCalledWith(
      "What hidden assumption should I test?",
    );
  });

  it("drops malformed block ids instead of rendering actionable rows", () => {
    const data = notebook([
      {
        block_id: " block-valid ",
        block_index: 0,
        block_type: "prose",
        ref_id: null,
        content_json: { text: "Visible prose" },
        created_at: "2026-07-01T00:00:00Z",
      },
      {
        block_id: " ",
        block_index: 1,
        block_type: "prose",
        ref_id: null,
        content_json: { text: "Invisible prose" },
        created_at: "2026-07-01T00:00:00Z",
      },
    ]);

    render(<NotebookCanvas notebook={data} onAppendBlock={vi.fn()} />);

    expect(screen.getByText("Visible prose")).toBeTruthy();
    expect(screen.queryByText("Invisible prose")).toBeNull();
    expect(document.body.textContent).toContain("1 block");
  });

  it("trims block ids before move/delete/edit callbacks", async () => {
    const onMoveBlock = vi.fn();
    const onDeleteBlock = vi.fn();
    const onEditBlock = vi.fn();
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const data = notebook([
      {
        block_id: " block-valid ",
        block_index: 0,
        block_type: "prose",
        ref_id: null,
        content_json: { text: "Editable prose" },
        created_at: "2026-07-01T00:00:00Z",
      },
    ]);

    render(
      <NotebookCanvas
        notebook={data}
        onAppendBlock={vi.fn()}
        onMoveBlock={onMoveBlock}
        onDeleteBlock={onDeleteBlock}
        onEditBlock={onEditBlock}
      />,
    );

    await userEvent.click(screen.getByTitle("Delete block"));
    expect(onDeleteBlock).toHaveBeenCalledWith("block-valid");

    await userEvent.dblClick(screen.getByText("Editable prose"));
    const editor = screen.getByRole("textbox");
    await userEvent.clear(editor);
    await userEvent.type(editor, "Edited prose");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(onEditBlock).toHaveBeenCalledWith("block-valid", { text: "Edited prose" });

    expect(onMoveBlock).not.toHaveBeenCalled();
  });
});
