import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, fireEvent } from "@testing-library/react";

import SpokenReply from "./SpokenReply";

const { speakMock, stopMock, hookState } = vi.hoisted(() => ({
  speakMock: vi.fn().mockResolvedValue(undefined),
  stopMock: vi.fn(),
  hookState: { state: "idle" as string, error: null as string | null },
}));

vi.mock("../hooks/useSpeech", () => ({
  useSpeech: () => ({
    state: hookState.state,
    error: hookState.error,
    speak: speakMock,
    stop: stopMock,
  }),
}));

beforeEach(() => {
  speakMock.mockClear();
  stopMock.mockClear();
  hookState.state = "idle";
  hookState.error = null;
});
afterEach(() => cleanup());

describe("SpokenReply", () => {
  it("speaks the reply text when Listen is clicked", () => {
    render(<SpokenReply text="The Stoics held that virtue suffices." voice="nova" />);
    fireEvent.click(screen.getByRole("button", { name: "Listen to reply" }));
    expect(speakMock).toHaveBeenCalledWith("The Stoics held that virtue suffices.", "nova");
  });

  it("auto-plays on mount when the reply-mode preference is audio", () => {
    render(<SpokenReply text="auto spoken reply" autoPlay />);
    expect(speakMock).toHaveBeenCalledWith("auto spoken reply", undefined);
  });

  it("does not auto-play when autoPlay is false (text preference)", () => {
    render(<SpokenReply text="silent until clicked" />);
    expect(speakMock).not.toHaveBeenCalled();
  });

  it("shows a Stop control while playing", () => {
    hookState.state = "playing";
    render(<SpokenReply text="now playing" />);
    const btn = screen.getByRole("button", { name: "Stop audio reply" });
    fireEvent.click(btn);
    expect(stopMock).toHaveBeenCalled();
  });

  it("surfaces an error from the hook", () => {
    hookState.state = "error";
    hookState.error = "Voice replies aren’t available right now.";
    render(<SpokenReply text="x" />);
    expect(screen.getByRole("alert").textContent).toMatch(/aren’t available/);
  });
});
