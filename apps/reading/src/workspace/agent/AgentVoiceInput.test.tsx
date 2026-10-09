/** UNIT caller-admission controls; no real microphone/account/provider request. */
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AgentVoiceInput, type AgentVoiceAdmission } from "./AgentVoiceInput";

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

describe("voice capture caller admission", () => {
  it.each(["null", "false", "unknown", "truthy", "throw", "capture-throw"] as const)("%s admission cannot request a microphone or publish a draft", (kind) => {
    const microphone = vi.fn();
    Object.defineProperty(navigator, "mediaDevices", { configurable: true, value: { getUserMedia: microphone } });
    const admission: AgentVoiceAdmission = { isCurrent: () => false, subscribe: vi.fn(() => () => {}) };
    Object.defineProperty(admission, "isCurrent", { value: () => {
      if (kind === "throw") throw new Error("UNIT current failure");
      return kind === "truthy" ? 1 : kind === "unknown" ? undefined : false;
    } });
    const onTranscript = vi.fn();
    const onRecordingChange = vi.fn();
    const registerStop = vi.fn(() => () => {});
    render(<AgentVoiceInput
      captureAdmission={() => {
        if (kind === "capture-throw") throw new Error("UNIT capture failure");
        return kind === "null" ? null : admission;
      }}
      onTranscript={onTranscript}
      onRecordingChange={onRecordingChange}
      registerStop={registerStop}
    />);
    fireEvent.click(screen.getByRole("button", { name: "Record voice" }));
    expect(screen.getByRole("status").textContent).toContain("Voice input is unavailable");
    expect(microphone).not.toHaveBeenCalled();
    expect(onTranscript).not.toHaveBeenCalled();
    expect(onRecordingChange).not.toHaveBeenCalled();
    expect(registerStop).not.toHaveBeenCalled();
    expect(admission.subscribe).not.toHaveBeenCalled();
  });
});
