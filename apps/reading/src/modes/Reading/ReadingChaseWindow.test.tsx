import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useWindows } from "../../workspace/windowsStore";
import ReadingChaseWindow from "./ReadingChaseWindow";

vi.mock("../ResearchWorkstation/ChaseThread", () => ({
  default: ({ onOpenInMain }: { onOpenInMain: (id: string) => void }) => (
    <button onClick={() => onOpenInMain("child-1")}>Promote research</button>
  ),
}));

describe("ReadingChaseWindow", () => {
  beforeEach(() => useWindows.getState().reset());

  it("shows honest source context and closes its exact host on promotion", () => {
    useWindows.getState().open("readingChase", {}, { id: "win:mine" });
    useWindows.getState().open("readingChase", {}, { id: "win:other" });
    render(
      <ReadingChaseWindow
        spawnContext="A bounded passage"
        parentInvestigationId="read-doc-1"
        documentTitle="The Source"
        pageNumber={7}
        workspaceWindowId="win:mine"
      />,
    );
    expect(screen.getByText(/From The Source · page 7/)).toBeTruthy();
    expect(screen.getByText(/A bounded passage/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Promote research" }));
    expect(useWindows.getState().windows["win:mine"]).toBeUndefined();
    expect(useWindows.getState().windows["win:other"]).toBeTruthy();
  });
});
