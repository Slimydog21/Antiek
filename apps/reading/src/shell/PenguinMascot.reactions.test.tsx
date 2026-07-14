import { act, cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { emitWernerExperience, WERNER_EXPERIENCE_EVENT } from "../werner";
import { useWorkspace } from "../workspace/WorkspaceStore";
import { PenguinMascot } from "./PenguinMascot";

beforeEach(() => {
  useWorkspace.getState().reset();
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    configurable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }),
  });
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("PenguinMascot product reactions", () => {
  it("translates real product experiences through its single stage", () => {
    render(
      <MemoryRouter initialEntries={["/brainstorm"]}>
        <PenguinMascot />
      </MemoryRouter>,
    );
    const mascot = screen.getByTestId("penguin-mascot");
    expect(mascot.getAttribute("data-werner-emote")).toBe("none");

    act(() => emitWernerExperience("highlight"));
    expect(mascot.getAttribute("data-werner-emote")).toBe("curious");

    act(() => emitWernerExperience("deep_research_complete"));
    expect(mascot.getAttribute("data-werner-emote")).toBe("happy");

    act(() => emitWernerExperience("source_read_committed"));
    expect(mascot.getAttribute("data-werner-emote")).toBe("happy");

    act(() => emitWernerExperience("outline_block_committed"));
    expect(mascot.getAttribute("data-werner-emote")).toBe("curious");

    act(() => emitWernerExperience("speak_invite_committed"));
    expect(mascot.getAttribute("data-werner-emote")).toBe("happy");
  });

  it("removes the shared reaction listener on unmount", () => {
    const remove = vi.spyOn(window, "removeEventListener");
    const view = render(
      <MemoryRouter>
        <PenguinMascot />
      </MemoryRouter>,
    );

    view.unmount();

    expect(remove).toHaveBeenCalledWith(
      WERNER_EXPERIENCE_EVENT,
      expect.any(Function),
    );
  });
});
